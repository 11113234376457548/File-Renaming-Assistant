"""资源定位工具。

同时兼容两种运行方式：

* **源码运行** —— 资源位于 ``src/renamer/resources/``
* **PyInstaller 打包** —— 资源被解包到 ``sys._MEIPASS`` 下
"""

from __future__ import annotations

import os
import sys

__all__ = ["resource_path"]

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts: str) -> str:
    """返回资源的绝对路径。

    依次尝试 ``_MEIPASS`` 下的多种布局，最后回退到源码目录。
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "renamer", "resources", *parts))
        candidates.append(os.path.join(meipass, "resources", *parts))
    candidates.append(os.path.join(_PKG_DIR, "resources", *parts))

    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[-1]
