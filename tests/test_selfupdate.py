"""就地更新模块测试。

这里要守住的是**安全与不破坏用户环境**两条底线：

- 摘要不匹配的下载一律丢弃，绝不落盘待用；
- 上游没给摘要就宁可不让用户自动更新；
- 替换只在确认过目标之后进行，且目标与自身相同时必须拒绝。

网络与子进程全部打桩，不依赖真实网络，也不会真的去替换什么东西。
"""

from __future__ import annotations

import hashlib
import os
import urllib.error

import pytest

from renamer import selfupdate as su
from renamer.update import Asset, Release, UpdateError

# ------------------------------------------------------------------ 桩

class _FakeResponse:
    """够用的假响应：``with`` + ``headers`` + 分块 ``read``。"""

    def __init__(self, data: bytes, content_length: int | None = None) -> None:
        self._data = data
        self._pos = 0
        size = len(data) if content_length is None else content_length
        self.headers = {"Content-Length": str(size)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            block = self._data[self._pos:]
            self._pos = len(self._data)
            return block
        block = self._data[self._pos:self._pos + size]
        self._pos += len(block)
        return block


def _asset(name: str = "File-Renaming-Assistant.exe",
           url: str = "https://example.com/a.exe",
           api_url: str = "https://api.example.com/1",
           size: int = 0, digest: str = "sha256:00") -> Asset:
    return Asset(name=name, url=url, api_url=api_url, size=size, digest=digest)


def _release(assets: tuple[Asset, ...] = (), version: str = "v9.9.9") -> Release:
    return Release(version=version, url="https://example.com/rel",
                   name=version, notes="", assets=assets)


@pytest.fixture()
def on_windows(monkeypatch):
    """把平台伪装成 Windows，附件名才有约定。"""
    monkeypatch.setattr(su.sys, "platform", "win32")


@pytest.fixture()
def frozen(monkeypatch):
    """伪装成打包运行（``supports_self_update`` 要求 ``sys.frozen``）。"""
    monkeypatch.setattr(su.sys, "frozen", True, raising=False)


@pytest.fixture()
def fast_retry(monkeypatch):
    """让 ``apply_update`` 的退避重试不真的睡，否则每条用例要等好几秒。"""
    monkeypatch.setattr(su.time, "sleep", lambda _seconds: None)


# ------------------------------------------------------------------ 环境

def test_update_root_follows_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(su.ENV_OVERRIDE, str(tmp_path / "upd"))
    assert su.update_root() == str(tmp_path / "upd")


def test_update_root_defaults_to_temp(monkeypatch):
    monkeypatch.delenv(su.ENV_OVERRIDE, raising=False)
    assert su.DIR_NAME in su.update_root()


def test_asset_name_is_empty_on_unknown_platform(monkeypatch):
    monkeypatch.setattr(su.sys, "platform", "plan9")
    assert su.asset_name() == ""


def test_supports_self_update_requires_frozen(on_windows, tmp_path):
    """从源码运行时不能自动更新 —— 否则会去替换用户的 python 解释器。"""
    assert su.supports_self_update() is False


def test_supports_self_update_true_when_frozen(on_windows, frozen, monkeypatch, tmp_path):
    exe = tmp_path / "app.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(su, "target_executable", lambda: str(exe))
    assert su.supports_self_update() is True


# ------------------------------------------------------------------ 挑附件

def test_pick_asset_returns_matching_asset(on_windows):
    asset = _asset()
    assert su.pick_asset(_release((asset,))) is asset


def test_pick_asset_rejects_release_without_that_asset(on_windows):
    with pytest.raises(UpdateError) as info:
        su.pick_asset(_release((_asset(name="other.exe"),)))
    assert "没有找到附件" in str(info.value)


def test_pick_asset_rejects_asset_without_digest(on_windows):
    """没有 SHA256 就没法确认下到的是不是原文件，宁可不更新。"""
    with pytest.raises(UpdateError) as info:
        su.pick_asset(_release((_asset(digest=""),)))
    assert "SHA256" in str(info.value)


def test_pick_asset_rejects_unsupported_platform(monkeypatch):
    monkeypatch.setattr(su.sys, "platform", "plan9")
    with pytest.raises(UpdateError) as info:
        su.pick_asset(_release((_asset(),)))
    assert "plan9" in str(info.value)


# ------------------------------------------------------------------ 校验

def test_sha256_file_matches_hashlib(tmp_path):
    path = tmp_path / "a.bin"
    path.write_bytes(b"hello")
    assert su.sha256_file(str(path)) == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_verify_accepts_matching_digest(tmp_path):
    path = tmp_path / "a.bin"
    path.write_bytes(b"hello")
    su.verify(str(path), su.sha256_file(str(path)))       # 不抛异常即通过
    assert path.exists()


def test_verify_rejects_mismatch_and_deletes_file(tmp_path):
    """校验不过的文件必须当场删掉：留在临时目录可能被误当成「已下好」。"""
    path = tmp_path / "a.bin"
    path.write_bytes(b"hello")
    with pytest.raises(UpdateError) as info:
        su.verify(str(path), "00" * 32)
    assert "校验失败" in str(info.value)
    assert not path.exists()


def test_verify_rejects_empty_digest(tmp_path):
    path = tmp_path / "a.bin"
    path.write_bytes(b"hello")
    with pytest.raises(UpdateError):
        su.verify(str(path), "")


# ------------------------------------------------------------------ 下载

def test_download_writes_file_and_reports_progress(monkeypatch, tmp_path):
    data = b"x" * (700 * 1024)          # 跨过多个分块
    monkeypatch.setattr(su.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(data))
    dest = tmp_path / "out" / "a.exe"
    seen: list[tuple[int, int]] = []

    su.download(_asset(size=len(data)), str(dest),
                progress=lambda done, total: seen.append((done, total)))

    assert dest.read_bytes() == data
    assert len(seen) > 1, "必须分块回调，否则进度条是假的"
    assert seen[-1] == (len(data), len(data))


def test_download_falls_back_to_api_url(monkeypatch, tmp_path):
    """发布页直链不通时改用接口地址，两条链路落在不同主机上。"""
    seen: list[str] = []

    def dispatch(request, *_a, **_k):
        seen.append(request.full_url)
        if request.full_url.startswith("https://example.com/"):
            raise urllib.error.URLError("直链不通")
        return _FakeResponse(b"ok")

    monkeypatch.setattr(su.urllib.request, "urlopen", dispatch)
    dest = tmp_path / "a.exe"
    su.download(_asset(), str(dest))

    assert dest.read_bytes() == b"ok"
    assert seen == ["https://example.com/a.exe", "https://api.example.com/1"]


def test_download_reports_all_failures(monkeypatch, tmp_path):
    def boom(*_a, **_k):
        raise urllib.error.URLError("全都不通")

    monkeypatch.setattr(su.urllib.request, "urlopen", boom)
    with pytest.raises(UpdateError) as info:
        su.download(_asset(), str(tmp_path / "a.exe"))
    assert "下载失败" in str(info.value)


def test_download_cancel_removes_partial_file(monkeypatch, tmp_path):
    """取消不是失败：抛 DownloadCancelled，并且把半截文件清掉。"""
    data = b"y" * (1024 * 1024)
    monkeypatch.setattr(su.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(data))
    counts = {"n": 0}

    def cancel() -> bool:
        counts["n"] += 1
        return counts["n"] > 1

    dest = tmp_path / "a.exe"
    with pytest.raises(su.DownloadCancelled):
        su.download(_asset(), str(dest), cancel=cancel)

    assert not dest.exists()
    assert isinstance(su.DownloadCancelled("x"), UpdateError), \
        "取消要能被 UpdateError 捕获，界面才能少写一条分支"


def test_download_uses_expected_size_when_header_missing(monkeypatch, tmp_path):
    """没有 Content-Length 时用附件声明的字节数，进度条才不会一直转圈。"""
    data = b"z" * 4096
    response = _FakeResponse(data, content_length=0)
    response.headers = {}
    monkeypatch.setattr(su.urllib.request, "urlopen", lambda *a, **k: response)
    seen: list[tuple[int, int]] = []

    su.download(_asset(size=len(data)), str(tmp_path / "a.exe"),
                progress=lambda done, total: seen.append((done, total)))

    assert seen[-1] == (len(data), len(data))


# ------------------------------------------------------------------ 落盘

def test_stage_refuses_when_self_update_unsupported(on_windows):
    with pytest.raises(UpdateError) as info:
        su.stage(_release((_asset(),)))
    assert "不支持自动更新" in str(info.value)


def test_stage_downloads_and_verifies(monkeypatch, tmp_path, on_windows, frozen):
    """完整走一遍「挑附件 → 下载 → 校验 → 落盘」。"""
    data = b"the new build"
    expected = hashlib.sha256(data).hexdigest()

    exe = tmp_path / "app.exe"
    exe.write_bytes(b"old")
    monkeypatch.setattr(su, "target_executable", lambda: str(exe))
    monkeypatch.setattr(su, "update_root", lambda: str(tmp_path / "upd"))
    monkeypatch.setattr(su.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(data))

    staged = su.stage(_release((_asset(size=len(data),
                                       digest=f"sha256:{expected}"),)))

    assert open(staged.path, "rb").read() == data
    assert staged.target == str(exe)
    assert staged.version == "v9.9.9"
    assert staged.size == len(data)


def test_stage_discards_file_when_digest_mismatches(monkeypatch, tmp_path,
                                                   on_windows, frozen):
    exe = tmp_path / "app.exe"
    exe.write_bytes(b"old")
    monkeypatch.setattr(su, "target_executable", lambda: str(exe))
    monkeypatch.setattr(su, "update_root", lambda: str(tmp_path / "upd"))
    monkeypatch.setattr(su.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(b"tampered"))

    with pytest.raises(UpdateError):
        su.stage(_release((_asset(digest="sha256:" + "11" * 32),)))

    leftovers = list((tmp_path / "upd").rglob("*.exe"))
    assert leftovers == [], "校验失败的下载必须被删掉"


# ------------------------------------------------------------------ 替换

def test_apply_update_replaces_target(tmp_path):
    target = tmp_path / "target.exe"
    source = tmp_path / "source.exe"
    target.write_bytes(b"old")
    source.write_bytes(b"new")

    su.apply_update(str(target), str(source))

    assert target.read_bytes() == b"new"
    assert not source.exists(), "替换后源文件不该还留在临时目录里"


def test_apply_update_retries_until_unlocked(monkeypatch, tmp_path, fast_retry):
    """文件还被占用时退避重试，不查进程表也能等到旧进程退出。"""
    target = tmp_path / "target.exe"
    source = tmp_path / "source.exe"
    target.write_bytes(b"old")
    source.write_bytes(b"new")

    calls = {"n": 0}
    real_replace = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("文件被占用")
        return real_replace(src, dst)

    monkeypatch.setattr(su.os, "replace", flaky)
    su.apply_update(str(target), str(source), timeout=5.0)

    assert calls["n"] == 3
    assert target.read_bytes() == b"new"


def test_apply_update_gives_up_and_explains(monkeypatch, tmp_path, fast_retry):
    def always_locked(*_a, **_k):
        raise PermissionError("文件被占用")

    monkeypatch.setattr(su.os, "replace", always_locked)
    with pytest.raises(UpdateError) as info:
        su.apply_update("t.exe", "s.exe", timeout=0.01)
    assert "无法替换" in str(info.value)


def test_apply_update_copies_when_target_on_another_volume(monkeypatch, tmp_path):
    """跨盘时 ``os.replace`` 必然失败，要先复制到目标旁边再改名。

    这不是边角情况：更新临时目录在系统临时目录（多半在 C 盘），
    而程序可能装在任何一块盘上。真机上就是踩到这个才通的。
    """
    target = tmp_path / "target.exe"
    source = tmp_path / "source.exe"
    target.write_bytes(b"old")
    source.write_bytes(b"new")

    monkeypatch.setattr(su, "_same_volume", lambda _a, _b: False)
    su.apply_update(str(target), str(source))

    assert target.read_bytes() == b"new"
    assert not source.exists(), "跨盘复制后源文件也要收掉"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".fra-update-")]
    assert leftovers == [], "落地的临时副本不能留在目标目录里"


def test_apply_update_cross_volume_retries_the_final_rename(monkeypatch, tmp_path,
                                                            fast_retry):
    """跨盘路径的最后一步同卷改名，同样要能等旧进程退出。"""
    target = tmp_path / "target.exe"
    source = tmp_path / "source.exe"
    target.write_bytes(b"old")
    source.write_bytes(b"new")

    monkeypatch.setattr(su, "_same_volume", lambda _a, _b: False)
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 2:
            raise PermissionError("文件被占用")
        return real_replace(src, dst)

    monkeypatch.setattr(su.os, "replace", flaky)
    su.apply_update(str(target), str(source), timeout=5.0)

    assert calls["n"] == 2
    assert target.read_bytes() == b"new"


def test_apply_update_cross_volume_cleans_up_on_failure(monkeypatch, tmp_path,
                                                        fast_retry):
    """跨盘时最终改名失败，临时副本要删掉，不能留在用户目录里。"""
    target = tmp_path / "target.exe"
    source = tmp_path / "source.exe"
    target.write_bytes(b"old")
    source.write_bytes(b"new")

    monkeypatch.setattr(su, "_same_volume", lambda _a, _b: False)
    monkeypatch.setattr(su.os, "replace",
                        lambda *_a, **_k: (_ for _ in ()).throw(PermissionError("锁")))

    with pytest.raises(UpdateError):
        su.apply_update(str(target), str(source), timeout=0.01)

    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".fra-update-")]
    assert leftovers == []
    assert target.read_bytes() == b"old", "失败时目标必须原样不动"


def test_same_volume_detection(tmp_path):
    """同一目录下的两个文件当然同卷。"""
    assert su._same_volume(str(tmp_path / "a"), str(tmp_path / "b")) is True


@pytest.mark.skipif(
    os.name != "nt",
    reason="盘符只有 Windows 才有意义：POSIX 上 os.path.splitdrive 恒返回空串，"
           "拿 'C:\\…' 与 'F:\\…' 去比会得到「同卷」，这个断言在那里没有意义",
)
def test_same_volume_detects_different_drives():
    assert su._same_volume(r"C:\a\b", r"F:\c\d") is False


# ------------------------------------------------------------------ 助手模式

def test_is_apply_request():
    assert su.is_apply_request(["app.exe", su.APPLY_FLAG, "t.exe"]) is True
    assert su.is_apply_request(["app.exe"]) is False


def test_run_apply_requires_target():
    assert su.run_apply(["app.exe", su.APPLY_FLAG]) == 2


def test_run_apply_refuses_to_replace_itself(monkeypatch, tmp_path):
    """目标就是自己时直接拒绝 —— 否则等于把正在跑的程序改成别的。"""
    exe = tmp_path / "app.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(su, "target_executable", lambda: str(exe))

    assert su.run_apply(["app.exe", su.APPLY_FLAG, str(exe)]) == 2


def test_run_apply_reports_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(su, "target_executable", lambda: str(tmp_path / "src.exe"))
    monkeypatch.setattr(su, "apply_update",
                        lambda *_a, **_k: (_ for _ in ()).throw(UpdateError("磁盘满了")))
    assert su.run_apply(["app.exe", su.APPLY_FLAG, str(tmp_path / "t.exe")]) == 1


def test_run_apply_replaces_and_relaunches(monkeypatch, tmp_path):
    target = tmp_path / "target.exe"
    source = tmp_path / "source.exe"
    target.write_bytes(b"old")
    source.write_bytes(b"new")

    started: list[str] = []
    monkeypatch.setattr(su, "target_executable", lambda: str(source))
    monkeypatch.setattr(su, "relaunch", lambda path: started.append(path) or 1234)

    assert su.run_apply(["app.exe", su.APPLY_FLAG, str(target)]) == 0
    assert target.read_bytes() == b"new"
    assert started == [str(target)]


def test_run_apply_still_succeeds_when_relaunch_fails(monkeypatch, tmp_path):
    """文件已经换好了，只是没能自动打开 —— 不该回头把旧版写回去。"""
    target = tmp_path / "target.exe"
    source = tmp_path / "source.exe"
    target.write_bytes(b"old")
    source.write_bytes(b"new")

    def boom(_path):
        raise OSError("打不开")

    monkeypatch.setattr(su, "target_executable", lambda: str(source))
    monkeypatch.setattr(su, "relaunch", boom)

    assert su.run_apply(["app.exe", su.APPLY_FLAG, str(target)]) == 0
    assert target.read_bytes() == b"new"


# ------------------------------------------------------------------ 清理

def test_cleanup_stale_removes_old_and_keeps_fresh(tmp_path, monkeypatch):
    root = tmp_path / "upd"
    root.mkdir()
    old = root / "v1" / "a.exe"
    old.parent.mkdir()
    old.write_bytes(b"x")
    fresh = root / "v2" / "a.exe"
    fresh.parent.mkdir()
    fresh.write_bytes(b"x")

    # 判据是**目录**的修改时间（见 cleanup_stale 的注释），所以要把目录本身调旧
    stale = 2 * 24 * 3600
    aged = os.path.getmtime(old.parent) - stale
    os.utime(old.parent, (aged, aged))
    monkeypatch.setattr(su, "update_root", lambda: str(root))

    assert su.cleanup_stale(max_age=24 * 3600) == 1
    assert not (root / "v1").exists()
    assert fresh.exists()


def test_cleanup_stale_tolerates_missing_root(tmp_path, monkeypatch):
    monkeypatch.setattr(su, "update_root", lambda: str(tmp_path / "nope"))
    assert su.cleanup_stale() == 0


def test_cleanup_stale_removes_loose_files(tmp_path, monkeypatch):
    root = tmp_path / "upd"
    root.mkdir()
    loose = root / "leftover.tmp"
    loose.write_bytes(b"x")
    stale = 2 * 24 * 3600
    os.utime(loose, (os.path.getmtime(loose) - stale, os.path.getmtime(loose) - stale))
    monkeypatch.setattr(su, "update_root", lambda: str(root))

    assert su.cleanup_stale(max_age=24 * 3600) == 1
    assert not root.exists(), "清空后连目录本身也该收掉"


def test_cleanup_stale_ignores_unremovable(tmp_path, monkeypatch):
    """删不掉（被占着）就跳过，不能因此让启动流程报错。"""
    root = tmp_path / "upd"
    root.mkdir()
    victim = root / "v1"
    victim.mkdir()
    (victim / "a.exe").write_bytes(b"x")
    stale = 2 * 24 * 3600
    os.utime(victim, (os.path.getmtime(victim) - stale,
                      os.path.getmtime(victim) - stale))

    monkeypatch.setattr(su, "update_root", lambda: str(root))
    # ignore_errors=True 会把删除失败吞掉，于是目录还在、不该被计入
    monkeypatch.setattr(su.shutil, "rmtree", lambda *_a, **_k: None)

    assert su.cleanup_stale(max_age=24 * 3600) == 0
    assert victim.exists()


# ------------------------------------------------------------------ 与 update 的衔接

def test_asset_sha256_is_normalized():
    assert _asset(digest="SHA256:ABC").sha256 == "abc"
    assert _asset(digest="").sha256 == ""


def test_download_cancelled_is_catchable_as_update_error():
    assert issubclass(su.DownloadCancelled, UpdateError)
