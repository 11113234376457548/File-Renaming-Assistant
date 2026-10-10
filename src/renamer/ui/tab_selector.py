"""左侧彩色标签选择器。

原版 v4.0 用一个「4 列 × 2 行」的按钮网格充当标签栏，每个标签配一种强调色，
选中项的填充与描边取自该色。本模块用 :class:`QGridLayout` 复刻这一布局，
并与右侧的 :class:`QStackedWidget` 联动切换页面。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..theme import TAB_TINTS, Theme, is_dark_palette

__all__ = ["TabSelector"]

#: 每行标签数量（原版为 4 列）
COLUMNS = 4
#: 标签按钮高度
TAB_HEIGHT = 34


class TabSelector(QWidget):
    """4 列 × N 行的彩色标签选择器。

    通过 :meth:`addTab` 依次注册页面与标签，:meth:`setCurrentIndex` 切换。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TabSelector")

        self._pages: list[QWidget] = []
        self._btns: list[QPushButton] = []
        self._colors: list[str] = []
        self.current: int = 0
        self.stack: QStackedWidget | None = None
        self._theme: dict[str, str] = Theme.get("light")

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 8, 4, 0)
        root.setSpacing(0)

        self.btn_area = QWidget()
        self.btn_area.setObjectName("tabBtnArea")
        self._grid = QGridLayout(self.btn_area)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(6)
        root.addWidget(self.btn_area)

        self.sep = QFrame()
        self.sep.setObjectName("tabSep")
        self.sep.setFixedHeight(1)
        root.addSpacing(3)
        root.addWidget(self.sep)

    # ---------------------------------------------------------------- 主题

    def set_theme(self, theme: dict[str, str]) -> None:
        """更新配色并重绘所有标签。"""
        self._theme = theme
        self._restyle()

    def _restyle(self) -> None:
        # 按底色亮度判断明暗，而不是比对某个固定的色值 —— 后者每加一套皮肤
        # 都要再登记一次，漏登记时不会报错，只会让页签在深色皮肤上变成「白底白字」。
        dark = is_dark_palette(self._theme)
        for i, (btn, color) in enumerate(zip(self._btns, self._colors, strict=True)):
            tint_light, tint_dark = TAB_TINTS.get(color, ("#eef1f3", "#33404a"))
            tint = tint_dark if dark else tint_light
            # outline: none 必须显式写：标签按钮自带样式表，全局 QSS 的那条
            # outline 规则不会覆盖到它，点过之后会留下一圈虚线焦点框。
            if i == self.current:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        border: 2px solid {color};
                        background: {tint};
                        color: {color};
                        padding: 4px 8px; border-radius: 4px;
                        font-size: 13px; font-weight: bold;
                        outline: none;
                    }}""")
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        border: 1px solid {self._theme['border']};
                        background: {self._theme['tab_idle_bg']};
                        color: {self._theme['text_primary']};
                        padding: 5px 9px; border-radius: 4px;
                        font-size: 13px;
                        outline: none;
                    }}
                    QPushButton:hover {{
                        border-color: {color}; color: {color};
                    }}""")

    # ---------------------------------------------------------------- 页面

    def addTab(self, widget: QWidget, label: str, color: str) -> int:
        """注册一个页面并生成对应标签，返回其索引。"""
        idx = len(self._pages)
        btn = QPushButton(label.strip())
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(TAB_HEIGHT)
        btn.setSizePolicy(btn.sizePolicy().horizontalPolicy(),
                          btn.sizePolicy().verticalPolicy())
        btn.clicked.connect(lambda _=False, i=idx: self.setCurrentIndex(i))
        self._grid.addWidget(btn, idx // COLUMNS, idx % COLUMNS)

        self._pages.append(widget)
        self._btns.append(btn)
        self._colors.append(color)
        if self.stack is not None:
            self.stack.addWidget(widget)
        self._restyle()
        return idx

    def setCurrentIndex(self, index: int) -> bool:
        """切换到第 ``index`` 页。``index`` 非法或与当前页相同时不做处理。"""
        if 0 <= index < len(self._pages) and index != self.current:
            self.current = index
            self._restyle()
            if self.stack is not None:
                self.stack.setCurrentIndex(index)
            return True
        return False

    def currentIndex(self) -> int:
        return self.current

    def widget(self, index: int) -> QWidget:
        return self._pages[index]

    def count(self) -> int:
        return len(self._pages)
