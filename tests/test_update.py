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
    """仓库还没发过 Release 时 GitHub 返回 404，这不是错误。"""
    def raise_404(*_a, **_k):
        raise urllib.error.HTTPError(update.API_LATEST, 404, "Not Found",
                                     None, None)

    monkeypatch.setattr(update.urllib.request, "urlopen", raise_404)
    assert update.check_latest() is None


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
    assert update.GITHUB_REPO in update.RELEASES_PAGE
