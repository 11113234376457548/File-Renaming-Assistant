"""主窗口：工具栏 + 左侧彩色标签页 + 右侧文件列表。

布局按原版 v4.0 的实际像素还原：页签为 4 列 × 2 行网格，文件表格为
「复选框 / 原文件名 / 新文件名 / 扩展名 / 状态」五列，「全选 / 可拖动」
位于表格下方。
"""

from __future__ import annotations

import os
import threading
from functools import partial

from PySide6.QtCore import QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPalette,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStackedWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__, __app_name_en__, __version__
from ..core import (
    STATUS_CONFLICT,
    STATUS_OVER,
    STATUS_RENAME,
    STATUS_SAME,
    STATUS_TAKEN,
    RenameEngine,
    apply_rename,
    natural_sort_key,
    normalize_ext,
    plan_rename,
    undo,
)
from ..icons import (
    ICON_ABOUT,
    ICON_ADD_FILES,
    ICON_BROWSE,
    ICON_CHECK_ALL,
    ICON_CLEAR,
    ICON_EXECUTE,
    ICON_MORE,
    ICON_PALETTE,
    ICON_PREVIEW,
    ICON_REFRESH,
    ICON_THEME,
    ICON_UNCHECK_ALL,
    ICON_UNDO,
    ICON_UPDATE,
    icon,
    theme_icon_dir,
)
from ..paths import resource_path
from ..selfupdate import (
    DownloadCancelled,
    Staged,
    pick_asset,
    spawn_apply,
    stage,
    supports_self_update,
)
from ..settings import get_skin, set_skin
from ..theme import TAB_COLORS, Theme, build_qss
from ..update import RELEASES_PAGE, Release, UpdateError, check_latest, is_newer
from .file_table import (
    COL_CHK,
    COL_EXT,
    COL_NEW,
    COL_ORIG,
    COL_STATUS,
    FileTable,
    NoFocusDelegate,
)
from .tab_selector import TabSelector

__all__ = ["MainWindow", "fix_palette"]

#: 左侧面板宽度、工具栏高度（按截图换算到逻辑像素）
SIDE_WIDTH = 397
TOOLBAR_HEIGHT = 42
#: 表格行高
ROW_HEIGHT = 24
#: 工具栏按钮上的 Lucide 图标尺寸
TOOL_ICON_SIZE = 14
#: 是否在工具栏按钮上显示图标。
#: 原版截图里工具栏只有文字，若需要严格对齐截图，把它改成 False 即可。
SHOW_TOOLBAR_ICONS = True

# 列号常量在 file_table 里定义，这里沿用导入的名字（向后兼容旧引用）

#: 预览状态 -> 主题色键
STATUS_COLORS = {
    STATUS_RENAME: "text_primary",
    STATUS_SAME: "text_muted",
    STATUS_OVER: "warning",
    STATUS_CONFLICT: "error",
    STATUS_TAKEN: "error",
    "已完成": "success",
    "失败": "error",
}

FOLDER_PLACEHOLDER = "选择文件夹，或拖拽文件到右侧列表..."
DRAG_HINT = "拖拽文件/文件夹到此"

#: 「格式」下拉里的预设模板（只列模板本身，``#`` 会被替换成序号）
FORMAT_PRESETS = [
    "#_[原文件名]",
    "#-[原文件名]",
    "#[原文件名]",
    "#",
]


def fix_palette(app: QApplication, mode: str = "light") -> None:
    """应用级调色板兜底。

    ``QMessageBox`` 等独立顶层窗口不继承主窗口样式表；在 Windows 深色模式下
    会取系统深色背景，而通用 ``QWidget`` 规则又强加了深色文字，形成黑底黑字。
    这里把调色板显式钉死，保证即便样式表未命中也能看清。

    注意：输入框的**占位提示色不归这里管**。实测只要控件带了样式表、且样式表里
    写了 ``color``，``QStyleSheetStyle`` 就会盖掉 ``PlaceholderText`` 角色，
    所以在 ``theme.build_qss`` 里用 ``placeholder-text-color`` 属性解决。
    """
    t = Theme.get(mode)
    pal = app.palette()
    roles = {
        QPalette.ColorRole.Window: t["bg_base"],
        QPalette.ColorRole.WindowText: t["text_primary"],
        QPalette.ColorRole.Base: t["bg_surface"],
        QPalette.ColorRole.AlternateBase: t["table_row_alt"],
        QPalette.ColorRole.Text: t["text_primary"],
        QPalette.ColorRole.Button: t["bg_surface"],
        QPalette.ColorRole.ButtonText: t["text_primary"],
        QPalette.ColorRole.Highlight: t["accent"],
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: t["bg_surface"],
        QPalette.ColorRole.ToolTipText: t["text_primary"],
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    app.setPalette(pal)


#: 弹窗最小宽度。Qt 会按文字长度自适应，中文短句常被挤成一条窄缝，
#: 看上去像个残缺的小窗；给一个下限让所有提示框宽度一致、也更好读。
DIALOG_MIN_WIDTH = 460


def _message_box(parent, icon, title: str, text: str,
                 buttons=QMessageBox.StandardButton.Ok) -> QMessageBox:
    """构造一个宽度受控的消息框。

    ``QMessageBox.information()`` 这类静态方法没法调整尺寸，所以统一改用
    实例方式构造。注意 **``setMinimumWidth()`` 是无效的**——``QMessageBox``
    显示时会按自己的布局重新定尺寸，直接无视最小宽度（实测 460 会被压回 258）。
    真正管用的做法是往布局里塞一个固定宽度的弹簧，把布局的最小宽度顶上去。
    """
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)

    # Qt 自带的按钮文案是英文（Yes / No / OK），在一水儿中文的界面里很扎眼。
    # 项目没有引入 .qm 翻译文件，直接给标准按钮改文字最省事，也不会漏掉
    # 某个弹窗 —— 所有消息框都必须经过这里。
    for name, label in (("Ok", "确定"), ("Yes", "是"), ("No", "否"),
                        ("Cancel", "取消"), ("Close", "关闭")):
        handle = box.button(getattr(QMessageBox.StandardButton, name))
        if handle is not None:
            handle.setText(label)

    # QMessageBox 内部是 QGridLayout：新开一行、横跨所有列放弹簧
    layout = box.layout()
    spacer = QSpacerItem(DIALOG_MIN_WIDTH, 0,
                         QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    layout.addItem(spacer, layout.rowCount(), 0, 1, layout.columnCount())
    return box


def _info(parent, title: str, text: str) -> None:
    """提示框（只有一个「确定」）。"""
    _message_box(parent, QMessageBox.Icon.Information, title, text).exec()


def _warn(parent, title: str, text: str) -> None:
    """警告框。"""
    _message_box(parent, QMessageBox.Icon.Warning, title, text).exec()


def _ask(parent, title: str, text: str) -> bool:
    """确认框：用户点了「是」返回 ``True``。"""
    box = _message_box(
        parent, QMessageBox.Icon.Question, title, text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    return box.exec() == QMessageBox.StandardButton.Yes


def _choose(parent, title: str, text: str, options: list[tuple[str, object]]) -> int:
    """多选一的对话框。

    ``options`` 是 ``(按钮文案, 按钮角色)`` 列表；返回被点按钮的下标，
    用户直接关掉窗口则返回 ``-1``。

    按钮文案自己写而不是用标准按钮：一是标准按钮只有「是 / 否」两档，
    二是「立即更新 / 打开下载页 / 以后再说」这种措辞比「是 / 否」清楚得多。
    """
    box = _message_box(parent, QMessageBox.Icon.Question, title, text,
                       QMessageBox.StandardButton.NoButton)
    buttons = [box.addButton(label, role) for label, role in options]
    box.setDefaultButton(buttons[0])
    box.exec()

    clicked = box.clickedButton()
    for index, handle in enumerate(buttons):
        if handle is clicked:
            return index
    return -1


class _UpdateWorker(QThread):
    """在后台线程里查询最新版本。

    网络请求可能卡住好几秒，放在主线程会让整个界面失去响应；这里用 Qt 的
    信号把结果投回 GUI 线程，弹窗仍然在主线程里进行。
    """

    #: ``(发布信息, 错误文本)`` —— 二者必有一个为空
    finished_check = Signal(object, str)

    def run(self) -> None:  # noqa: D102 (Qt 虚函数)
        try:
            release = check_latest()
        except UpdateError as exc:
            self.finished_check.emit(None, str(exc))
        except Exception as exc:                     # noqa: BLE001 兜底
            self.finished_check.emit(None, f"未知错误：{exc}")
        else:
            self.finished_check.emit(release, "")


class _DownloadWorker(QThread):
    """在后台线程里下载并校验新版本。

    产物有 45 MB 上下，慢网络下要几十秒；放在主线程里连进度条本身都会卡住。
    """

    #: ``(已下载字节, 总字节)``；总字节未知时为 0
    progressed = Signal(int, int)
    #: ``(Staged | None, 错误文本)`` —— 二者必有一个为空
    finished_download = Signal(object, str)
    #: 用户取消，不算失败
    cancelled = Signal()

    def __init__(self, release: Release, parent=None) -> None:
        super().__init__(parent)
        self._release = release
        self._stop = threading.Event()

    def cancel(self) -> None:
        """请下载线程停下；下一个分块处生效。"""
        self._stop.set()

    def run(self) -> None:  # noqa: D102 (Qt 虚函数)
        try:
            staged = stage(
                self._release,
                progress=lambda done, total: self.progressed.emit(done, total),
                cancel=self._stop.is_set,
            )
        except DownloadCancelled:
            self.cancelled.emit()
        except UpdateError as exc:
            self.finished_download.emit(None, str(exc))
        except Exception as exc:                     # noqa: BLE001 兜底
            self.finished_download.emit(None, f"未知错误：{exc}")
        else:
            self.finished_download.emit(staged, "")


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        # 每个文件项：[绝对路径, 原文件名, 新文件名, 状态, 是否勾选]
        self.files: list[list] = []
        self.history: list[tuple[str, str]] = []
        # 皮肤名从配置文件恢复。这里**不做校验**：Theme.get 对未知值自带回退，
        # 在 __init__ 里再查一遍只会让「配置坏了」这件小事多出一处分支。
        self._skin: str = get_skin()
        self._theme: dict[str, str] = Theme.get(self._skin)
        # (动作/按钮, Lucide 图标名) —— 主题切换时要按新配色重新着色
        self._menu_icons: list[tuple[QAction, str]] = []
        self._toolbar_icons: list[tuple[QPushButton, str, str]] = []
        # 「视图 → 皮肤」下的勾选项：皮肤键 -> 动作
        self._skin_actions: dict[str, QAction] = {}
        self._skin_menu: QMenu | None = None
        # 检查更新的后台线程；持有引用，避免线程跑着跑着被回收
        self._update_worker: _UpdateWorker | None = None
        # 下载新版的线程与进度框；同样得留住引用
        self._download_worker: _DownloadWorker | None = None
        self._download_dialog: QProgressDialog | None = None
        # 行拖动开始时的顺序快照；拖动中按 ESC 取消时用它还原
        self._drag_snapshot: list[list] | None = None

        self.setWindowTitle(f"{__app_name__} v{__version__}")
        icon = QIcon(resource_path("icon.png"))
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.resize(1160, 730)
        self.setAcceptDrops(True)

        self._build_menu()
        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------ 菜单

    def _build_menu(self) -> None:
        bar = self.menuBar()

        # 「文件」只保留真正与文件相关的两个入口：打开文件夹 / 添加文件。
        # 「刷新」是工具栏上的动作，菜单里不再重复；「退出」交给窗口关闭按钮。
        m_file = bar.addMenu("文件")
        self._action(m_file, "打开文件夹", self.browse_folder, "Ctrl+O",
                     ICON_BROWSE)
        self._action(m_file, "添加文件", self.add_files, "Ctrl+Shift+O",
                     ICON_ADD_FILES)

        m_edit = bar.addMenu("编辑")
        self._action(m_edit, "全选",
                     lambda: self.chk_all.setChecked(True), "Ctrl+A",
                     ICON_CHECK_ALL)
        self._action(m_edit, "取消全选",
                     lambda: self.chk_all.setChecked(False), None,
                     ICON_UNCHECK_ALL)
        m_edit.addSeparator()
        self._action(m_edit, "清空列表", self.clear_all, None, ICON_CLEAR)
        self._action(m_edit, "撤销上次重命名", self.undo_rename, "Ctrl+Z",
                     ICON_UNDO)

        m_view = bar.addMenu("视图")
        self._build_skin_menu(m_view)
        m_view.addSeparator()
        self._action(m_view, "切换深色 / 浅色", self.toggle_theme, "Ctrl+D",
                     ICON_THEME)

        m_help = bar.addMenu("帮助")
        self._action(m_help, "检查更新", self.check_update, "Ctrl+U",
                     ICON_UPDATE)
        m_help.addSeparator()
        self._action(m_help, "关于", self.show_about, None, ICON_ABOUT)

    def _action(self, menu, text: str, slot, shortcut: str | None = None,
                icon_name: str | None = None) -> QAction:
        act = QAction(text, self)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        menu.addAction(act)
        if icon_name:
            self._menu_icons.append((act, icon_name))
        return act

    def _build_skin_menu(self, parent: QMenu) -> None:
        """在「视图」下挂一个「皮肤」子菜单，当前皮肤带勾。

        用 ``QActionGroup`` 而不是普通 ``QCheckBox`` 式的勾选动作：分组自带互斥，
        点新的一项时旧项会自动取消，不需要手写「取消兄弟项」的逻辑，也就不存在
        「两套皮肤同时打勾」的中间态。
        """
        menu = parent.addMenu("皮肤")
        self._skin_menu = menu

        group = QActionGroup(self)
        group.setExclusive(True)
        for key in Theme.keys():
            act = QAction(Theme.name(key), self)
            act.setCheckable(True)
            act.setChecked(key == self._skin)
            act.triggered.connect(lambda _checked=False, k=key: self.set_skin(k))
            group.addAction(act)
            menu.addAction(act)
            self._skin_actions[key] = act

    # ------------------------------------------------------------ 界面

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())

        body = QWidget()
        body_l = QHBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(0)
        body_l.addWidget(self._build_left())
        body_l.addWidget(self._build_right(), 1)
        root.addWidget(body, 1)

        self._build_pages()
        self._sync_all()

    # ------------------------------------------------------------ 工具栏

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("toolbarWidget")
        bar.setFixedHeight(TOOLBAR_HEIGHT)
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 9, 16, 9)
        h.setSpacing(6)

        lab = QLabel("文件夹")
        lab.setObjectName("toolbarLabel")
        h.addWidget(lab)

        # 与原版一致：这里是一个只读输入框，用来显示当前路径 / 占位提示
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.folder_edit.setPlaceholderText(FOLDER_PLACEHOLDER)
        self.folder_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h.addWidget(self.folder_edit, 1)

        specs = (
            ("打开文件夹", self.browse_folder, ICON_BROWSE, "text_primary"),
            ("添加文件", self.add_files, ICON_ADD_FILES, "text_primary"),
            ("刷新", self.refresh_list, ICON_REFRESH, "text_primary"),
            ("清空", self.clear_all, ICON_CLEAR, "text_primary"),
        )
        for text, slot, icon_name, color_key in specs:
            btn = QPushButton(text)
            btn.setObjectName("tbBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(slot)
            if SHOW_TOOLBAR_ICONS:
                btn.setIconSize(QSize(TOOL_ICON_SIZE, TOOL_ICON_SIZE))
                self._toolbar_icons.append((btn, icon_name, color_key))
            h.addWidget(btn)

        sep = QFrame()
        sep.setObjectName("toolbarSep")
        sep.setFixedWidth(1)
        h.addWidget(sep)

        self.btn_preview = QPushButton("预览效果")
        self.btn_preview.setObjectName("btnPreview")
        self.btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview.clicked.connect(self.preview)
        h.addWidget(self.btn_preview)

        self.btn_execute = QPushButton("执行修改")
        self.btn_execute.setObjectName("btnExecute")
        self.btn_execute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_execute.clicked.connect(self.execute)
        h.addWidget(self.btn_execute)

        if SHOW_TOOLBAR_ICONS:
            # 这两个按钮是彩底白字，图标必须跟着用白色
            for btn, icon_name in ((self.btn_preview, ICON_PREVIEW),
                                   (self.btn_execute, ICON_EXECUTE)):
                btn.setIconSize(QSize(TOOL_ICON_SIZE, TOOL_ICON_SIZE))
                self._toolbar_icons.append((btn, icon_name, "#ffffff"))
        return bar

    # ------------------------------------------------------------ 左栏

    def _build_left(self) -> QFrame:
        left = QFrame()
        left.setObjectName("sidePanel")
        left.setFixedWidth(SIDE_WIDTH)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        self.tabsel = TabSelector()
        lv.addWidget(self.tabsel)

        self.stack = QStackedWidget()
        self.tabsel.stack = self.stack
        lv.addWidget(self.stack, 1)
        return left

    # ------------------------------------------------------------ 右栏

    def _build_right(self) -> QFrame:
        right = QFrame()
        right.setObjectName("filePanel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 18, 0, 8)
        rl.setSpacing(6)
        rl.addWidget(self._build_list_header())

        self.table = FileTable(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["", "原文件名", "新文件名", "扩展名", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.itemChanged.connect(self._on_item_changed)

        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setHighlightSections(False)
        header.setFixedHeight(28)
        # 列宽必须可拖动调节：Stretch 模式下用户拖不动分界线。
        # 全部改 Interactive，最后一列吃掉剩余宽度，避免右侧留一条空白。
        header.setMinimumSectionSize(28)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for col, width in ((COL_CHK, 42), (COL_EXT, 56),
                           (COL_ORIG, 280), (COL_NEW, 280),
                           (COL_STATUS, 98)):
            self.table.setColumnWidth(col, width)
        # 不画单元格虚线焦点框（键盘导航不受影响）
        self.table.setItemDelegate(NoFocusDelegate(self.table))
        # 行拖动与外部文件拖入都由 FileTable 接管后以信号通知
        self.table.reorder_requested.connect(self._reorder_rows)
        self.table.files_dropped.connect(self._add_paths)
        self.table.drag_started.connect(self._on_drag_started)
        self.table.drag_state_changed.connect(self._on_drag_state)
        self.table.drag_finished.connect(self._on_drag_finished)
        self.table.drag_cancelled.connect(self._on_drag_cancelled)
        rl.addWidget(self.table, 1)
        rl.addWidget(self._build_bottom_bar())
        return right

    def _build_list_header(self) -> QWidget:
        frame = QWidget()
        frame.setFixedHeight(27)
        h = QHBoxLayout(frame)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(12)

        self.file_count = QLabel("0 个文件")
        self.file_count.setObjectName("fileListCount")
        h.addWidget(self.file_count)
        h.addStretch()

        # 状态提示借用这一行的空白区域，避免在底部多出一条原版没有的状态栏
        self.status_label = QLabel("")
        self.status_label.setObjectName("dragHint")
        h.addWidget(self.status_label)

        drag = QLabel(DRAG_HINT)
        drag.setObjectName("dragHint")
        h.addWidget(drag)
        return frame

    def _build_bottom_bar(self) -> QWidget:
        frame = QWidget()
        h = QHBoxLayout(frame)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(18)

        self.chk_all = QCheckBox("全选")
        self.chk_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_all.toggled.connect(self._toggle_all)
        h.addWidget(self.chk_all)

        self.chk_drag = QCheckBox("可拖动")
        self.chk_drag.setCursor(Qt.CursorShape.PointingHandCursor)
        # 默认勾上：原版其实一启动就允许拖动，只是复选框忘了同步状态，
        # 导致「看起来不能拖、实际能拖」。这里让勾选状态说实话。
        self.chk_drag.setChecked(True)
        self.chk_drag.toggled.connect(self._set_draggable)
        h.addWidget(self.chk_drag)
        h.addStretch()
        return frame

    # ------------------------------------------------------------ 页面骨架

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 16, 12, 12)
        v.setSpacing(26)
        return w, v

    @staticmethod
    def _group(title: str) -> tuple[QGroupBox, QVBoxLayout]:
        grp = QGroupBox(title)
        gv = QVBoxLayout(grp)
        gv.setContentsMargins(14, 18, 14, 14)
        gv.setSpacing(8)
        return grp, gv

    @staticmethod
    def _hint(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("hint")
        lb.setWordWrap(True)
        return lb

    def _cond_row(self, parent: QVBoxLayout) -> tuple[QWidget, QHBoxLayout]:
        """一行「按需显示」的控件，默认隐藏，返回 ``(容器, 布局)``。"""
        holder = QWidget()
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        holder.setVisible(False)
        parent.addWidget(holder)
        return holder, h

    @staticmethod
    def _spin(lo: int, hi: int, value: int, width: int = 62,
              buttons: bool = True) -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(value)
        sp.setFixedWidth(width)
        if not buttons:
            # 见 theme.build_qss：不能用 setButtonSymbols(NoButtons)
            sp.setObjectName("plainSpin")
        return sp

    @staticmethod
    def _exclusive(boxes: tuple[QCheckBox, ...], on_change) -> None:
        """把一组复选框变成「单选」：勾中一个就取消组内其余。

        外观仍然是方框（原版截图如此），只是行为互斥——同时勾「文件名前」和
        「文件名后」这类组合既难预期也没有实际意义。允许全部不选，这样删除页
        可以安稳地停在「什么都不删」的初始状态。

        ``on_change`` 在每次状态变化后调用，用来刷新「按需显示」的输入行：
        被 ``blockSignals`` 取消的兄弟项不会发出信号，必须在这里补一次。
        """
        def on_toggled(checked: bool, box: QCheckBox) -> None:
            if checked:
                for other in boxes:
                    if other is not box and other.isChecked():
                        other.blockSignals(True)
                        other.setChecked(False)
                        other.blockSignals(False)
            on_change()

        for box in boxes:
            box.toggled.connect(partial(on_toggled, box=box))
        on_change()

    def _build_pages(self) -> None:
        builders = {
            "序号": self._page_number, "添加": self._page_add,
            "删除": self._page_delete, "替换": self._page_replace,
            "转换": self._page_case, "扩展名": self._page_ext,
            "其他": self._page_other, "关于": self._page_about,
        }
        for label, color in TAB_COLORS:
            self.tabsel.addTab(builders[label](), label, color)

    # ------------------------------------------------------------ 序号页

    def _page_number(self) -> QWidget:
        w, v = self._page()

        grp, gv = self._group("命名格式")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("格式:"))
        self.num_fmt = QLineEdit("#_[原文件名]")
        self.num_fmt.setPlaceholderText("# = 序号, [原文件名] = 原文件名")
        row.addWidget(self.num_fmt, 1)
        row.addWidget(self._build_format_menu())
        gv.addLayout(row)
        gv.addWidget(self._hint("# = 序号, [原文件名] = 原文件名(不可单独修改)"))
        v.addWidget(grp)

        grp2, gv2 = self._group("参数")
        r1 = QHBoxLayout()
        r1.setSpacing(6)
        r1.addWidget(QLabel("起始:"))
        self.num_start = self._spin(0, 999999, 1)
        r1.addWidget(self.num_start)
        r1.addSpacing(16)
        r1.addWidget(QLabel("增量:"))
        self.num_step = self._spin(-99999, 99999, 1)
        r1.addWidget(self.num_step)
        r1.addSpacing(16)
        r1.addWidget(QLabel("位数:"))
        self.num_digits = self._spin(0, 20, 2, buttons=False)
        r1.addWidget(self.num_digits)
        r1.addStretch()
        gv2.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(6)
        r2.addWidget(QLabel("截止(0=不限):"))
        self.num_end = self._spin(0, 999999, 0)
        r2.addWidget(self.num_end)
        r2.addSpacing(16)
        self.num_random = QCheckBox("随机编号")
        r2.addWidget(self.num_random)
        r2.addStretch()
        gv2.addLayout(r2)
        v.addWidget(grp2)

        v.addStretch()
        return w

    def _build_format_menu(self) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("fmtMore")
        btn.setFixedSize(46, 32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setIconSize(QSize(11, 11))
        self.fmt_more_btn = btn
        menu = QMenu(btn)
        for template in FORMAT_PRESETS:
            act = menu.addAction(template)
            act.triggered.connect(
                lambda _=False, t=template: self.num_fmt.setText(t))
        btn.setMenu(menu)
        btn.setToolTip("选择常用的命名格式")
        return btn

    # ------------------------------------------------------------ 添加页

    def _page_add(self) -> QWidget:
        w, v = self._page()
        grp, gv = self._group("添加文字")

        r1 = QHBoxLayout()
        r1.setSpacing(14)
        r1.addWidget(QLabel("位置:"))
        self.add_prefix = QCheckBox("文件名前")
        self.add_suffix = QCheckBox("文件名后")
        self.add_pos = QCheckBox("指定位置")
        self.add_prefix.setChecked(True)      # 与原版一致的默认值
        for cb in (self.add_prefix, self.add_suffix, self.add_pos):
            r1.addWidget(cb)
        r1.addStretch()
        gv.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(8)
        r2.addWidget(QLabel("内容:"))
        self.add_text = QLineEdit()
        self.add_text.setPlaceholderText("输入要添加的文字...")
        r2.addWidget(self.add_text, 1)
        gv.addLayout(r2)

        self._add_pos_row, r3 = self._cond_row(gv)
        r3.addWidget(QLabel("在第"))
        self.add_pos_idx = self._spin(0, 99999, 1, width=70)
        r3.addWidget(self.add_pos_idx)
        r3.addWidget(QLabel("个字符后"))
        r3.addStretch()

        self.add_prefix.setToolTip("在文件名最前面插入")
        self.add_suffix.setToolTip("在文件名（扩展名之前）最后面插入")
        self.add_pos.setToolTip("在指定的字符位置插入")
        # 放在最后：_exclusive 会立刻回调一次 on_change，此时这些行必须已存在
        self._exclusive((self.add_prefix, self.add_suffix, self.add_pos),
                        self._sync_add_rows)
        v.addWidget(grp)
        v.addStretch()
        return w

    def _sync_add_rows(self) -> None:
        self._add_pos_row.setVisible(self.add_pos.isChecked())

    # ------------------------------------------------------------ 删除页

    def _page_delete(self) -> QWidget:
        w, v = self._page()
        grp, gv = self._group("删除文字")

        r1 = QHBoxLayout()
        r1.setSpacing(14)
        self.del_text = QCheckBox("指定文本")
        self.del_head = QCheckBox("开头N字符")
        self.del_tail = QCheckBox("结尾N字符")
        for cb in (self.del_text, self.del_head, self.del_tail):
            r1.addWidget(cb)
        r1.addStretch()
        gv.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(14)
        self.del_from_front = QCheckBox("从前数删除")
        self.del_from_back = QCheckBox("从后数删除")
        for cb in (self.del_from_front, self.del_from_back):
            r2.addWidget(cb)
        r2.addStretch()
        gv.addLayout(r2)

        # 「内容」只在勾选「指定文本」时才有意义，其余四种模式都不用它，
        # 一直摆在那里会让人误以为要同时填。
        self._del_text_row, r3 = self._cond_row(gv)
        r3.addWidget(QLabel("内容:"))
        self.del_entry = QLineEdit()
        self.del_entry.setPlaceholderText("要删除的文字...")
        r3.addWidget(self.del_entry, 1)

        self._del_cnt_row, r4 = self._cond_row(gv)
        r4.addWidget(QLabel("字符数:"))
        self.del_cnt = self._spin(0, 99999, 1, width=70)
        r4.addWidget(self.del_cnt)
        r4.addStretch()

        self._del_pos_row, r5 = self._cond_row(gv)
        r5.addWidget(QLabel("起始位置:"))
        self.del_pos_from = self._spin(1, 99999, 1, width=70)
        r5.addWidget(self.del_pos_from)
        r5.addSpacing(8)
        r5.addWidget(QLabel("删除个数:"))
        self.del_pos_cnt = self._spin(1, 99999, 1, width=70)
        r5.addWidget(self.del_pos_cnt)
        r5.addStretch()

        tip = "五种删除方式只能选一种；全部不选时不做任何删除"
        for cb in (self.del_text, self.del_head, self.del_tail,
                   self.del_from_front, self.del_from_back):
            cb.setToolTip(tip)
        self.del_text.setToolTip(f"{tip}（在「内容」里填写要删掉的字）")
        self.del_head.setToolTip(f"{tip}（N 取自下面的「字符数」）")
        self.del_tail.setToolTip(f"{tip}（N 取自下面的「字符数」）")
        self.del_from_front.setToolTip(
            f"{tip}（从「起始位置」起往后再删「删除个数」个）")
        self.del_from_back.setToolTip(
            f"{tip}（从倒数「起始位置」个起往前再删「删除个数」个）")

        # 放在最后：_exclusive 会立刻回调一次 on_change，此时上面两行必须已存在
        self._exclusive((self.del_text, self.del_head, self.del_tail,
                         self.del_from_front, self.del_from_back),
                        self._sync_del_rows)
        v.addWidget(grp)
        v.addStretch()
        return w

    def _sync_del_rows(self) -> None:
        self._del_text_row.setVisible(self.del_text.isChecked())
        self._del_cnt_row.setVisible(
            self.del_head.isChecked() or self.del_tail.isChecked())
        self._del_pos_row.setVisible(
            self.del_from_front.isChecked() or self.del_from_back.isChecked())

    # ------------------------------------------------------------ 替换页

    def _page_replace(self) -> QWidget:
        w, v = self._page()
        grp, gv = self._group("查找替换")

        r1 = QHBoxLayout()
        r1.setSpacing(8)
        r1.addWidget(QLabel("查找:"))
        self.rep_find = QLineEdit()
        self.rep_find.setPlaceholderText("要查找的内容")
        r1.addWidget(self.rep_find, 1)
        gv.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(8)
        r2.addWidget(QLabel("替换:"))
        self.rep_to = QLineEdit()
        self.rep_to.setPlaceholderText("替换为")
        r2.addWidget(self.rep_to, 1)
        gv.addLayout(r2)

        r3 = QHBoxLayout()
        r3.setSpacing(14)
        self.rep_case = QCheckBox("区分大小写")
        self.rep_regex = QCheckBox("正则表达式")
        r3.addWidget(self.rep_case)
        r3.addWidget(self.rep_regex)
        r3.addStretch()
        gv.addLayout(r3)

        v.addWidget(grp)
        v.addStretch()
        return w

    # ------------------------------------------------------------ 转换页

    def _page_case(self) -> QWidget:
        w, v = self._page()
        grp, gv = self._group("大小写转换")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("方式:"))
        self.case_mode = QComboBox()
        self.case_mode.addItems(["全部小写", "全部大写", "首字母大写"])
        row.addWidget(self.case_mode, 1)
        gv.addLayout(row)
        v.addWidget(grp)
        v.addStretch()
        return w

    # ------------------------------------------------------------ 扩展名页

    def _page_ext(self) -> QWidget:
        w, v = self._page()
        grp, gv = self._group("修改扩展名")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("新扩展名:"))
        self.ext_new = QLineEdit()
        self.ext_new.setPlaceholderText("例如 jpg")
        self.ext_new.setFixedWidth(96)
        self.ext_new.editingFinished.connect(self._normalize_ext_input)
        row.addWidget(self.ext_new)
        row.addStretch()
        gv.addLayout(row)
        gv.addWidget(self._hint("无需输入点号，会自动转为小写，例如 PNG → png"))
        v.addWidget(grp)
        v.addStretch()
        return w

    def _normalize_ext_input(self) -> None:
        """离开输入框时把扩展名就地改正，让用户看到真正会写入的值。"""
        fixed = normalize_ext(self.ext_new.text())
        if fixed and fixed != self.ext_new.text():
            self.ext_new.setText(fixed)

    # ------------------------------------------------------------ 其他页

    def _page_other(self) -> QWidget:
        w, v = self._page()
        grp, gv = self._group("按顺序命名")
        gv.addWidget(self._hint("输入多个名称，用空格隔开，依次分配给文件列表中的文件："))
        self.other_entry = QLineEdit()
        self.other_entry.setPlaceholderText("张三 李四 王五 ...")
        gv.addWidget(self.other_entry)
        v.addWidget(grp)
        v.addStretch()
        return w

    # ------------------------------------------------------------ 关于页

    def _page_about(self) -> QWidget:
        w, v = self._page()
        grp, gv = self._group("关于")

        title = QLabel(f"{__app_name__} v{__version__}")
        title.setObjectName("aboutTitle")
        gv.addWidget(title)
        sub = QLabel(__app_name_en__)
        sub.setObjectName("aboutSubtitle")
        gv.addWidget(sub)
        gv.addSpacing(6)
        info = QLabel(
            "一个基于 PySide6 的批量文件重命名工具。\n\n"
            "支持序号、添加、删除、替换、大小写转换、扩展名、按顺序命名\n"
            "七类规则；预览与执行分离，支持撤销。")
        info.setObjectName("aboutInfo")
        info.setWordWrap(True)
        gv.addWidget(info)
        v.addWidget(grp)
        v.addStretch()
        return w

    # ------------------------------------------------------------ 主题

    def _apply_theme(self) -> None:
        self._theme = Theme.get(self._skin)
        app = QApplication.instance()
        if app is not None:
            fix_palette(app, self._skin)
        # QSS 的位图图标按主题着色后落到缓存目录里，再交给样式表
        self.setStyleSheet(build_qss(self._theme, theme_icon_dir(self._skin)))
        self.table.indicator_color = self._theme["accent"]
        self._paint_icons()
        self.tabsel.set_theme(self._theme)
        self._restyle_status()

    def _paint_icons(self) -> None:
        """按当前主题色给菜单项、子菜单与工具栏按钮重新着色 Lucide 图标。"""
        t = self._theme
        for act, name in self._menu_icons:
            act.setIcon(icon(name, t["text_primary"]))
        for btn, name, color_key in self._toolbar_icons:
            btn.setIcon(icon(name, t.get(color_key, color_key),
                             TOOL_ICON_SIZE))
        if getattr(self, "fmt_more_btn", None) is not None:
            self.fmt_more_btn.setIcon(icon(ICON_MORE, t["accent"], 11))
        if self._skin_menu is not None:
            # QMenu 自己没有 setIcon，子菜单标题的图标只能改它的 menuAction
            self._skin_menu.menuAction().setIcon(
                icon(ICON_PALETTE, t["text_primary"]))

    def _restyle_status(self) -> None:
        if not hasattr(self, "table") or self.table.rowCount() == 0:
            return
        for r in range(self.table.rowCount()):
            item = self.table.item(r, COL_STATUS)
            if item is not None:
                item.setForeground(QColor(self._theme[STATUS_COLORS.get(
                    item.text(), "text_primary")]))

    def set_skin(self, key: str) -> None:
        """切换到 ``key`` 这套皮肤，并把选择写进配置文件。

        切换皮肤只重刷样式表与图标，**不动 ``self.files`` 里的任何数据** ——
        用户挑皮肤时列表里可能已经排好了预览结果，刷新一下不该把它弄丢。
        """
        if not Theme.has(key) or key == self._skin:
            return
        self._skin = key
        for name, act in self._skin_actions.items():
            act.setChecked(name == key)
        self._apply_theme()
        set_skin(key)
        self._set_status(f"已切换皮肤：{Theme.name(key)}")

    def toggle_theme(self) -> None:
        """在「经典浅色 / 经典深色」这一对之间快速切换（Ctrl+D）。"""
        light, dark = Theme.TOGGLE_PAIR
        self.set_skin(dark if self._skin != dark else light)

    # ------------------------------------------------------------ 数据

    def _set_status(self, text: str) -> None:
        """更新列表头部的提示文字（原版没有状态栏，提示借用这一行的空白）。"""
        self.status_label.setText(text)

    def _add_paths(self, paths: list[str], reset: bool = False) -> None:
        if reset:
            self.files.clear()
            self.history.clear()
        added = 0
        for p in paths:
            p = os.path.abspath(p)
            if os.path.isdir(p):
                for name in sorted(os.listdir(p), key=natural_sort_key):
                    full = os.path.join(p, name)
                    if os.path.isfile(full) and self._append(full):
                        added += 1
            elif os.path.isfile(p) and self._append(p):
                added += 1
        self.refresh_table()
        if added:
            self._set_status(f"已添加 {added} 个文件，共 {len(self.files)} 个")

    def _append(self, full: str) -> bool:
        if any(f[0] == full for f in self.files):
            return False
        name = os.path.basename(full)
        self.files.append([full, name, name, "", True])
        return True

    def refresh_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.files))
        for r, f in enumerate(self.files):
            chk = QTableWidgetItem("")
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable |
                         Qt.ItemFlag.ItemIsEnabled |
                         Qt.ItemFlag.ItemIsSelectable)
            chk.setCheckState(Qt.CheckState.Checked if f[4]
                              else Qt.CheckState.Unchecked)
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, COL_CHK, chk)
            self.table.setItem(r, COL_ORIG, QTableWidgetItem(f[1]))
            self.table.setItem(r, COL_NEW, QTableWidgetItem(f[2]))
            self.table.setItem(r, COL_EXT, QTableWidgetItem(
                os.path.splitext(f[2])[1]))
            status = QTableWidgetItem(f[3])
            status.setForeground(QColor(
                self._theme[STATUS_COLORS.get(f[3], "text_primary")]))
            self.table.setItem(r, COL_STATUS, status)
        self.table.blockSignals(False)
        self.file_count.setText(f"{len(self.files)} 个文件")
        self._sync_all()

    def _sync_all(self) -> None:
        total = len(self.files)
        checked = sum(1 for f in self.files if f[4])
        self.chk_all.blockSignals(True)
        # 空列表也保持勾选（原版如此），避免“全选”看起来被禁用
        self.chk_all.setChecked(total == 0 or checked == total)
        self.chk_all.setText(f"全选 {checked}/{total}" if total else "全选")
        self.chk_all.blockSignals(False)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != COL_CHK:
            return
        row = item.row()
        if not 0 <= row < len(self.files):
            return
        state = item.checkState() == Qt.CheckState.Checked
        # 按住 Shift 选中多行后点其中一行的选择框 → 整个选区一起变。
        # 选区行号是 FileTable 在鼠标按下时记下的：勾选在松开时才翻转，
        # 那时点击已经把选区收成一行，再查 selectionModel 就晚了。
        pressed = list(self.table.chk_press_rows)
        self.table.chk_press_rows = []
        targets = pressed if len(pressed) > 1 and row in pressed else [row]
        for r in targets:
            self.files[r][4] = state

        if len(targets) == 1:
            self._sync_all()
            return

        # 整表刷新会清掉选区，先把选中的行记下来再恢复
        selected = [i.row() for i in self.table.selectionModel().selectedRows()]
        self.refresh_table()
        self.table.select_rows(selected)

    def _reorder_rows(self, rows: list[int], target: int) -> None:
        """把拖动的行搬到 ``target`` 位置，然后整表刷新。

        拖动由 :class:`FileTable` 自己实现（不走 Qt 的 ``InternalMove``），
        这里只负责按信号搬数据：Qt 的 ``InternalMove`` 既会与我们的数据
        各自为政、又会在拖动结束后私自删掉选中的行，所以一概不用。

        拖动过程中这个槽会被反复调用 —— 表格是「实时重排」的，鼠标每越过
        一行就把数据搬一次，列表当场排成松手后的样子。因此这里不写状态提示，
        提示统一交给 :meth:`_on_drag_state` / :meth:`_on_drag_finished`。
        """
        rows = [r for r in rows if 0 <= r < len(self.files)]
        if not rows:
            return
        target = max(0, min(target, len(self.files)))
        removed = set(rows)
        taken = [self.files[r] for r in rows]
        before = [f for i, f in enumerate(self.files)
                  if i < target and i not in removed]
        after = [f for i, f in enumerate(self.files)
                 if i >= target and i not in removed]

        first = len(before)
        if before + taken + after == self.files:
            # 拖回原位：不刷新、不提示，免得白闪一下
            self.table.select_rows(range(first, first + len(taken)))
            return

        self.files[:] = before + taken + after
        self.refresh_table()
        # 拖完保持这些行处于选中态，方便接着拖第二次
        self.table.select_rows(range(first, first + len(taken)))
        if not self.table.dragging:
            self._set_status(f"已移动 {len(taken)} 行到第 {first + 1} 位")

    # ------------------------------------------------------------ 拖动提示

    def _on_drag_started(self) -> None:
        """记下拖动前的顺序，供 ESC 取消时还原。"""
        self._drag_snapshot = list(self.files)

    def _on_drag_state(self, position: int, count: int) -> None:
        """拖动过程中实时播报落点，让用户松手前就知道会落到哪。"""
        self._set_status(f"拖动中：{count} 个文件 → 第 {position} 位")

    def _on_drag_finished(self, position: int, count: int) -> None:
        before = self._drag_snapshot or []
        self._drag_snapshot = None
        if [f[1] for f in before] != [f[1] for f in self.files]:
            self._set_status(f"已移动 {count} 个文件到第 {position} 位")
        else:
            self._set_status("顺序未变")

    def _on_drag_cancelled(self) -> None:
        """拖动中按 ESC：顺序还原到本次拖动之前。"""
        if self._drag_snapshot is None:
            return
        self.files[:] = self._drag_snapshot
        self._drag_snapshot = None
        self.refresh_table()
        self._set_status("已取消拖动，顺序已还原")

    def _toggle_all(self, checked: bool) -> None:
        for f in self.files:
            f[4] = checked
        self.refresh_table()

    def _set_draggable(self, on: bool) -> None:
        """「可拖动」复选框：控制能不能拖动行来重排。"""
        if hasattr(self, "table"):
            self.table.row_drag_enabled = on
            self._set_status("已开启行拖动，可直接拖动列表行调整顺序" if on
                             else "已关闭行拖动")

    # ------------------------------------------------------------ 工具栏动作

    def browse_folder(self) -> None:
        """选择文件夹并载入其中的文件。"""
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self._add_paths([folder], reset=True)
            self.folder_edit.setText(folder)

    def add_files(self) -> None:
        """追加选择文件。"""
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if files:
            self._add_paths(files)

    def refresh_list(self) -> None:
        """重新扫描首个文件所在目录。"""
        if not self.files:
            self._set_status("列表为空，无需刷新")
            return
        base = os.path.dirname(self.files[0][0])
        self._add_paths([base], reset=True)
        self.folder_edit.setText(base)
        self._set_status(f"已刷新，共 {len(self.files)} 个文件")

    def clear_all(self) -> None:
        """清空列表并恢复初始状态。"""
        self.files.clear()
        self.history.clear()
        self.refresh_table()
        self.folder_edit.clear()
        self._set_status("已恢复初始状态")

    # ------------------------------------------------------------ 预览 / 执行

    def _settings(self) -> dict[str, object]:
        """把界面控件的当前值汇集成引擎设置字典。"""
        return dict(
            tab=self.tabsel.currentIndex(),
            num_fmt=self.num_fmt.text(),
            num_start=self.num_start.value(),
            num_step=self.num_step.value(),
            num_end=self.num_end.value(),
            num_digits=self.num_digits.value(),
            num_random=self.num_random.isChecked(),
            add_text=self.add_text.text(),
            add_prefix=self.add_prefix.isChecked(),
            add_suffix=self.add_suffix.isChecked(),
            add_pos=self.add_pos.isChecked(),
            add_pos_idx=self.add_pos_idx.value(),
            del_text=self.del_text.isChecked(),
            del_entry=self.del_entry.text(),
            del_head=self.del_head.isChecked(),
            del_tail=self.del_tail.isChecked(),
            del_from_front=self.del_from_front.isChecked(),
            del_from_back=self.del_from_back.isChecked(),
            del_cnt=self.del_cnt.value(),
            del_pos_from=self.del_pos_from.value(),
            del_pos_cnt=self.del_pos_cnt.value(),
            rep_find=self.rep_find.text(),
            rep_to=self.rep_to.text(),
            rep_regex=self.rep_regex.isChecked(),
            rep_case=self.rep_case.isChecked(),
            case_mode=self.case_mode.currentText(),
            ext_new=self.ext_new.text(),
            other_entry=self.other_entry.text(),
        )

    def preview(self) -> None:
        """计算并展示新文件名，不修改磁盘。"""
        if not self.files:
            _warn(self, "提示", "请先添加文件或文件夹")
            return
        engine = RenameEngine(self._settings())
        items = [(f[0], f[1], f[4]) for f in self.files]
        plan = plan_rename(items, engine)
        changed = over = bad = 0
        for f, (_path, orig, new, status) in zip(self.files, plan, strict=True):
            f[1], f[2], f[3] = orig, new, status
            changed += status == STATUS_RENAME
            over += status == STATUS_OVER
            bad += status in (STATUS_CONFLICT, STATUS_TAKEN)
        self.refresh_table()
        msg = f"预览完成 - {changed} 个将被修改"
        if over:
            msg += f"，{over} 个超过截止"
        if bad:
            msg += f"，{bad} 个命名冲突"
        self._set_status(msg)

    def execute(self) -> None:
        """按预览结果执行重命名。"""
        if not self.files:
            return
        todo = [f for f in self.files if f[3] == STATUS_RENAME and f[4]]
        if not todo:
            blocked = [f for f in self.files
                       if f[3] in (STATUS_CONFLICT, STATUS_TAKEN)]
            tip = ("没有待修改的文件，请先点击 [预览效果]"
                   if not blocked else
                   f"有 {len(blocked)} 个文件名冲突，无法执行，请调整命名规则")
            _info(self, "提示", tip)
            return

        if not _ask(self, "确认",
                    f"确定要重命名 {len(todo)} 个文件？\n\n"
                    "此操作可通过「撤销」恢复。"):
            return

        self.history.clear()
        plan = [(f[0], f[1], f[2], STATUS_RENAME) for f in todo]
        ok, errors = apply_rename(plan, self.history)

        failed = {path for path, _name, _why in errors}
        for f in todo:
            if f[0] in failed:
                f[3] = "失败"
        # history 记录的是 (新路径, 原路径)，据此把列表同步到新路径
        mapping = {origin: final for final, origin in self.history}
        for f in self.files:
            if f[0] in mapping:
                f[0] = mapping[f[0]]
                f[1] = f[2] = os.path.basename(f[0])
                f[3] = "已完成"
        self.refresh_table()

        msg = f"完成！成功 {ok} 个"
        if errors:
            msg += f"，失败 {len(errors)} 个"
            detail = "\n".join(f"  {n}：{why}" for _, n, why in errors[:20])
            _warn(self, "部分失败", msg + "\n\n" + detail)
        else:
            _info(self, "已完成", msg)
        self._set_status(msg)

    def undo_rename(self) -> None:
        """撤销上一次重命名。"""
        if not self.history:
            _info(self, "提示", "没有可撤销的操作")
            return
        if not _ask(self, "确认", f"撤销最近 {len(self.history)} 次重命名？"):
            return

        # core.undo 会清空 history，先把 (现名 -> 原名) 的映射留下来，
        # 否则列表里的路径会停留在旧的新名上，后续任何操作都会失败。
        restore = {final: origin for final, origin in self.history}
        ok, fail = undo(self.history)

        for f in self.files:
            origin = restore.get(f[0])
            if origin is None:
                continue
            f[0] = origin
            if os.path.exists(origin):
                f[1] = f[2] = os.path.basename(origin)
                f[3] = ""
            else:
                f[3] = "失败"
        self.refresh_table()
        msg = f"撤销完成：{ok} 个已恢复" + (f"，{fail} 个失败" if fail else "")
        self._set_status(msg)
        _info(self, "撤销完成", msg)

    def show_about(self) -> None:
        self.tabsel.setCurrentIndex(self.tabsel.count() - 1)

    # ------------------------------------------------------------ 检查更新

    def check_update(self) -> None:
        """查询 GitHub 上有没有更新的正式版本。

        网络请求交给 :class:`_UpdateWorker` 在后台线程执行，避免界面卡住；
        结果通过信号回到主线程后再弹窗。
        """
        if self._update_worker is not None and self._update_worker.isRunning():
            self._set_status("正在检查更新…（请稍候）")
            return
        self._set_status("正在检查更新…")
        self._update_worker = _UpdateWorker(self)
        self._update_worker.finished_check.connect(self._on_update_checked)
        self._update_worker.start()

    def _on_update_checked(self, release: Release | None, error: str) -> None:
        if error:
            self._set_status("检查更新失败")
            _warn(self, "检查更新",
                  f"{error}\n\n也可以直接访问项目发布页：\n{RELEASES_PAGE}")
            return

        if release is None:
            self._set_status("暂无发布版本")
            _info(self, "检查更新", "作者尚未发布任何正式版本。")
            return

        if not is_newer(release.version, __version__):
            self._set_status(f"已是最新版本 v{__version__}")
            _info(self, "检查更新", f"当前已是最新版本 v{__version__}。")
            return

        self._set_status(f"发现新版本 {release.version}")

        # 能不能在本程序内更新，取决于三件事：是不是打包运行、这个平台有没有
        # 对应的附件、以及附件有没有带 SHA256 摘要。任何一条不满足就老老实实
        # 退回「打开下载页」—— 理由要讲清楚，别让用户以为功能坏了。
        reason = self._self_update_blocker(release)
        if reason:
            if _ask(self, "发现新版本",
                    f"发现新版本 {release.version}（当前 v{__version__}）。\n\n"
                    f"{reason}\n是否打开下载页面？"):
                QDesktopServices.openUrl(QUrl(release.url))
            return

        choice = _choose(
            self, "发现新版本",
            f"发现新版本 {release.version}（当前 v{__version__}）。\n\n"
            "可以直接在程序内下载并校验，完成后自动重启完成更新。",
            [("立即更新", QMessageBox.ButtonRole.AcceptRole),
             ("打开下载页", QMessageBox.ButtonRole.ActionRole),
             ("以后再说", QMessageBox.ButtonRole.RejectRole)])
        if choice == 0:
            self._start_self_update(release)
        elif choice == 1:
            QDesktopServices.openUrl(QUrl(release.url))
        else:
            self._set_status(f"有新版本 {release.version}（本次未更新）")

    @staticmethod
    def _self_update_blocker(release: Release) -> str:
        """返回「不能自动更新」的原因；可以自动更新时返回空串。"""
        if not supports_self_update():
            return "当前是以源码方式运行的，无法替换自身。"
        try:
            pick_asset(release)
        except UpdateError as exc:
            return str(exc)
        return ""

    # ------------------------------------------------------------ 就地更新

    def _start_self_update(self, release: Release) -> None:
        """下载新版本并校验，全程带一个可以取消的进度条。"""
        if self._download_worker is not None and self._download_worker.isRunning():
            self._set_status("正在下载更新…（请稍候）")
            return

        dialog = QProgressDialog("正在下载新版本…", "取消", 0, 0, self)
        dialog.setWindowTitle("下载更新")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumWidth(DIALOG_MIN_WIDTH)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)

        worker = _DownloadWorker(release, self)
        self._download_worker = worker
        self._download_dialog = dialog

        worker.progressed.connect(self._on_download_progress)
        worker.finished_download.connect(partial(self._on_download_done, dialog))
        worker.cancelled.connect(partial(self._on_download_cancelled, dialog))
        dialog.canceled.connect(worker.cancel)

        dialog.show()
        worker.start()
        self._set_status(f"正在下载 {release.version}…")

    def _on_download_progress(self, done: int, total: int) -> None:
        dialog = self._download_dialog
        if dialog is None:
            return
        if total > 0 and dialog.maximum() != total:
            dialog.setRange(0, total)
        if total > 0:
            dialog.setValue(done)
        downloaded = f"{done / 1024 / 1024:.1f} MB"
        if total > 0:
            downloaded += f" / {total / 1024 / 1024:.1f} MB"
        dialog.setLabelText(f"正在下载新版本… {downloaded}")

    def _close_download_dialog(self, dialog: QProgressDialog) -> None:
        dialog.close()
        if self._download_dialog is dialog:
            self._download_dialog = None

    def _on_download_cancelled(self, dialog: QProgressDialog) -> None:
        self._close_download_dialog(dialog)
        self._set_status("已取消更新下载")

    def _on_download_done(self, dialog: QProgressDialog, staged: Staged | None,
                          error: str) -> None:
        self._close_download_dialog(dialog)

        if error:
            self._set_status("更新下载失败")
            _warn(self, "更新失败",
                  f"{error}\n\n也可以到发布页手动下载：\n{RELEASES_PAGE}")
            return
        if staged is None:                       # 理论上不会走到，兜底
            return

        self._set_status(f"已下载 {staged.version}")
        choice = _choose(
            self, "更新已就绪",
            f"{staged.version} 已经下载并校验通过。\n\n"
            "更新需要关闭当前程序来完成替换，随后会重新打开。",
            [("立即重启并更新", QMessageBox.ButtonRole.AcceptRole),
             ("取消", QMessageBox.ButtonRole.RejectRole)])
        if choice != 0:
            self._discard_staged(staged)
            return
        self._apply_and_restart(staged)

    @staticmethod
    def _discard_staged(staged: Staged) -> None:
        """放弃这次更新，把已下载的文件删掉。

        留着它只会变成一个「看着更新过了、其实没有」的陷阱：没有任何代码
        会在下次启动时去应用它。
        """
        try:
            os.unlink(staged.path)
        except OSError:
            pass

    def _apply_and_restart(self, staged: Staged) -> None:
        """启动更新助手并退出，把替换文件的活交给它。"""
        try:
            spawn_apply(staged)
        except OSError as exc:
            self._set_status("无法启动更新助手")
            _warn(self, "更新失败",
                  f"无法启动更新助手：{exc}\n\n请到发布页手动下载：\n{RELEASES_PAGE}")
            return

        self._set_status("正在重启以完成更新…")
        app = QApplication.instance()
        if app is None:
            return
        # 用 singleShot 而不是直接 quit()：此刻还嵌在弹窗的事件循环里，
        # 直接退出的可能是那一层循环，主循环反而留着。
        QTimer.singleShot(0, app.quit)

    # ------------------------------------------------------------ 拖放

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        if paths:
            self._add_paths(paths)
