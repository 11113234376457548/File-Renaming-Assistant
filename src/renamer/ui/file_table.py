"""文件表格：QTableWidget 的定制版。

标准 ``QTableWidget`` 在这几件事上做不了或做不好，因此这里全部自己实现：

1. **列宽可调** —— ``Stretch`` 模式下用户拖不动表头分界线；主窗口改用
   ``Interactive``（见 ``main_window._build_right``），最后一列吃掉剩余宽度。
2. **勾选框跟随选区** —— 按住 Shift 选中多行后点其中一行的选择框，
   整个选区应当一起变；标准控件只会改点击的那一行。这里在鼠标按下时
   把选区行号记进 :attr:`chk_press_rows`，供主窗口的 ``_on_item_changed``
   取用（勾选状态在松开鼠标时才翻转，届时点击已把选区收成一行）。
3. **行拖动重排（实时）** —— 完全自己实现，**不用 Qt 的 ``InternalMove``**。
   原因有两条：``InternalMove`` 只搬视图里的表格项，而真正的数据在
   ``MainWindow.files`` 里，放任 Qt 自己搬必然错位；更麻烦的是
   ``QAbstractItemView.startDrag()`` 在拖动返回 ``MoveAction`` 之后会调用私有的
   ``clearOrRemove()`` 把选中的行从模型里**删掉**，与我们自己的数据重排相互打架。

   现在的做法是「所见即所得」：鼠标每越过一行就**立刻**把数据搬过去并整表刷新，
   所以拖动过程中列表已经排成了松手后的样子，不存在「指示线指着一处、结果落到
   另一处」的错位感。为了让这个循环稳定（不来回抖），落点用当前布局算出来后
   会先判断「搬过去是否等于没搬」，相等就原地不动 —— 被拖的行自己就压在光标
   下面，于是自然收敛。被拖的行画一层强调色底 + 顶边一条加粗插入线。
4. **不画虚线焦点框** —— 单元格获得焦点时 Qt 会画一圈虚线，
   由 :class:`NoFocusDelegate` 在绘制时把焦点状态抹掉。
"""

from __future__ import annotations

from PySide6.QtCore import (
    QItemSelectionModel,
    QPoint,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
)

__all__ = [
    "COL_CHK", "COL_ORIG", "COL_NEW", "COL_EXT", "COL_STATUS",
    "FileTable", "NoFocusDelegate",
]

#: 列号：复选框 / 原文件名 / 新文件名 / 扩展名 / 状态
COL_CHK, COL_ORIG, COL_NEW, COL_EXT, COL_STATUS = 0, 1, 2, 3, 4

#: 拖动时距离视口上下边缘多少像素内开始自动滚动
_AUTOSCROLL_MARGIN = 18
#: 自动滚动每次滚动的像素
_AUTOSCROLL_STEP = 10
#: 自动滚动的间隔（毫秒）
_AUTOSCROLL_INTERVAL = 25
#: 被拖的行的底色透明度（0~255），太淡看不清、太浓压住文字
_DRAG_OVERLAY_ALPHA = 56
#: 插入线粗细
_INSERT_LINE_HEIGHT = 3


class NoFocusDelegate(QStyledItemDelegate):
    """绘制单元格时不画虚线焦点框。

    焦点框是样式在 ``PE_FrameFocusRect`` 里画的，样式表管不到它；
    最省事也最稳的办法是在委托里把 ``State_HasFocus`` 从绘制选项里剥掉。
    视图本身仍保有焦点，键盘方向键照常可用。
    """

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, opt, index)


class FileTable(QTableWidget):
    """文件列表表格：选区勾选 + 实时重排的行拖动。"""

    #: (被拖的行号列表, 插入位置) —— 请求把行搬到该位置（拖动中会反复发出）
    reorder_requested = Signal(object, int)
    #: 外部文件拖入
    files_dropped = Signal(list)
    #: 一次行拖动开始（主窗口借此记录拖动前的顺序，供 ESC 取消时还原）
    drag_started = Signal()
    #: 拖动中落点变化：(1 基的落点位置, 被拖的行数)
    drag_state_changed = Signal(int, int)
    #: 一次行拖动结束：(1 基的落点位置, 被拖的行数)
    drag_finished = Signal(int, int)
    #: 拖动被取消（按了 ESC）
    drag_cancelled = Signal()

    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        #: 鼠标按下选择框列时的选区行号（见类文档第 2 条）
        self.chk_press_rows: list[int] = []
        #: 是否允许拖动行重排，由界面上的「可拖动」复选框控制
        self.row_drag_enabled = True
        #: 插入指示线颜色（跟随主题）
        self.indicator_color = "#5b8def"

        self._press_row = -1
        self._press_pos = QPoint()
        self._drag_rows: list[int] = []
        self._drop_target = -1
        self._last_pos = QPoint()

        # 光标停在视口上下边缘时持续滚动，否则拖不到看不见的行
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(_AUTOSCROLL_INTERVAL)
        self._auto_timer.timeout.connect(self._auto_tick)

        # 只接受外部文件拖入；行重排走自己的鼠标事件，不经过 Qt 的 DnD
        self.setAcceptDrops(True)
        self.setDragEnabled(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDropIndicatorShown(False)

    # ------------------------------------------------------------ 状态

    @property
    def dragging(self) -> bool:
        """是否正在拖动行。"""
        return bool(self._drag_rows)

    # ------------------------------------------------------------ 选区勾选

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """记下按下位置：选择框列用于整块勾选，其它列用于拖动重排。"""
        self.chk_press_rows = []
        self._reset_drag()
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            idx = self.indexAt(pos)
            if idx.isValid() and idx.column() == COL_CHK:
                # 选择框列：点在小方框上就勾选，点在方框旁边的空白处照样能拖动
                rect = self.visualRect(idx)
                on_box = abs(pos.x() - rect.center().x()) <= 12
                if not on_box and self.row_drag_enabled:
                    self._press_row = idx.row()
                    self._press_pos = pos
                else:
                    rows = sorted(
                        {i.row() for i in self.selectionModel().selectedRows()})
                    self.chk_press_rows = (rows if idx.row() in rows
                                           else [idx.row()])
            elif idx.isValid() and self.row_drag_enabled:
                self._press_row = idx.row()
                self._press_pos = pos
        super().mousePressEvent(event)

    # ------------------------------------------------------------ 行拖动

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_row >= 0:
            pos = event.position().toPoint()
            self._last_pos = pos
            if not self._drag_rows:
                moved = (pos - self._press_pos).manhattanLength()
                if moved < QApplication.startDragDistance():
                    super().mouseMoveEvent(event)
                    return
                self._begin_drag()
            self._update_target(pos)
            self._update_autoscroll(pos)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_rows:
            rows, target = list(self._drag_rows), self._drop_target
            self._reset_drag()
            if rows:
                self.reorder_requested.emit(rows, target)
                self.drag_finished.emit(target + 1, len(rows))
            return
        self._reset_drag()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """拖动中按 ESC 取消，顺序还原到本次拖动之前。"""
        if event.key() == Qt.Key.Key_Escape and self._drag_rows:
            self.cancel_drag()
            return
        super().keyPressEvent(event)

    def cancel_drag(self) -> None:
        """放弃当前拖动（不提交任何顺序变化）。"""
        if not self._drag_rows:
            return
        self._reset_drag()
        self.drag_cancelled.emit()

    def _begin_drag(self) -> None:
        """正式进入拖动：确定被拖的行，并让它们保持选中（视觉上跟手）。"""
        selected = sorted(
            {i.row() for i in self.selectionModel().selectedRows()})
        rows = selected if self._press_row in selected else [self._press_row]
        self._drag_rows = rows
        self._drop_target = rows[0]
        self.select_rows(rows)
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        self.drag_started.emit()
        self.drag_state_changed.emit(self._drop_target + 1, len(rows))
        self.viewport().update()

    def _reset_drag(self) -> None:
        self._press_row = -1
        self._drag_rows = []
        self._drop_target = -1
        self._auto_timer.stop()
        self.viewport().unsetCursor()
        self.viewport().update()

    def _update_target(self, pos: QPoint) -> None:
        """按光标位置实时把被拖的行挪到落点。

        「搬到 ``target`` 是否等于没搬」由 :meth:`_is_identity` 判断：相等就原地
        不动。这一条是稳定性的关键 —— 被拖的行就压在光标下面，若不判断就会
        搬过去又搬回来，来回抖动。
        """
        rows = list(self._drag_rows)
        if not rows:
            return
        target = self.target_row_at(pos)
        if self._is_identity(target):
            if self._drop_target != rows[0]:
                self._drop_target = rows[0]
                self.drag_state_changed.emit(self._drop_target + 1, len(rows))
                self.viewport().update()
            return

        first = self._insert_index(rows, target)
        self.reorder_requested.emit(rows, target)
        # 数据层搬完后，这些行落在 [first, first + n)
        self._drag_rows = list(range(first, first + len(rows)))
        self._drop_target = first
        self.drag_state_changed.emit(first + 1, len(rows))
        self.viewport().update()

    def _is_identity(self, target: int) -> bool:
        """把被拖的行插到 ``target`` 之后顺序是否毫无变化。"""
        rows = set(self._drag_rows)
        total = self.rowCount()
        order = (
            [i for i in range(total) if i < target and i not in rows]
            + list(self._drag_rows)
            + [i for i in range(total) if i >= target and i not in rows]
        )
        return order == list(range(total))

    def _insert_index(self, rows: list[int], target: int) -> int:
        """被拖的行搬完后第一个行的下标（与主窗口 ``_reorder_rows`` 一致）。"""
        removed = set(rows)
        return sum(1 for i in range(self.rowCount())
                   if i < target and i not in removed)

    def target_row_at(self, pos: QPoint) -> int:
        """由鼠标 y 坐标算出插入位置，取值 ``0..rowCount``。

        落在某行的上半部 → 插到该行之前；下半部 → 插到该行之后；
        落在表头之上 → 插到最前；落在空白处 → 插到最后。
        """
        row = self.rowAt(max(pos.y(), 0))
        if row < 0:
            return 0 if pos.y() < 0 else self.rowCount()
        rect = self.visualRect(self.model().index(row, 0))
        return row if pos.y() <= rect.center().y() else row + 1

    def _update_autoscroll(self, pos: QPoint) -> None:
        """光标贴到视口上下边缘时启动持续滚动。"""
        bar = self.verticalScrollBar()
        if bar.maximum() <= 0:
            self._auto_timer.stop()
            return
        near_edge = (pos.y() < _AUTOSCROLL_MARGIN
                     or pos.y() > self.viewport().height() - _AUTOSCROLL_MARGIN)
        if near_edge:
            if not self._auto_timer.isActive():
                self._auto_timer.start()
        else:
            self._auto_timer.stop()

    def _auto_tick(self) -> None:
        """定时器回调：滚动一截，并重新计算落点。"""
        if not self._drag_rows:
            self._auto_timer.stop()
            return
        bar = self.verticalScrollBar()
        y = self._last_pos.y()
        if y < _AUTOSCROLL_MARGIN:
            step = -_AUTOSCROLL_STEP
        elif y > self.viewport().height() - _AUTOSCROLL_MARGIN:
            step = _AUTOSCROLL_STEP
        else:
            self._auto_timer.stop()
            return
        before = bar.value()
        bar.setValue(before + step)
        if bar.value() == before:          # 已经到头
            self._auto_timer.stop()
            return
        self._update_target(self._last_pos)
        self.viewport().update()

    def select_rows(self, rows) -> None:
        """整行选中给定行，供拖动开始与重排之后复用。"""
        self.selectionModel().clearSelection()
        for r in rows:
            if 0 <= r < self.rowCount():
                self.selectionModel().select(
                    self.model().index(r, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows)

    # ------------------------------------------------------------ 指示

    def paintEvent(self, event: QPaintEvent) -> None:
        """在正常绘制之上补一层「手里握着哪些行」与落点插入线。"""
        super().paintEvent(event)
        if not self._drag_rows or self.rowCount() == 0:
            return

        viewport = self.viewport()
        width, height = viewport.width(), viewport.height()
        color = QColor(self.indicator_color)

        painter = QPainter(viewport)

        # 1) 被拖的行铺一层强调色底，一眼看出「这几行被拿起来了」
        blend = QColor(color)
        blend.setAlpha(_DRAG_OVERLAY_ALPHA)
        for r in self._drag_rows:
            if 0 <= r < self.rowCount():
                rect = self.visualRect(self.model().index(r, 0))
                if rect.isValid() and not rect.isEmpty():
                    painter.fillRect(
                        QRect(0, rect.top(), width, rect.height()), blend)

        # 2) 顶边画一条加粗插入线，两端加圆头，浅底深底都看得见
        top = self.visualRect(
            self.model().index(self._drag_rows[0], 0)).top()
        top = max(1, min(top, height - _INSERT_LINE_HEIGHT))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(QRect(0, top, width, _INSERT_LINE_HEIGHT), color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        radius = _INSERT_LINE_HEIGHT // 2 + 2
        painter.drawEllipse(QPoint(radius, top + _INSERT_LINE_HEIGHT // 2),
                            radius, radius)
        painter.drawEllipse(QPoint(width - radius,
                                   top + _INSERT_LINE_HEIGHT // 2),
                            radius, radius)

    # ------------------------------------------------------------ 外部拖入

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.files_dropped.emit(
                [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()])
        else:
            event.ignore()
