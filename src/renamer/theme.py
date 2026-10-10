"""配色与样式表。

项目内置多套「皮肤」，每一套都是 :class:`Theme` 里一个**键完全相同**的色值
字典，由 :func:`build_qss` 铺成完整样式表。下面这张表是 ``LIGHT``（经典浅色）
的取值，也是其余皮肤的对照基准：

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

__all__ = ["Theme", "TAB_COLORS", "TAB_TINTS", "build_qss", "is_dark_palette"]


def _luminance(hex_color: str) -> float:
    """返回 ``#rrggbb`` 的相对亮度（0=黑，1=白），用 sRGB 转线性后的加权和。"""
    value = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        raw = int(value[i:i + 2], 16) / 255.0
        channels.append(raw / 12.92 if raw <= 0.04045
                        else ((raw + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def is_dark_palette(t: dict[str, str]) -> bool:
    """按底色亮度判断这套配色是深色还是浅色。

    不用「颜色 == Theme.DARK 的某个值」这类比较来判断 —— 那种写法每加一套
    皮肤就得再登记一次，漏登记时不会报错，只会让页签在深色皮肤上用浅色底，
    白底白字。按亮度算则是自洽的：新皮肤不需要做任何额外声明。
    """
    return _luminance(t["bg_base"]) < 0.5


class Theme:
    """内置皮肤（调色板）注册表。

    每套皮肤都是一个**键完全相同**的色值字典，因此 :func:`build_qss` 与
    :func:`renamer.icons.theme_icon_dir` 对任何一套都能直接工作，不需要分支。
    色键集合由 ``tests/test_theme.py`` 钉死，新增皮肤时若漏键会立刻测出来。
    """

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
        success_hover="#4a9c76",
        success_pressed="#3e8a68",
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
        success_hover="#6cbd95",
        success_pressed="#4a9c76",
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

    #: 护眼绿 —— 底色带一点豆沙绿，长时间盯着不刺眼。
    #: 仍沿用原版那条规矩：输入框与底色同为 ``bg_base``，只靠描边区分。
    EYE: dict[str, str] = dict(
        bg_base="#e8f0e0",
        bg_panel="#e8f0e0",
        bg_surface="#f7faf3",
        bg_elevated="#ffffff",
        bg_hover="#dde9d3",
        bg_pressed="#d0e0c4",
        bg_input="#e8f0e0",
        bg_spin="#dce7d2",
        border="#b5c9a8",
        border_light="#c9d8bf",
        border_focus="#2f7d49",
        text_primary="#26311f",
        text_secondary="#5b6b52",
        text_muted="#8b9a83",
        accent="#2f7d49",
        accent_hover="#276a3d",
        accent_pressed="#1f5732",
        success="#2f7d49",
        success_hover="#276a3d",
        success_pressed="#1f5732",
        warning="#9a7412",
        error="#b23c3c",
        info="#2f6f95",
        table_header="#dce7d2",
        table_bg="#f7faf3",
        table_row_alt="#f0f5ea",
        table_grid="#dbe5d3",
        table_selection="#cfe0c2",
        tab_active_bg="#cfe0c2",
        tab_idle_bg="#f7faf3",
        scrollbar_bg="#e0eadd",
        scrollbar_handle="#9db28f",
        scrollbar_hover="#8aa07c",
        separator="#cfe0c6",
        status_bg="#e8f0e0",
        status_text="#5b6b52",
    )

    #: 暖沙 —— 米黄纸感底色 + 陶土红强调色，偏「纸质文档」的观感。
    SAND: dict[str, str] = dict(
        bg_base="#f2ece1",
        bg_panel="#f2ece1",
        bg_surface="#fffaf2",
        bg_elevated="#ffffff",
        bg_hover="#e8e0d2",
        bg_pressed="#dcd2c1",
        bg_input="#f2ece1",
        bg_spin="#e8e0d2",
        border="#d3c6b1",
        border_light="#e0d6c6",
        border_focus="#b4532a",
        text_primary="#3a3128",
        text_secondary="#6f6355",
        text_muted="#9c9083",
        accent="#b4532a",
        accent_hover="#9d4723",
        accent_pressed="#863c1d",
        success="#5f8a3f",
        success_hover="#527a35",
        success_pressed="#456a2c",
        warning="#a8821f",
        error="#b8503f",
        info="#3f7796",
        table_header="#e8e0d2",
        table_bg="#fffaf2",
        table_row_alt="#f8f3ea",
        table_grid="#e6dccd",
        table_selection="#f0e2ce",
        tab_active_bg="#f0e2ce",
        tab_idle_bg="#fffaf2",
        scrollbar_bg="#ebe3d6",
        scrollbar_handle="#b8a88f",
        scrollbar_hover="#a3937a",
        separator="#ded3c2",
        status_bg="#f2ece1",
        status_text="#6f6355",
    )

    #: 暗夜蓝 —— 深色但不是纯灰，底色偏靛蓝，夜里看比 DEFAULT_DARK 柔和。
    MIDNIGHT: dict[str, str] = dict(
        bg_base="#161b26",
        bg_panel="#161b26",
        bg_surface="#1e2534",
        bg_elevated="#1e2534",
        bg_hover="#2a3346",
        bg_pressed="#354159",
        bg_input="#1a2030",
        bg_spin="#252d3f",
        border="#2f3a4f",
        border_light="#3c4a63",
        border_focus="#5b8def",
        text_primary="#dce4f2",
        text_secondary="#93a1bb",
        text_muted="#68758d",
        accent="#5b8def",
        accent_hover="#6d9bf2",
        accent_pressed="#4a7de0",
        success="#4fae86",
        success_hover="#5cbf95",
        success_pressed="#439a75",
        warning="#d4a843",
        error="#e06060",
        info="#4aa8f0",
        table_header="#242c3d",
        table_bg="#1b2231",
        table_row_alt="#1f2735",
        table_grid="#2c3648",
        table_selection="#2b3f63",
        tab_active_bg="#2b3f63",
        tab_idle_bg="#1e2534",
        scrollbar_bg="#1d2432",
        scrollbar_handle="#3a4661",
        scrollbar_hover="#48566f",
        separator="#2b3446",
        status_bg="#161b26",
        status_text="#93a1bb",
    )

    #: 高对比 —— 纯黑白 + 全黑描边，给视力不佳或强光环境用。
    #: 边框刻意压到 ``#000000``，弱化一切「装饰性」的灰阶。
    CONTRAST: dict[str, str] = dict(
        bg_base="#ffffff",
        bg_panel="#ffffff",
        bg_surface="#ffffff",
        bg_elevated="#ffffff",
        bg_hover="#e6e6e6",
        bg_pressed="#cccccc",
        bg_input="#ffffff",
        bg_spin="#e0e0e0",
        border="#000000",
        border_light="#4d4d4d",
        border_focus="#0000cc",
        text_primary="#000000",
        text_secondary="#1a1a1a",
        text_muted="#4d4d4d",
        accent="#0000cc",
        accent_hover="#0000a3",
        accent_pressed="#000080",
        success="#006600",
        success_hover="#005500",
        success_pressed="#004400",
        warning="#8a5a00",
        error="#c00000",
        info="#00557f",
        table_header="#e6e6e6",
        table_bg="#ffffff",
        table_row_alt="#f2f2f2",
        table_grid="#000000",
        table_selection="#cfe0ff",
        tab_active_bg="#cfe0ff",
        tab_idle_bg="#ffffff",
        scrollbar_bg="#e6e6e6",
        scrollbar_handle="#5a5a5a",
        scrollbar_hover="#303030",
        separator="#000000",
        status_bg="#ffffff",
        status_text="#1a1a1a",
    )

    #: 皮肤注册表。键就是写进 ``settings.json`` 的名字，**改名等于让老配置失效**
    #: （读不出来会静默回退默认皮肤），要改就得同时写迁移逻辑。
    SKINS: dict[str, dict[str, str]] = {
        "light": LIGHT,
        "dark": DARK,
        "eye": EYE,
        "sand": SAND,
        "midnight": MIDNIGHT,
        "contrast": CONTRAST,
    }

    #: 菜单里的显示名
    NAMES: dict[str, str] = {
        "light": "经典浅色",
        "dark": "经典深色",
        "eye": "护眼绿",
        "sand": "暖沙",
        "midnight": "暗夜蓝",
        "contrast": "高对比",
    }

    #: 「视图 → 皮肤」菜单里的排列顺序：浅色系在前，深色系在后
    ORDER: list[str] = ["light", "eye", "sand", "dark", "midnight", "contrast"]

    #: 默认皮肤
    DEFAULT: str = "light"

    #: Ctrl+D 快速切换的一对皮肤
    TOGGLE_PAIR: tuple[str, str] = ("light", "dark")

    @classmethod
    def keys(cls) -> list[str]:
        """按菜单顺序返回全部皮肤键。"""
        return list(cls.ORDER)

    @classmethod
    def has(cls, key: str) -> bool:
        """``key`` 是否是一套已登记的皮肤。"""
        return key in cls.SKINS

    @classmethod
    def get(cls, key: str = DEFAULT) -> dict[str, str]:
        """返回配色副本；未知键回退到默认皮肤。"""
        return dict(cls.SKINS.get(key) or cls.SKINS[cls.DEFAULT])

    @classmethod
    def name(cls, key: str) -> str:
        """返回皮肤显示名；未知键回退到默认皮肤的名字。"""
        return cls.NAMES.get(key) or cls.NAMES[cls.DEFAULT]

    @classmethod
    def is_dark(cls, key: str) -> bool:
        """这套皮肤是不是深色系。"""
        return is_dark_palette(cls.get(key))


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
QPushButton#btnExecute:hover {{
    background: {t['success_hover']}; border-color: {t['success_hover']};
}}
QPushButton#btnExecute:pressed {{
    background: {t['success_pressed']}; border-color: {t['success_pressed']};
}}

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
    /* 必须显式指定：不给的话 Qt 会拿 color 做三分之一透明来推导占位文字色，
       深色皮肤上只剩约 2.5:1，输入框里那句提示基本看不清。
       注意**调色板里的 PlaceholderText 角色在这里是无效的** —— 只要控件带了
       样式表、且样式表里写了 color，QStyleSheetStyle 就会盖掉那个角色，
       实测验证过；唯一管用的是这条 QSS 属性。 */
    placeholder-text-color: {t['text_muted']};
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
