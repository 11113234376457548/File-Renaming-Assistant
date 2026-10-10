"""检查更新模块测试。

网络部分全部打桩：只验证「拿到响应后怎么判断」和「异常怎么翻译成提示」，
不依赖真实网络，CI 里也不会因为 GitHub 抽风而红。
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from renamer import update


class _FakeResponse(io.BytesIO):
    """够用的假响应：支持 ``with`` 与 ``read()``。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _payload(tag: str = "v9.9.9") -> bytes:
    return json.dumps({
        "tag_name": tag,
        "name": f"Release {tag}",
        "html_url": f"https://example.com/{tag}",
        "body": "notes",
    }).encode("utf-8")


# ------------------------------------------------------------------ 版本比较

@pytest.mark.parametrize("text,expected", [
    ("v1.0", (1, 0, 0)),
    ("1.0", (1, 0, 0)),
    ("1.1", (1, 1, 0)),
    ("v2", (2, 0, 0)),
    ("v1.1.0-beta.1", (1, 1, 0)),
    ("  v10.0.2  ", (10, 0, 2)),
])
def test_parse_version(text, expected):
    assert update.parse_version(text) == expected


@pytest.mark.parametrize("latest,current,expected", [
    ("v1.1", "1.0", True),
    ("v1.0", "1.0", False),
    ("v1.0", "1.1", False),
    ("v2.0", "1.9", True),
    ("v1.10", "1.9", True),          # 逐段比较，10 > 9
    ("v1.1.1", "1.1", True),
])
def test_is_newer(latest, current, expected):
    assert update.is_newer(latest, current) is expected


# ------------------------------------------------------------------ 网络桩

def test_check_latest_parses_release(monkeypatch):
    monkeypatch.setattr(update.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(_payload("v2.0.0")))
    release = update.check_latest()
    assert release is not None
    assert release.version == "v2.0.0"
    assert release.url == "https://example.com/v2.0.0"
    assert update.is_newer(release.version, "1.0")


def test_check_latest_returns_none_when_no_release(monkeypatch):
    """仓库还在、只是没发过 Release 时，GitHub 对 latest 接口返回 404。

    这不是错误，界面应该说「作者尚未发布任何正式版本」；
    仓库接口要能正常返回，才说明仓库本身是存在的。
    """
    def dispatch(request, *a, **k):
        url = request.full_url
        if url == update.API_REPO:
            return _FakeResponse(json.dumps({"full_name": update.GITHUB_REPO})
                                 .encode("utf-8"))
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(update.urllib.request, "urlopen", dispatch)
    assert update.check_latest() is None


def test_check_latest_reports_missing_repo(monkeypatch):
    """仓库地址配错时不能伪装成「还没发过版本」，要明确报错。"""
    def raise_404(request, *a, **k):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found",
                                     None, None)

    monkeypatch.setattr(update.urllib.request, "urlopen", raise_404)
    with pytest.raises(update.UpdateError) as info:
        update.check_latest()
    assert "仓库不存在" in str(info.value)


def test_repo_probe_survives_network_error(monkeypatch):
    """探仓库时断网，不能误报成「仓库不存在」。"""
    def boom(*_a, **_k):
        raise urllib.error.URLError("名字解析失败")

    monkeypatch.setattr(update.urllib.request, "urlopen", boom)
    assert update._repo_exists(8.0) is True


def test_check_latest_wraps_network_error(monkeypatch):
    """断网要变成可读的提示，而不是把 URLError 抛到界面上。"""
    def boom(*_a, **_k):
        raise urllib.error.URLError("名字解析失败")

    monkeypatch.setattr(update.urllib.request, "urlopen", boom)
    with pytest.raises(update.UpdateError) as info:
        update.check_latest()
    assert "无法连接更新服务器" in str(info.value)


def test_check_latest_wraps_server_error(monkeypatch):
    def raise_500(*_a, **_k):
        raise urllib.error.HTTPError(update.API_LATEST, 500, "Server",
                                     None, None)

    monkeypatch.setattr(update.urllib.request, "urlopen", raise_500)
    with pytest.raises(update.UpdateError) as info:
        update.check_latest()
    assert "HTTP 500" in str(info.value)


def test_urls_are_derived_from_repo_slug():
    """接口地址与发布页都要跟着 GITHUB_REPO 走，fork 后只改一处即可。"""
    assert update.GITHUB_REPO in update.API_LATEST
    assert update.GITHUB_REPO in update.API_REPO
    assert update.GITHUB_REPO in update.RELEASES_PAGE


# ------------------------------------------------------------------ 附件

def _release_with_assets(assets: list[dict]) -> update.Release:
    payload = json.loads(_payload("v9.9.9"))
    payload["assets"] = assets
    return update._release_from_payload(payload)


def test_assets_are_parsed_with_digest():
    """GitHub 会给发布附件带 ``digest: sha256:...``，界面靠它决定能否自动更新。"""
    release = _release_with_assets([{
        "name": "File-Renaming-Assistant.exe",
        "browser_download_url": "https://example.com/a.exe",
        "url": "https://api.example.com/assets/1",
        "size": 1234,
        "digest": "sha256:AABBCC",
    }])
    assert len(release.assets) == 1
    asset = release.assets[0]
    assert asset.size == 1234
    assert asset.api_url == "https://api.example.com/assets/1"
    assert asset.sha256 == "aabbcc", "摘要要归一成小写裸十六进制"


def test_asset_lookup_ignores_case_and_missing_name():
    release = _release_with_assets([{
        "name": "File-Renaming-Assistant.exe",
        "browser_download_url": "https://example.com/a.exe",
        "url": "",
        "size": 1,
        "digest": "sha256:aa",
    }])
    assert release.asset("file-renaming-assistant.EXE") is not None
    assert release.asset("nope.exe") is None


def test_asset_sha256_only_accepts_sha256_digest():
    """摘要算法不是 sha256 时要当作「没有摘要」，不能拿去比对。"""
    release = _release_with_assets([{
        "name": "a.exe",
        "browser_download_url": "https://example.com/a.exe",
        "url": "",
        "size": 1,
        "digest": "md5:whatever",
    }])
    assert release.assets[0].sha256 == ""


@pytest.mark.parametrize("assets", [None, "not-a-list", [None, 42], [{}]])
def test_broken_assets_block_does_not_crash(assets):
    """``assets`` 字段缺失或结构异常时，只是没有附件，不该让解析炸掉。"""
    payload = json.loads(_payload())
    payload["assets"] = assets
    release = update._release_from_payload(payload)
    assert release.assets == ()
    assert release.version == "v9.9.9"


def test_asset_without_url_is_dropped():
    """没有下载地址的条目留着也没用，直接丢掉，免得后面拿到空链接。"""
    release = _release_with_assets([
        {"name": "a.exe", "browser_download_url": "", "size": 1, "digest": "sha256:aa"},
        {"name": "b.exe", "browser_download_url": "https://example.com/b.exe",
         "size": 1, "digest": "sha256:bb"},
    ])
    assert [a.name for a in release.assets] == ["b.exe"]
