"""检查更新。

只依赖标准库：为了「看一眼有没有新版本」而引入第三方 HTTP 库并不划算，
``urllib`` 足够，也少一个需要跟进的供应链依赖。

版本比较刻意写得宽容 —— 仓库里的标签可能写作 ``v1.1``、``1.1`` 甚至
``v1.1.0-beta.1``，一律按「逐段取数字前缀」解析，非数字后缀直接忽略，
避免因为标签格式不统一把「有新版」误判成「已是最新」。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

__all__ = [
    "GITHUB_REPO",
    "RELEASES_PAGE",
    "Release",
    "UpdateError",
    "check_latest",
    "is_newer",
    "parse_version",
]

#: 仓库坐标。**fork 后请改成自己的**
#: ``<用户名>/<仓库名>``，否则「检查更新」会去查上游仓库。
GITHUB_REPO = "11113234376457548/File-Renaming-Assistant"
#: GitHub 的「最新正式发布」接口
API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
#: 兜底跳转地址（接口拿不到链接时用）
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"

#: 单次请求超时（秒）
TIMEOUT = 8
#: GitHub 接口要求带 User-Agent
_USER_AGENT = "File-Renaming-Assistant-Updater"

_NUM = re.compile(r"(\d+)")


class UpdateError(Exception):
    """检查更新失败（网络不通、仓库不存在、返回内容异常……）。"""


@dataclass(frozen=True)
class Release:
    """一条发布信息。"""

    version: str          #: 标签，如 ``v1.1``
    url: str              #: 发布页地址
    name: str             #: 发布标题
    notes: str            #: 发布说明（Markdown 原文）


def parse_version(text: str) -> tuple[int, int, int]:
    """把版本字符串解析成可比较的三元组。

    >>> parse_version("v1.1.1")
    (1, 1, 1)
    >>> parse_version("1.1")
    (1, 1, 0)
    """
    parts: list[int] = []
    for chunk in str(text).strip().lstrip("vV").split("."):
        match = _NUM.match(chunk.strip())
        parts.append(int(match.group(1)) if match else 0)
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def is_newer(latest: str, current: str) -> bool:
    """``latest`` 是否比 ``current`` 新。"""
    return parse_version(latest) > parse_version(current)


def check_latest(timeout: float = TIMEOUT) -> Release | None:
    """查询最新一次正式发布。

    :returns: :class:`Release`；仓库尚无任何发布时返回 ``None``。
    :raises UpdateError: 网络不可达、仓库不存在或响应无法解析。
    """
    request = urllib.request.Request(
        API_LATEST,
        headers={"User-Agent": _USER_AGENT,
                 "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # 404 有两种可能：仓库不存在，或仓库还没发过 Release
            return None
        raise UpdateError(f"更新服务器返回 HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateError(f"无法连接更新服务器（{exc}）") from exc

    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        return None
    return Release(
        version=tag,
        url=str(payload.get("html_url") or RELEASES_PAGE),
        name=str(payload.get("name") or tag),
        notes=str(payload.get("body") or ""),
    )
