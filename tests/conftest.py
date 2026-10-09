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

from renamer.core import DEFAULT_SETTINGS  # noqa: E402


@pytest.fixture()
def make_settings():
    """返回一个工厂函数：``make_settings(**overrides)`` 生成完整设置字典。"""

    def _factory(**overrides: Any) -> dict[str, Any]:
        settings = dict(DEFAULT_SETTINGS)
        settings.update(overrides)
        return settings

    return _factory
