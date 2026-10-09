"""配色与样式表。

色值全部取自原版 v4.0 界面的实际像素采样，因此与用户手上的截图保持一致：

======================  ==========  ========================================
用途                     色值        说明
======================  ==========  ========================================
窗口 / 侧栏底色           #f5f5f5     整体基调是浅灰，而非纯白
卡片 / 页签 / 按钮        #ffffff     需要“浮起”的元素才是白色
边框                     #d4d4d4     输入框、分组框、表格统一使用
表头                     #e5e5e5
正文                     #2c2c2c
次级文字 / 分组框标题      #6b6b6b
提示文字                 #a0a0a0
强调蓝（预览效果）         #5b8def
成功绿（执行修改）         #58aa82
======================  ==========  ========================================

另外需要特别说明：``QMessageBox`` / ``QDialog`` 属于独立顶层窗口，**不会继承
主窗口的样式表**。若只在主窗口 ``setStyleSheet``，在 Windows 深色模式下弹窗
会取用系统深色背景，而通用 ``QWidget`` 规则又给它强加了深色文字，最终表现为
“黑底黑字”。因此这里显式补齐了对话框规则。
"""

from __future__ import annotations

__all__ = ["Theme", "TAB_COLORS", "TAB_TINTS", "build_qss"]


class Theme:
    """浅色 / 深色两套配色。"""

    LIGHT: dict[str, str] = dict(
        # 底色层次
        bg_base="#f5f5f5",        # 窗口 / 侧栏
        bg_panel="#f5f5f5",       # 页面区
        bg_surface="#ffffff",     # 卡片、页签、按钮
        bg_elevated="#ffffff",
        bg_hover="#ececec",       # 浅灰底上的悬停
        bg_pressed="#dedede",
        bg_input="#f5f5f5",       # 输入控件：与底色平铺，只靠描边区分
        bg_spin="#ebebeb",        # 数字框右侧的微调按钮列（比输入区略深）
        # 边框
        border="#d4d4d4",
        border_light="#e0e0e0",
        border_focus="#5b8def",
        # 文字
        text_primary="#2c2c2c",
        text_secondary="#6b6b6b",
        text_muted="#a0a0a0",
        # 强调色
        accent="#5b8def",
        accent_hover="#4a7de0",
        accent_pressed="#3a6dd0",
        success="#58aa82",
        warning="#d4a843",
        error="#e05454",
        info="#42a5f5",
        # 表格
        table_header="#e5e5e5",
        table_bg="#ffffff",
        table_row_alt="#fafafa",
        table_grid="#e8e8e8",
        table_selection="#e0eaf5",
        # 页签
        tab_active_bg="#e0eaf5",
        tab_idle_bg="#ffffff",
        # 滚动条
        scrollbar_bg="#f0f0f0",
        scrollbar_handle="#c4c4c4",
        scrollbar_hover="#b4b4b4",
        separator="#e0e0e0",
        status_bg="#f5f5f5",
        status_text="#6b6b6b",
    )

    DARK: dict[str, str] = dict(
        bg_base="#202020",
        bg_panel="#202020",
        bg_surface="#2c2c2c",
        bg_elevated="#2c2c2c",
        bg_hover="#3a3a3a",
        bg_pressed="#464646",
        bg_input="#242424",
        bg_spin="#333333",
        border="#3d3d3d",
        border_light="#4a4a4a",
        border_focus="#5b8def",
        text_primary="#e6e6e6",
        text_secondary="#a6a6a6",
        text_muted="#787878",
        accent="#5b8def",
        accent_hover="#6d9bf2",
        accent_pressed="#4a7de0",
        success="#58aa82",
        warning="#d4a843",
        error="#e05454",
        info="#42a5f5",
        table_header="#333333",
        table_bg="#262626",
        table_row_alt="#2b2b2b",
        table_grid="#3a3a3a",
        table_selection="#2d3f5c",
        tab_active_bg="#2d3f5c",
        tab_idle_bg="#2c2c2c",
        scrollbar_bg="#2a2a2a",
        scrollbar_handle="#4a4a4a",
        scrollbar_hover="#5a5a5a",
        separator="#3a3a3a",
        status_bg="#202020",
        status_text="#a6a6a6",
    )

    @classmethod
    def get(cls, mode: str = "light") -> dict[str, str]:
        """返回配色副本；``mode='dark'`` 时返回深色。"""
        return dict(cls.DARK if mode == "dark" else cls.LIGHT)


#: 八个功能页的强调色（与原版 v4.0 一致）
TAB_COLORS: list[tuple[str, str]] = [
    ("序号", "#42a5f5"),
    ("添加", "#66bb6a"),
    ("删除", "#ef5350"),
    ("替换", "#ffa726"),
    ("转换", "#ab47bc"),
    ("扩展名", "#26c6da"),
    ("其他", "#78909c"),
    ("关于", "#78909c"),
]

#: 选中态页签的浅色填充（原版对每个颜色配了一档浅底）
TAB_TINTS: dict[str, tuple[str, str]] = {
    "#42a5f5": ("#e0eaf5", "#2b3a4d"),
    "#66bb6a": ("#e6f4e7", "#2b4030"),
    "#ef5350": ("#fdeaea", "#4d2b2b"),
    "#ffa726": ("#fff3e2", "#4d3a1f"),
    "#ab47bc": ("#f6e9f8", "#3f2b45"),
    "#26c6da": ("#e2f7fa", "#1f4249"),
    "#78909c": ("#eef1f3", "#33404a"),
}


def build_qss(t: dict[str, str], icon_dir: str = "") -> str:
    """根据配色 ``t`` 生成完整样式表。

    ``icon_dir`` 是**已经按该主题着色好**的位图目录，由
    :func:`renamer.icons.theme_icon_dir` 提供 —— QSS 的 ``image: url()``
    只能引用磁盘上的位图，无法直接吃内存里的 SVG。
    """
    d = icon_dir.replace("\\", "/")
    up = f"{d}/spin_plus.png"
    dn = f"{d}/spin_minus.png"
    chk_on = f"{d}/chk_checked.png"
    chk_off = f"{d}/chk_unchecked.png"
    arr = f"{d}/dropdown_arrow.png"

    return f"""
/* ============================ 全局 ============================ */
QMainWindow, QDialog, QMessageBox {{ background: {t['bg_base']}; }}
QWidget {{
    color: {t['text_primary']};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
                 "Segoe UI", "Noto Sans CJK SC", sans-serif;
    font-size: 13px;
}}

/* ============================ 左右分栏 ============================ */
/* 原版左栏是浅灰底、右栏是白底，两者靠一条边框线分隔 */
QFrame#sidePanel {{ background: {t['bg_base']}; border: none; }}
QFrame#filePanel {{ background: {t['bg_surface']}; border: none; }}

/* ============================ 菜单 ============================ */
QMenuBar {{
    background: {t['bg_base']};
    color: {t['text_primary']};
    font-size: 13px;
    padding: 2px 4px;
    border: none;
}}
QMenuBar::item {{ padding: 4px 12px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {t['bg_hover']}; }}
QMenuBar::item:pressed {{ background: {t['bg_pressed']}; }}
QMenu {{
    background: {t['bg_surface']};
    border: 1px solid {t['border']};
    border-radius: 4px; padding: 4px 0px;
}}
QMenu::item {{ padding: 5px 30px 5px 20px; background: transparent; }}
QMenu::item:selected {{ background: {t['bg_hover']}; }}
QMenu::separator {{ height: 1px; background: {t['separator']}; margin: 4px 8px; }}

/* ============================ 工具栏 ============================ */
QWidget#toolbarWidget {{
    background: {t['bg_base']};
    border-bottom: 1px solid {t['border']};
}}
QLabel#toolbarLabel {{ color: {t['text_primary']}; font-size: 13px; }}
QFrame#toolbarSep {{
    background: {t['border']}; max-width: 1px; border: none; margin: 10px 6px;
}}

/* ============================ 按钮 ============================ */
/* outline: none —— 去掉按钮获得焦点时 Qt 画的那个虚线方框。
   它在浅色底上像一圈「还没画完的边框」，用户会以为是样式错误。 */
QPushButton {{
    padding: 5px 14px; border-radius: 4px;
    border: 1px solid {t['border']};
    background: {t['bg_surface']};
    color: {t['text_primary']};
    font-size: 13px; min-height: 20px;
    outline: none;
}}
QPushButton:hover {{ background: {t['bg_hover']}; }}
QPushButton:pressed {{ background: {t['bg_pressed']}; }}
QPushButton:disabled {{ color: {t['text_muted']}; }}

QPushButton#tbBtn {{ padding: 2px 10px; min-height: 18px; }}

QPushButton#btnPreview {{
    background: {t['accent']}; color: #ffffff; border: 1px solid {t['accent']};
    font-weight: bold; padding: 2px 18px; border-radius: 5px;
}}
QPushButton#btnPreview:hover {{
    background: {t['accent_hover']}; border-color: {t['accent_hover']};
}}
QPushButton#btnPreview:pressed {{
    background: {t['accent_pressed']}; border-color: {t['accent_pressed']};
}}

QPushButton#btnExecute {{
    background: {t['success']}; color: #ffffff; border: 1px solid {t['success']};
    font-weight: bold; padding: 2px 18px; border-radius: 5px;
}}
QPushButton#btnExecute:hover {{ background: #4a9c76; border-color: #4a9c76; }}
QPushButton#btnExecute:pressed {{ background: #3e8a68; border-color: #3e8a68; }}

/* 输入框右侧的「格式预设」下拉按钮 */
QToolButton#fmtMore {{
    background: {t['bg_input']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 0px; margin-left: 10px;
    outline: none;
}}
QToolButton#fmtMore:hover {{ background: {t['bg_hover']}; }}
QToolButton#fmtMore::menu-indicator {{ image: none; width: 0px; }}

/* ============================ 页签选择器 ============================ */
TabSelector {{ background: {t['bg_base']}; }}
QFrame#tabSep {{ background: {t['border']}; max-height: 1px; border: none; }}

/* ============================ 分组框 ============================ */
QGroupBox {{
    border: 1px solid {t['border']};
    border-radius: 5px;
    margin-top: 9px;
    padding: 0px;
    color: {t['text_primary']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0px 4px;
    color: {t['text_secondary']};
    font-size: 13px;
    background: {t['bg_base']};
}}

/* ============================ 输入控件 ============================ */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    padding: 4px 8px;
    border: 1px solid {t['border']};
    border-radius: 4px;
    background: {t['bg_input']};
    color: {t['text_primary']};
    font-size: 13px; min-height: 22px;
    selection-background-color: {t['accent']};
    selection-color: #ffffff;
    outline: none;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {t['accent']};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    color: {t['text_muted']};
}}
QLineEdit[readOnly="true"] {{ color: {t['text_secondary']}; }}

QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border;
    width: 17px;
    background: {t['bg_spin']};
}}
/* 原版的数字框是「一个完整的圆角框 + 右侧一条灰底按钮列」。
   基座让出右边框与右侧圆角，改由两个按钮各自补齐，拼起来才是一条
   连续的轮廓线（否则中间会断、出现一个缺口）。 */
QSpinBox, QDoubleSpinBox {{
    border-right: none;
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
}}
QAbstractSpinBox::up-button {{
    subcontrol-position: top right;
    border: 1px solid {t['border']};
    border-bottom: 1px solid {t['border']};
    border-top-right-radius: 4px;
}}
QAbstractSpinBox::down-button {{
    subcontrol-position: bottom right;
    border-left: 1px solid {t['border']};
    border-right: 1px solid {t['border']};
    border-bottom: 1px solid {t['border']};
    border-bottom-right-radius: 4px;
}}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
    background: {t['bg_hover']};
}}
QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed {{
    background: {t['bg_pressed']};
}}
QAbstractSpinBox::up-arrow {{ image: url({up}); width: 14px; height: 14px; }}
QAbstractSpinBox::down-arrow {{ image: url({dn}); width: 14px; height: 14px; }}

/* 无微调按钮的数字框（原版「位数」就是这种样式）。
   注意不能用 setButtonSymbols(NoButtons)：那会与样式表冲突导致文字不绘制，
   必须在样式表里把按钮宽度压成 0；边框则要补回上面被让出的右边。 */
QSpinBox#plainSpin {{
    border: 1px solid {t['border']};
    border-radius: 4px;
}}
QSpinBox#plainSpin::up-button, QSpinBox#plainSpin::down-button {{
    width: 0px; border: none; background: transparent;
}}
QSpinBox#plainSpin::up-arrow, QSpinBox#plainSpin::down-arrow {{
    image: none; width: 0px; height: 0px;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 22px; border: none; background: transparent;
}}
QComboBox::down-arrow {{ image: url({arr}); width: 11px; height: 11px; }}
QComboBox QAbstractItemView {{
    background: {t['bg_surface']};
    border: 1px solid {t['border']};
    outline: none; padding: 2px;
    selection-background-color: {t['bg_hover']};
    selection-color: {t['text_primary']};
}}

/* ============================ 表格 ============================ */
QTableWidget {{
    background: {t['table_bg']};
    alternate-background-color: {t['table_row_alt']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    gridline-color: {t['table_grid']};
    selection-background-color: {t['table_selection']};
    selection-color: {t['text_primary']};
    outline: none;
}}
QTableWidget::item {{ padding: 3px 6px; border: none; outline: none; }}
QTableWidget::item:selected {{ background: {t['table_selection']}; }}
QHeaderView {{ background: {t['table_header']}; outline: none; }}
QHeaderView::section {{
    background: {t['table_header']};
    color: {t['text_secondary']};
    border: none;
    border-right: 1px solid {t['border']};
    padding: 6px 4px;
}}
QTableCornerButton::section {{
    background: {t['table_header']};
    border: none;
    border-right: 1px solid {t['border']};
}}
QLabel#fileListCount {{ color: {t['text_primary']}; font-weight: bold; }}
QLabel#dragHint {{ color: {t['text_muted']}; font-size: 12px; }}

/* ============================ 复选框 ============================ */
QCheckBox {{ color: {t['text_primary']}; spacing: 6px; outline: none; }}
QCheckBox::indicator, QTableWidget::indicator {{
    width: 15px; height: 15px; image: url({chk_off});
}}
QCheckBox::indicator:checked, QTableWidget::indicator:checked {{
    image: url({chk_on});
}}
QRadioButton {{ color: {t['text_primary']}; spacing: 6px; outline: none; }}
QRadioButton::indicator {{
    width: 15px; height: 15px; border-radius: 8px;
    border: 1px solid {t['border']}; background: {t['bg_surface']};
}}
QRadioButton::indicator:checked {{
    background: {t['accent']}; border: 4px solid {t['bg_surface']};
    outline: 1px solid {t['accent']};
}}

/* ============================ 滚动条 ============================ */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 0; border: none;
}}
QScrollBar::handle:vertical {{
    background: {t['scrollbar_handle']}; min-height: 30px;
    border-radius: 5px; margin: 1px;
}}
QScrollBar::handle:vertical:hover {{ background: {t['scrollbar_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 0; border: none;
}}
QScrollBar::handle:horizontal {{
    background: {t['scrollbar_handle']}; min-width: 30px;
    border-radius: 5px; margin: 1px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t['scrollbar_hover']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

/* ============================ 其它 ============================ */
QLabel#hint {{ color: {t['text_muted']}; font-size: 12px; }}
QLabel#aboutTitle {{ font-size: 17px; font-weight: bold; color: {t['text_primary']}; }}
QLabel#aboutSubtitle {{ font-size: 13px; color: {t['text_secondary']}; }}
QLabel#aboutInfo {{ font-size: 13px; color: {t['text_secondary']}; }}
QStatusBar {{
    background: {t['status_bg']};
    color: {t['status_text']};
    border-top: 1px solid {t['separator']};
    font-size: 12px;
}}
QStatusBar::item {{ border: none; }}
QToolTip {{
    background: {t['bg_surface']}; color: {t['text_primary']};
    border: 1px solid {t['border']}; padding: 4px 6px;
}}

/* ============================ 对话框 ============================ */
QMessageBox, QDialog {{ background: {t['bg_base']}; }}
QMessageBox QLabel, QDialog QLabel {{
    color: {t['text_primary']}; background: transparent;
}}
QMessageBox QPushButton, QDialog QPushButton {{
    background: {t['bg_surface']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 5px 18px; min-width: 64px; min-height: 22px;
}}
QMessageBox QPushButton:hover, QDialog QPushButton:hover {{
    background: {t['bg_hover']};
}}
QMessageBox QPushButton:default, QDialog QPushButton:default {{
    background: {t['accent']}; color: #ffffff;
    border: 1px solid {t['accent']};
}}
QMessageBox QPushButton:default:hover, QDialog QPushButton:default:hover {{
    background: {t['accent_hover']};
}}
"""
