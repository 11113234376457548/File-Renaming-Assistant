"""pytest 公共配置：把 ``src`` 加入导入路径，并提供设置工厂 fixture。"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from renamer import settings  # noqa: E402
from renamer.core import DEFAULT_SETTINGS  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_user_config(tmp_path):
    """把用户配置目录指到临时目录。

    自动生效（``autouse``），因为只要有一个测试碰到「切换皮肤」，就会写
    ``%APPDATA%/File-Renaming-Assistant/settings.json``，把开发机上的真实
    配置改掉 —— 而且这种污染不会让任何测试变红，下次手工启动才发现皮肤变了。
    与其逐个测试去记着隔离，不如在这里一次性堵死。

    **刻意不用 ``monkeypatch.setenv``**：测试内部一旦有人喊 ``monkeypatch.undo()``
    （想手动「恢复现场」），会把 fixture 设的隔离一并撤掉，之后读到的就是开发机
    上的真实配置 —— 实测踩过这个坑。改用裸 ``os.environ`` 加自己的 finally 收尾，
    别人既撤不掉、也不会被误撤。
    """
    key = settings.ENV_OVERRIDE
    missing = object()
    previous = os.environ.get(key, missing)
    os.environ[key] = str(tmp_path / "config")
    try:
        yield
    finally:
        if previous is missing:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


@pytest.fixture()
def make_settings():
    """返回一个工厂函数：``make_settings(**overrides)`` 生成完整设置字典。"""

    def _factory(**overrides: Any) -> dict[str, Any]:
        settings = dict(DEFAULT_SETTINGS)
        settings.update(overrides)
        return settings

    return _factory
