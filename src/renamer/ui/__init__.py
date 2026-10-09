"""界面组件。"""

from __future__ import annotations

__all__ = ["TabSelector", "MainWindow"]


def __getattr__(name: str):
    # 延迟导入，避免仅使用子模块时也要拉起整个 Qt 依赖链
    if name == "TabSelector":
        from .tab_selector import TabSelector
        return TabSelector
    if name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    raise AttributeError(name)
