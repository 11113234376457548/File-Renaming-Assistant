"""用户配置持久化。

目前只存「上次选的皮肤」，但仍然单开一个模块，原因是读取时机很特殊：
``app.py`` 必须在**构造主窗口之前**就知道该用哪套皮肤，好先把应用程序调色板
钉死（否则深色皮肤启动瞬间会闪一下浅色底）。这个动作发生在任何界面对象
存在之前，所以它不能挂在 ``MainWindow`` 上。

刻意**不依赖 Qt**：一是可以脱离 ``QApplication`` 单独测试，二是配置读写这种
纯 IO 不该把 Qt 的事件循环拖进来。

文件位置（可用环境变量 ``FRA_CONFIG_DIR`` 覆盖，测试靠它隔离）::

    Windows   %APPDATA%/File-Renaming-Assistant/settings.json
    macOS     ~/Library/Application Support/File-Renaming-Assistant/settings.json
    Linux     $XDG_CONFIG_HOME/File-Renaming-Assistant/settings.json
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import Any

from .theme import Theme

__all__ = [
    "config_dir",
    "get_skin",
    "load",
    "save",
    "set_skin",
    "set_value",
    "settings_path",
    "value",
]

#: 配置目录名（用英文名，避免中文路径在部分工具链下的编码问题）
APP_DIR_NAME = "File-Renaming-Assistant"
SETTINGS_FILENAME = "settings.json"
#: 覆盖配置目录的环境变量（测试用）
ENV_OVERRIDE = "FRA_CONFIG_DIR"

#: 各项配置的默认值
DEFAULTS: dict[str, Any] = {"skin": Theme.DEFAULT}


def config_dir() -> str:
    """返回配置目录（不保证已存在）。"""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return override

    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP_DIR_NAME)


def settings_path() -> str:
    """返回配置文件绝对路径。"""
    return os.path.join(config_dir(), SETTINGS_FILENAME)


def load() -> dict[str, Any]:
    """读取全部配置。

    文件不存在、不是合法 JSON、或顶层不是对象时一律返回空字典 —— 配置坏了
    不该让程序起不来，调用方各自回退到 :data:`DEFAULTS` 即可。
    """
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict[str, Any]) -> None:
    """写入全部配置。

    **原子写入**：先写同目录下的临时文件再 ``os.replace`` 顶替。直接覆写原文件
    的话，写到一半断电／被杀进程会留下一个残缺的 JSON，下次启动整份配置作废。

    写入失败只吞掉异常：配置存不下来是件小事，不该让它弹窗或崩溃。
    """
    path = settings_path()
    tmp = ""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(path), prefix=".settings-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def value(key: str, default: Any = None) -> Any:
    """读取单个配置项；缺失时回退到 ``DEFAULTS``，再回退到 ``default``。"""
    fallback = DEFAULTS.get(key, default)
    return load().get(key, fallback)


def set_value(key: str, val: Any) -> None:
    """写入单个配置项（保留其余项）。"""
    data = load()
    data[key] = val
    save(data)


def get_skin() -> str:
    """返回已保存的皮肤名。

    存储内容不合法（被手改过、或来自删掉了某套皮肤的旧版本）时回退到默认皮肤，
    而不是抛异常或返回一个 ``Theme.get`` 认不出的字符串。
    """
    key = value("skin", Theme.DEFAULT)
    return key if isinstance(key, str) and Theme.has(key) else Theme.DEFAULT


def set_skin(key: str) -> None:
    """保存皮肤名；非法值直接忽略。"""
    if isinstance(key, str) and Theme.has(key):
        set_value("skin", key)
