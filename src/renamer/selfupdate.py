"""就地更新：下载新版本、校验、替换正在运行的程序。

## 为什么不能「自己替换自己」

Windows 不允许覆盖正在执行的映像文件，写入会被直接拒绝。PyInstaller 的单文件
模式还多一层：程序启动时 bootloader 先把自身解包到 ``%TEMP%\\_MEIxxxx``，
再从那里加载 Python 运行时，而磁盘上那个原始 exe 在整个进程存活期间一直被
占用。所以「下载完就直接覆盖自己」这条路在 Windows 上根本走不通。

## 走的路线

必须**先退出、再由另一个进程来完成替换**。这里没有引入 ``.bat`` 或额外的
小助手二进制，而是**让下载下来的那个新 exe 自己当助手**：

1. :func:`stage` 把新版下载到临时目录并校验 SHA256；
2. :func:`spawn_apply` 用**新版**启动一个助手进程，把「要替换谁」告诉它；
3. 主程序退出，文件锁随之释放；
4. 助手等文件解锁（失败就退避重试），原子替换，再把程序重新拉起来。

好处是替换者天然不是被替换者，不用跟 ``os.replace`` 抢锁；而且全过程没有
「脚本释放可执行文件」这种最容易触发杀软告警的行为。

## 安全上的取舍

下载并执行网络上的二进制是整个程序里攻击面最大的动作。因此：

- 只要上游给了 ``sha256`` 摘要（GitHub 现在会为发布附件提供），
  :func:`stage` **强制**校验，不匹配直接删除临时文件并报错，绝不落盘待用；
- 上游没给摘要时不假装安全，而是明确拒绝自动更新，退回「打开下载页」。

模块刻意不依赖 Qt：下载要跑在后台线程里，但替换逻辑本身是纯 IO，
放在这里才能脱离 ``QApplication`` 直接测试。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from .update import Asset, Release, UpdateError

__all__ = [
    "APPLY_FLAG",
    "DEFAULT_APPLY_TIMEOUT",
    "DEFAULT_DOWNLOAD_TIMEOUT",
    "DownloadCancelled",
    "Staged",
    "apply_update",
    "asset_name",
    "cleanup_stale",
    "download",
    "is_apply_request",
    "pick_asset",
    "relaunch",
    "run_apply",
    "sha256_file",
    "spawn_apply",
    "stage",
    "supports_self_update",
    "target_executable",
    "update_root",
]

#: 助手模式的命令行开关：``<新 exe> --apply-update <要替换的目标路径>``
APPLY_FLAG = "--apply-update"

#: 下载整体超时（秒）。45 MB 的产物在慢网络上要留足余量。
DEFAULT_DOWNLOAD_TIMEOUT = 180.0
#: 等目标文件解锁的最长时间（秒）
DEFAULT_APPLY_TIMEOUT = 90.0

#: 覆盖更新目录的环境变量（测试用，语义同 ``settings.ENV_OVERRIDE``）
ENV_OVERRIDE = "FRA_UPDATE_DIR"
#: 更新目录名
DIR_NAME = "File-Renaming-Assistant-update"
#: 发布附件名（由 CI 产出，见 .github/workflows/release.yml）
_ASSET_BY_PLATFORM = {
    "win32": "File-Renaming-Assistant.exe",
}

_USER_AGENT = "File-Renaming-Assistant-Updater"
_CHUNK = 256 * 1024


class DownloadCancelled(UpdateError):    # noqa: N818 (它不是故障，是用户主动中止)
    """用户在下载途中取消了。

    单独一类是为了让界面能安静收场：取消是用户自己的决定，
    不该再弹一个「下载失败」的框。名字因此不加 ``Error`` 后缀 ——
    加了反而误导，这里没有任何出错。
    """


def _cancelled(cancel: Callable[[], bool] | None) -> bool:
    return cancel is not None and cancel()


def _request(url: str, binary: bool = False) -> urllib.request.Request:
    headers = {"User-Agent": _USER_AGENT}
    headers["Accept"] = (
        "application/octet-stream" if binary else "application/vnd.github+json"
    )
    return urllib.request.Request(url, headers=headers)


# ------------------------------------------------------------------ 环境


def update_root() -> str:
    """返回更新临时目录（不保证存在）。

    放在系统临时目录而不是程序旁边：一是那里一定有写权限（程序可能装在
    ``Program Files`` 这类只读位置，新版落不进去），二是位置稳定、便于按年龄清理。

    代价是**临时目录往往和目标程序不在同一个卷上**（临时目录在 C 盘，
    程序可能在别的盘），而 ``os.replace`` 不能跨卷 —— 这一点由
    :func:`apply_update` 负责兜住：跨卷时先在目标旁边复制一份副本，
    再做同卷的原子改名。
    """
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return override
    return os.path.join(tempfile.gettempdir(), DIR_NAME)


def asset_name() -> str:
    """当前平台对应的发布附件名；没有约定则返回空串。"""
    return _ASSET_BY_PLATFORM.get(sys.platform, "")


def target_executable() -> str:
    """返回「该被替换的文件」——打包后就是程序自己那个 exe。"""
    return os.path.abspath(sys.executable)


def supports_self_update() -> bool:
    """当前是否能做就地更新。

    只在「被打包成可执行文件」且平台有对应附件时才为真。从源码直接运行时
    ``sys.executable`` 是 python 解释器，替换它毫无意义，也会毁掉用户的
    Python 环境 —— 这种场景一律退回手动下载。
    """
    if not getattr(sys, "frozen", False):
        return False
    if not asset_name():
        return False
    return os.path.isfile(target_executable())


def pick_asset(release: Release) -> Asset:
    """从发布里挑出当前平台要下载的附件。

    :raises UpdateError: 该发布没有当前平台的附件，或附件缺少 SHA256 摘要。
    """
    name = asset_name()
    if not name:
        raise UpdateError(f"当前平台（{sys.platform}）没有提供可执行文件附件。")

    found = release.asset(name)
    if found is None:
        raise UpdateError(f"发布 {release.version} 里没有找到附件 {name}。")

    if not found.sha256:
        # 没有摘要就无法确认下到的是不是原文件。这里宁可不让用户冒险，
        # 也不做「反正走 HTTPS 了」的自我安慰。
        raise UpdateError(
            f"附件 {name} 没有提供 SHA256 摘要，为安全起见不自动更新。\n"
            "请到发布页手动下载。"
        )
    return found


# ------------------------------------------------------------------ 下载与校验


def sha256_file(path: str) -> str:
    """计算文件的 SHA256（小写十六进制）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: str, expected: str) -> None:
    """校验文件摘要；不匹配就删掉它再报错。

    :raises UpdateError: 摘要不一致（下载被截断、被中间人替换、或上游算错）。
    """
    wanted = (expected or "").strip().lower()
    if not wanted:
        raise UpdateError("没有可用的 SHA256 摘要，无法校验下载内容。")

    actual = sha256_file(path)
    if actual != wanted:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise UpdateError(
            "下载的文件校验失败，已丢弃。\n"
            f"期望 {wanted[:16]}…，实际 {actual[:16]}…"
        )


def download(
    asset: Asset,
    dest: str,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
    cancel: Callable[[], bool] | None = None,
) -> str:
    """把附件下载到 ``dest``，返回落盘路径。

    先试发布页直链（``browser_download_url``），失败再退到接口地址并带上
    ``Accept: application/octet-stream``。两条链路落在不同的主机上，
    某些网络里只放行其中一条，多一次尝试能省掉一次「下载失败」。

    :param progress: 回调 ``(已下载字节, 总字节)``；总字节未知时给 0。
    :param cancel: 回调；返回真值即中止下载并抛 :class:`DownloadCancelled`。
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    errors: list[str] = []
    for url, binary in ((asset.url, False), (asset.api_url, True)):
        if not url:
            continue
        try:
            _download_one(url, binary, dest, asset.size, progress, timeout, cancel)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            errors.append(f"{url.split('/')[2]}：{exc}")
            continue
        return dest

    raise UpdateError("下载失败：\n" + "\n".join(errors or ["没有可用的下载地址"]))


def _download_one(
    url: str,
    binary: bool,
    dest: str,
    expected_size: int,
    progress: Callable[[int, int], None] | None,
    timeout: float,
    cancel: Callable[[], bool] | None = None,
) -> None:
    with urllib.request.urlopen(_request(url, binary), timeout=timeout) as resp:
        total = 0
        try:
            total = int(resp.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            total = 0
        total = total or expected_size

        done = 0
        try:
            with open(dest, "wb") as fh:
                while True:
                    if _cancelled(cancel):
                        raise DownloadCancelled("已取消下载。")
                    block = resp.read(_CHUNK)
                    if not block:
                        break
                    fh.write(block)
                    done += len(block)
                    if progress is not None:
                        progress(done, total)
        except DownloadCancelled:
            # 半截文件留在临时目录没有意义，而且可能被误当成「已经下好了」
            try:
                os.unlink(dest)
            except OSError:
                pass
            raise


# ------------------------------------------------------------------ 落盘与替换


@dataclass(frozen=True)
class Staged:
    """已经下载并校验通过、随时可以应用的新版本。"""

    path: str      #: 新版可执行文件的路径
    target: str    #: 它要替换掉的文件
    version: str   #: 版本标签，如 ``v2.1``
    size: int      #: 字节数


def stage(
    release: Release,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
    cancel: Callable[[], bool] | None = None,
) -> Staged:
    """下载并校验新版本，返回待应用的 :class:`Staged`。

    :raises UpdateError: 平台不支持、附件缺失 / 无摘要、下载失败或校验不通过。
    :raises DownloadCancelled: 用户在下载途中取消。
    """
    if not supports_self_update():
        raise UpdateError("当前运行方式不支持自动更新，请手动下载新版本。")

    asset = pick_asset(release)
    target = target_executable()
    # 每个版本一个子目录：既是天然的隔离，也让「上次残留」能被按年龄清掉
    folder = os.path.join(update_root(), release.version.strip() or "latest")
    dest = os.path.join(folder, asset.name)

    download(asset, dest, progress=progress, timeout=timeout, cancel=cancel)
    verify(dest, asset.sha256)
    return Staged(path=dest, target=target,
                  version=release.version, size=os.path.getsize(dest))


def _detached_flags() -> int:
    """让子进程脱离控制台，关掉父进程也能继续跑。"""
    if os.name != "nt":
        return 0
    return (getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def spawn_apply(staged: Staged) -> int:
    """用新版启动助手进程，返回它的 pid。

    助手就是刚下载的那个 exe 本身：它跑在临时目录里，不占用目标文件，
    因此可以安安稳稳地去替换。主程序应当在本函数返回后**尽快退出**，
    否则助手要一直等到文件解锁。
    """
    proc = subprocess.Popen(
        [staged.path, APPLY_FLAG, staged.target],
        cwd=os.path.dirname(staged.path) or None,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_detached_flags(),
    )
    return proc.pid


def _same_volume(first: str, second: str) -> bool:
    """两个路径是否在同一个卷上。

    ``os.replace`` 只在同卷时能用（对文件系统来说是一次改名）。跨卷时
    Windows 直接抛 ``WinError 17 系统无法将文件移到不同的磁盘驱动器``，
    且**退避重试再久也没用** —— 必须先老老实实复制一份过去。
    """
    return os.path.splitdrive(first)[0].lower() == os.path.splitdrive(second)[0].lower()


def _stage_next_to(source: str, target: str) -> str:
    """把 ``source`` 复制到 ``target`` 同目录下的临时文件，返回该路径。

    复制到目标所在目录，是为了接下来那一步 ``os.replace`` 能落在同一个卷上，
    从而保持原子性 —— 否则用户可能在「文件已被删、新文件还没到位」的瞬间
    断电或强杀进程，留下一个半截的程序。
    """
    directory = os.path.dirname(target) or "."
    fd, holder = tempfile.mkstemp(dir=directory, prefix=".fra-update-", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copyfile(source, holder)
    except OSError:
        _unlink(holder)
        raise
    return holder


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _replace_until(source: str, target: str, deadline: float) -> None:
    """把 ``source`` 改名覆盖到 ``target``；目标被占用时退避重试。

    重试本身就是「等旧进程退出」的判据：文件还被锁着说明它没退，
    解锁了自然就替换成功，不需要去查进程表（那还要处理 pid 复用）。
    """
    while True:
        try:
            os.replace(source, target)
        except OSError as exc:
            if time.monotonic() >= deadline:
                raise UpdateError(
                    f"无法替换 {target}：{exc}\n"
                    "文件可能仍被占用，或当前目录没有写入权限。"
                ) from exc
            time.sleep(0.5)
        else:
            return


def apply_update(
    target: str,
    source: str,
    timeout: float = DEFAULT_APPLY_TIMEOUT,
) -> None:
    """把 ``source`` 覆盖到 ``target``，目标被占用时退避重试。

    :raises UpdateError: 超过 ``timeout`` 仍无法替换（权限不足、进程没退……）。
    """
    target = os.path.abspath(target)
    source = os.path.abspath(source)
    deadline = time.monotonic() + timeout

    if _same_volume(source, target):
        _replace_until(source, target, deadline)
        return

    # 跨卷：先在目标旁边落一份副本，再同卷原子改名，最后删掉源文件。
    holder = _stage_next_to(source, target)
    try:
        _replace_until(holder, target, deadline)
    except UpdateError:
        _unlink(holder)
        raise
    _unlink(source)


def relaunch(target: str) -> int:
    """重新启动替换后的程序，返回新进程 pid。"""
    proc = subprocess.Popen(
        [target],
        cwd=os.path.dirname(target) or None,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_detached_flags(),
    )
    return proc.pid


def is_apply_request(argv: list[str]) -> bool:
    """``argv`` 是不是助手模式（``--apply-update <目标>``）。"""
    return APPLY_FLAG in argv


def run_apply(argv: list[str]) -> int:
    """助手模式的入口：替换目标文件并重新拉起。

    调用方（``app.main``）必须在创建 ``QApplication`` **之前**处理它 ——
    助手不需要界面，建了窗口反而会闪一下。

    :returns: 进程退出码。
    """
    index = argv.index(APPLY_FLAG)
    rest = argv[index + 1:]
    if not rest:
        print(f"{APPLY_FLAG} 需要给出要替换的目标路径", file=sys.stderr)
        return 2
    target = os.path.abspath(rest[0])
    source = target_executable()

    if os.path.abspath(target) == source:
        print("目标与自身相同，拒绝执行", file=sys.stderr)
        return 2

    try:
        apply_update(target, source)
    except UpdateError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        relaunch(target)
    except OSError as exc:
        # 文件已经换好了，只是没能自动打开 —— 让用户自己双击即可，
        # 这比回滚（把旧版再写回去）更不容易出错。
        print(f"已更新，但自动重启失败：{exc}", file=sys.stderr)
        return 0
    return 0


# ------------------------------------------------------------------ 清理


def cleanup_stale(max_age: float = 24 * 3600) -> int:
    """删掉过期的更新临时目录，返回清掉的数量。

    刻意按修改时间设一条年龄线：助手进程可能**正在**用着某个目录，
    把「刚刚创建的」一起清掉会把它连同正在替换的文件一起删了。
    """
    root = update_root()
    if not os.path.isdir(root):
        return 0

    removed = 0
    now = time.time()
    for name in os.listdir(root):
        path = os.path.join(root, name)
        try:
            if now - os.path.getmtime(path) < max_age:
                continue
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.unlink(path)
        except OSError:
            continue
        if not os.path.exists(path):
            removed += 1

    try:
        if not os.listdir(root):
            os.rmdir(root)
    except OSError:
        pass
    return removed
