"""应用入口：创建 ``QApplication`` 并显示主窗口。"""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import __app_name__, __app_name_en__, __version__
from .paths import resource_path
from .ui.main_window import MainWindow, fix_palette

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """启动 GUI，返回进程退出码。"""
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_name_en__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__app_name_en__)

    icon = QIcon(resource_path("icon.png"))
    if not icon.isNull():
        app.setWindowIcon(icon)

    # 必须在建窗口之前钉住调色板，否则深色系统下弹窗可能黑底黑字
    fix_palette(app, "light")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
