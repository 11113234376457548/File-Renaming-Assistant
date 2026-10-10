"""应用入口：创建 ``QApplication`` 并显示主窗口。"""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import __app_name__, __app_name_en__, __version__
from .paths import resource_path
from .selfupdate import cleanup_stale, is_apply_request, run_apply
from .settings import get_skin
from .ui.main_window import MainWindow, fix_palette

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """启动 GUI，返回进程退出码。"""
    args = argv if argv is not None else sys.argv

    # 助手模式：更新时由**新版** exe 带着 ``--apply-update`` 启动，负责在旧
    # 进程退出后替换文件。它不需要界面 —— 而且必须在这一步就拦掉，
    # 否则会先闪一个空窗口出来。
    if is_apply_request(args):
        return run_apply(args)

    app = QApplication(args)
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_name_en__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__app_name_en__)

    icon = QIcon(resource_path("icon.png"))
    if not icon.isNull():
        app.setWindowIcon(icon)

    # 必须在建窗口之前钉住调色板，否则深色系统下弹窗可能黑底黑字。
    # 这里要按**上次保存的皮肤**来钉 —— 固定用 "light" 会让深色皮肤
    # 在启动的一瞬间闪一下白底。
    fix_palette(app, get_skin())

    # 顺手清掉上次更新留下的临时文件。按年龄线清扫，正在被助手用着的目录
    # 不会受影响（见 selfupdate.cleanup_stale）。
    cleanup_stale()

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
