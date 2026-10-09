"""GUI 冒烟与工作流测试。

在 ``offscreen`` 平台上真实构造主窗口，验证界面可加载、预览 / 执行 / 撤销
这一整条链路的状态一致性。没有安装 PySide6 或无法初始化 Qt 时自动跳过，
因此可安全地放进 CI。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过 GUI 测试")

from PySide6.QtCore import QItemSelectionModel, QPoint, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture()
def window(app):
    from renamer.ui.main_window import MainWindow
    win = MainWindow()
    yield win
    win.close()


@pytest.fixture()
def auto_yes(monkeypatch):
    """把所有模态对话框改为自动应答，避免测试卡住。

    弹窗统一走 ``main_window`` 里的三个小封装（``_ask`` / ``_info`` / ``_warn``），
    它们内部用的是 ``QMessageBox`` 实例而不是静态方法，所以这里直接替换封装。
    """
    from renamer.ui import main_window as mw

    monkeypatch.setattr(mw, "_ask", lambda *a, **k: True)
    monkeypatch.setattr(mw, "_info", lambda *a, **k: None)
    monkeypatch.setattr(mw, "_warn", lambda *a, **k: None)


def _seed(tmp_path, *names: str) -> None:
    for name in names:
        (tmp_path / name).write_text(name, encoding="utf-8")


# ------------------------------------------------------------------ 界面结构

def test_window_has_eight_tabs(window):
    assert window.tabsel.count() == 8
    assert window.tabsel.currentIndex() == 0


def test_tabs_are_laid_out_four_per_row(window):
    """原版是 4 列 × 2 行的按钮网格。"""
    from renamer.ui.tab_selector import COLUMNS
    grid = window.tabsel._grid
    assert COLUMNS == 4
    positions = [grid.getItemPosition(i)[:2] for i in range(grid.count())]
    assert positions == [(0, 0), (0, 1), (0, 2), (0, 3),
                         (1, 0), (1, 1), (1, 2), (1, 3)]


def test_table_has_extension_column(window):
    """表格必须包含「扩展名」列，与截图一致。"""
    headers = [window.table.horizontalHeaderItem(i).text()
               for i in range(window.table.columnCount())]
    assert headers == ["", "原文件名", "新文件名", "扩展名", "状态"]


def test_all_select_is_checked_when_empty(window):
    """原版在空列表时「全选」也是勾上的。"""
    assert window.chk_all.isChecked()


def test_settings_cover_all_pages(window):
    settings = window._settings()
    for key in ("num_fmt", "add_text", "del_entry", "rep_find",
                "case_mode", "ext_new", "other_entry", "tab", "add_pos"):
        assert key in settings


def test_theme_toggle(window):
    assert window._mode == "light"
    window.toggle_theme()
    assert window._mode == "dark"
    window.toggle_theme()
    assert window._mode == "light"


def test_conditional_rows_follow_checkboxes(window):
    """删除页的输入行只在对应模式勾选后出现。"""
    assert window._del_text_row.isHidden()
    assert window._del_cnt_row.isHidden()
    assert window._del_pos_row.isHidden()
    window.del_head.setChecked(True)
    assert not window._del_cnt_row.isHidden()
    window.del_from_front.setChecked(True)
    assert not window._del_pos_row.isHidden()
    # 单选：勾「从前数删除」会同时取消「开头N字符」，对应行随之收起
    assert not window.del_head.isChecked()
    assert window._del_cnt_row.isHidden()
    assert window._del_text_row.isHidden()

    assert window._add_pos_row.isHidden()
    window.add_pos.setChecked(True)
    assert not window._add_pos_row.isHidden()


def test_delete_content_row_only_shows_for_text_mode(window):
    """「内容」行只在勾「指定文本」时出现，其余四种模式都不显示。"""
    assert window._del_text_row.isHidden()

    window.del_text.setChecked(True)
    assert not window._del_text_row.isHidden()

    window.del_head.setChecked(True)          # 切到「开头N字符」
    assert not window.del_text.isChecked()
    assert window._del_text_row.isHidden()
    assert not window._del_cnt_row.isHidden()

    window.del_from_back.setChecked(True)     # 切到「从后数删除」
    assert window._del_text_row.isHidden()
    assert window._del_cnt_row.isHidden()
    assert not window._del_pos_row.isHidden()


def test_add_position_boxes_are_single_choice(window):
    """「添加」页的三个位置选项只能选一个。"""
    assert window.add_prefix.isChecked()

    window.add_suffix.setChecked(True)
    assert not window.add_prefix.isChecked()
    assert not window.add_pos.isChecked()
    assert window._add_pos_row.isHidden()

    window.add_pos.setChecked(True)
    assert not window.add_suffix.isChecked()
    assert not window.add_prefix.isChecked()
    assert not window._add_pos_row.isHidden()


def test_delete_modes_are_single_choice(window):
    """「删除」页的五种删除方式只能选一个，且允许全不选。"""
    window.del_text.setChecked(True)
    window.del_tail.setChecked(True)
    assert not window.del_text.isChecked()
    assert window.del_tail.isChecked()

    window.del_from_back.setChecked(True)
    assert not window.del_tail.isChecked()
    # 换成「从后数删除」后：字符数行收起，位置行展开
    assert window._del_cnt_row.isHidden()
    assert not window._del_pos_row.isHidden()

    # 允许全部取消，回到「什么都不删」的初始状态
    window.del_from_back.setChecked(False)
    boxes = (window.del_text, window.del_head, window.del_tail,
             window.del_from_front, window.del_from_back)
    assert not any(b.isChecked() for b in boxes)
    assert window._del_cnt_row.isHidden()
    assert window._del_pos_row.isHidden()


def test_add_prefix_is_checked_by_default(window):
    """原版「添加」页默认勾选「文件名前」。"""
    assert window.add_prefix.isChecked()
    assert not window.add_suffix.isChecked()
    assert not window.add_pos.isChecked()


def test_file_menu_keeps_only_open_and_add(window):
    """「文件」菜单只保留打开文件夹 / 添加文件，刷新与退出已移除。"""
    bar = window.menuBar()
    assert [a.text() for a in bar.actions()] == ["文件", "编辑", "视图", "帮助"]

    def items(index):
        menu = bar.actions()[index].menu()
        return [a.text() for a in menu.actions() if not a.isSeparator()]

    assert items(0) == ["打开文件夹", "添加文件"]
    assert "刷新" not in items(0)
    assert "退出" not in items(0)
    assert items(3) == ["检查更新", "关于"]


def test_number_format_menu_lists_four_templates(window):
    """「序号」页的格式下拉只列用户指定的 4 个模板，点选即填入输入框。"""
    from renamer.ui.main_window import FORMAT_PRESETS

    assert FORMAT_PRESETS == ["#_[原文件名]", "#-[原文件名]",
                              "#[原文件名]", "#"]
    actions = window.fmt_more_btn.menu().actions()
    assert [a.text() for a in actions] == FORMAT_PRESETS
    for action, template in zip(actions, FORMAT_PRESETS, strict=True):
        action.trigger()
        assert window.num_fmt.text() == template


def test_extension_is_normalised_to_lowercase(window, tmp_path):
    """「扩展名」页自动规范化输入，不再需要「转为小写」开关。"""
    assert not hasattr(window, "ext_lower")
    assert "ext_lower" not in window._settings()

    window.ext_new.setText("PNG")
    window._normalize_ext_input()
    assert window.ext_new.text() == "png"          # 输入框就地改正

    _seed(tmp_path, "a.png")
    window._add_paths([str(tmp_path)], reset=True)
    window.tabsel.setCurrentIndex(5)
    window.ext_new.setText("JPG")
    window.preview()
    assert window.files[0][2] == "a.jpg"


def test_normalize_ext_leaves_invalid_input_alone(window):
    """非法输入不改写输入框内容（执行时会被引擎忽略）。"""
    window.ext_new.setText("a/b")
    window._normalize_ext_input()
    assert window.ext_new.text() == "a/b"


def test_about_page_has_no_logo(window):
    """「关于」页只保留文字，不再显示图标图案。"""
    from PySide6.QtWidgets import QLabel

    page = window.tabsel.widget(window.tabsel.count() - 1)
    labels = page.findChildren(QLabel)
    assert not any(not lb.pixmap().isNull() for lb in labels)
    assert any("v" in lb.text() for lb in labels)


def test_dialogs_are_wide_enough(window):
    """确认 / 成功弹窗设了最小宽度，不会窄成一条缝。"""
    from renamer.ui.main_window import DIALOG_MIN_WIDTH, _message_box

    assert DIALOG_MIN_WIDTH >= 400
    box = _message_box(window, QMessageBox.Icon.Information,
                       "已完成", "完成！成功 3 个")
    try:
        box.show()
        QApplication.processEvents()
        # 注意：这里不能用 minimumWidth() 断言——QMessageBox 会无视它，
        # 真正撑开宽度的是布局里的弹簧，所以只能量实际宽度。
        assert box.width() >= DIALOG_MIN_WIDTH
    finally:
        box.close()


def test_case_conversion_is_not_reported_as_taken(window, tmp_path):
    """回归：大小写转换时目标路径其实就是文件自己。

    Windows 的文件名不区分大小写，早期实现直接拿 ``os.path.exists`` 判断，
    于是把 ``ABC.JPG`` 改成 ``abc.JPG`` 会被误报成「目标已存在」。
    """
    _seed(tmp_path, "ABC.JPG", "DEF.JPG")
    window._add_paths([str(tmp_path)], reset=True)
    window.tabsel.setCurrentIndex(4)              # 转换页
    window.case_mode.setCurrentText("全部小写")
    window.preview()
    assert [f[2] for f in window.files] == ["abc.JPG", "def.JPG"]
    assert [f[3] for f in window.files] == ["将重命名", "将重命名"]


# ------------------------------------------------------------------ 表格交互

def _select_rows(table, rows: list[int]) -> None:
    for r in rows:
        table.selectionModel().select(
            table.model().index(r, 0),
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows)


def test_table_columns_are_user_resizable(window):
    """回归：列宽必须能拖动调节，Stretch 模式下分界线是拖不动的。"""
    from PySide6.QtWidgets import QHeaderView

    header = window.table.horizontalHeader()
    for col in (1, 2, 3):
        assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.Interactive
    assert header.stretchLastSection()

    width = window.table.columnWidth(1)
    header.resizeSection(1, width + 40)
    assert window.table.columnWidth(1) == width + 40


def test_checkbox_click_applies_to_whole_selection(window, tmp_path):
    """回归：Shift 选中多行后点选择框，整个选区要一起勾/取消。"""
    from renamer.ui.file_table import COL_CHK

    _seed(tmp_path, "a.jpg", "b.jpg", "c.jpg", "d.jpg")
    window._add_paths([str(tmp_path)], reset=True)
    table = window.table

    _select_rows(table, [0, 1, 2])          # 模拟 Shift+点击后的选区
    table.chk_press_rows = [0, 1, 2]        # FileTable 在鼠标按下时记录
    table.item(0, COL_CHK).setCheckState(Qt.CheckState.Unchecked)

    assert [f[4] for f in window.files] == [False, False, False, True]
    # 选区在整表刷新后恢复
    assert sorted(i.row() for i in table.selectionModel().selectedRows()) == [0, 1, 2]


def test_checkbox_click_outside_selection_toggles_one_row(window, tmp_path):
    """点在选区外的选择框只影响那一行。"""
    from renamer.ui.file_table import COL_CHK

    _seed(tmp_path, "a.jpg", "b.jpg", "c.jpg")
    window._add_paths([str(tmp_path)], reset=True)
    table = window.table

    table.chk_press_rows = [1]
    table.item(1, COL_CHK).setCheckState(Qt.CheckState.Unchecked)
    assert [f[4] for f in window.files] == [True, False, True]


def test_drag_reorder_moves_data_and_table_together(window, tmp_path):
    """回归：行拖动必须搬数据并整表刷新，否则表格与数据错位（乱序）。"""
    from renamer.ui.file_table import COL_ORIG

    _seed(tmp_path, "a.jpg", "b.jpg", "c.jpg", "d.jpg")
    window._add_paths([str(tmp_path)], reset=True)

    window.table.reorder_requested.emit([1], 0)     # 把 b.jpg 拖到最上
    assert [f[1] for f in window.files] == ["b.jpg", "a.jpg", "c.jpg", "d.jpg"]
    assert window.table.item(0, COL_ORIG).text() == "b.jpg"

    window.table.reorder_requested.emit([0], 4)     # 再拖到最后
    assert [f[1] for f in window.files] == ["a.jpg", "c.jpg", "d.jpg", "b.jpg"]
    assert window.table.item(3, COL_ORIG).text() == "b.jpg"


# ------------------------------------------------------- 真实鼠标拖动（端到端）

def _show(window) -> None:
    """拖动要用 visualRect 算坐标，所以得让窗口真的有尺寸。"""
    window.resize(1200, 700)
    window.show()
    QApplication.processEvents()


def _row_pos(table, row: int, where: str = "center", col: int | None = None):
    from renamer.ui.file_table import COL_ORIG

    rect = table.visualRect(table.model().index(row, col if col is not None
                                                else COL_ORIG))
    if where == "top":
        return QPoint(rect.center().x(), rect.top() + 1)
    if where == "bottom":
        return QPoint(rect.center().x(), rect.bottom() - 1)
    return rect.center()


def _drag(table, src_row: int, dst_row: int, where: str = "top",
          col: int | None = None) -> None:
    """用真实鼠标事件拖一行（不用 Qt 的 DnD，所以 QTest 能直接驱动）。"""
    start = _row_pos(table, src_row, col=col)
    end = _row_pos(table, dst_row, where, col=col)
    QTest.mousePress(table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(table.viewport(), start + QPoint(0, -14))
    QTest.mouseMove(table.viewport(), end)
    QTest.mouseRelease(table.viewport(), Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, end)
    QApplication.processEvents()


def _seed_five(window, tmp_path) -> None:
    _seed(tmp_path, "a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg")
    window._add_paths([str(tmp_path)], reset=True)
    _show(window)


def test_mouse_drag_reorders_row(window, tmp_path):
    """把第 4 行拖到最前：数据与表格都要变，且该行保持选中。"""
    from renamer.ui.file_table import COL_ORIG

    _seed_five(window, tmp_path)
    _drag(window.table, 3, 0, "top")

    assert [f[1] for f in window.files] == ["d.jpg", "a.jpg", "b.jpg",
                                           "c.jpg", "e.jpg"]
    assert [window.table.item(r, COL_ORIG).text()
            for r in range(window.table.rowCount())] == [f[1] for f in window.files]
    assert [i.row() for i in window.table.selectionModel().selectedRows()] == [0]


def test_mouse_drag_inserts_after_target_row(window, tmp_path):
    """拖到某行下半部 → 插到该行之后（中间插入）。"""
    _seed_five(window, tmp_path)
    _drag(window.table, 1, 3, "bottom")
    assert [f[1] for f in window.files] == ["a.jpg", "c.jpg", "d.jpg",
                                           "b.jpg", "e.jpg"]


def test_mouse_drag_moves_all_selected_rows(window, tmp_path):
    """选中多行时，拖动其中一行会把整个选区一起搬走。"""
    _seed_five(window, tmp_path)
    window.table.select_rows([0, 1])
    QApplication.processEvents()
    _drag(window.table, 0, 4, "bottom")
    assert [f[1] for f in window.files] == ["c.jpg", "d.jpg", "e.jpg",
                                           "a.jpg", "b.jpg"]


def test_mouse_drag_ignored_when_draggable_unchecked(window, tmp_path):
    """「可拖动」取消勾选后，拖动不应产生任何变化。"""
    _seed_five(window, tmp_path)
    window.chk_drag.setChecked(False)
    QApplication.processEvents()

    before = [f[1] for f in window.files]
    _drag(window.table, 3, 0, "top")
    assert [f[1] for f in window.files] == before


def test_click_on_checkbox_indicator_only_toggles(window, tmp_path):
    """点在勾选小方框上：只切换勾选，绝不重排。"""
    from renamer.ui.file_table import COL_CHK

    _seed_five(window, tmp_path)
    before = [f[1] for f in window.files]

    QTest.mouseClick(window.table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier,
                     _row_pos(window.table, 0, col=COL_CHK))
    QApplication.processEvents()

    assert [f[1] for f in window.files] == before
    assert window.files[0][4] is False


def test_drag_started_from_checkbox_cell_blank_area(window, tmp_path):
    """选择框列的空白处（不在小方框上）可以直接拖动该行。"""
    from renamer.ui.file_table import COL_CHK

    _seed_five(window, tmp_path)
    box = _row_pos(window.table, 4, col=COL_CHK)
    start = QPoint(box.x() - 18, box.y())
    assert start.x() >= 0

    QTest.mousePress(window.table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(window.table.viewport(), start + QPoint(0, -14))
    QTest.mouseMove(window.table.viewport(), _row_pos(window.table, 0, "top"))
    QTest.mouseRelease(window.table.viewport(), Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier,
                       _row_pos(window.table, 0, "top"))
    QApplication.processEvents()

    assert window.files[0][1] == "e.jpg"


def test_drag_from_checkbox_indicator_does_not_reorder(window, tmp_path):
    """按在小方框上再拖出去，仍按「勾选」处理，不重排。"""
    from renamer.ui.file_table import COL_CHK

    _seed_five(window, tmp_path)
    before = [f[1] for f in window.files]
    start = _row_pos(window.table, 1, col=COL_CHK)

    QTest.mousePress(window.table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(window.table.viewport(),
                    _row_pos(window.table, 4, "bottom"))
    QTest.mouseRelease(window.table.viewport(), Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier,
                       _row_pos(window.table, 4, "bottom"))
    QApplication.processEvents()

    assert [f[1] for f in window.files] == before


def test_drag_indicator_line_is_painted(window, tmp_path):
    """拖动过程中要画出插入指示线（颜色取自主题强调色）。"""
    from PySide6.QtCore import QPoint as _QPoint

    _seed_five(window, tmp_path)
    table = window.table
    # 拖到中间位置，线不会贴在视口边缘
    press = _row_pos(table, 1)
    target = _row_pos(table, 3, "top")
    QTest.mousePress(table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, press)
    QTest.mouseMove(table.viewport(), press + _QPoint(0, -14))
    QTest.mouseMove(table.viewport(), target)
    QApplication.processEvents()

    assert table._drag_rows and table._drop_target >= 0
    image = table.viewport().grab().toImage()
    accent = QColor(table.indicator_color)
    line_found = False
    for y in range(image.height()):
        color = image.pixelColor(image.width() // 2, y)
        if (abs(color.red() - accent.red()) < 30
                and abs(color.green() - accent.green()) < 30
                and abs(color.blue() - accent.blue()) < 30):
            line_found = True
            break
    QTest.mouseRelease(table.viewport(), Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, target)
    assert line_found, "拖动时没有画出插入指示线"


def test_external_file_drop_is_handled(window, tmp_path):
    """外部文件拖进表格：走 files_dropped 信号追加，而不是 Qt 自己处理。"""
    _seed(tmp_path, "x.jpg", "y.jpg")
    window.table.files_dropped.emit([str(tmp_path / "x.jpg"),
                                     str(tmp_path / "y.jpg")])
    assert [f[1] for f in window.files] == ["x.jpg", "y.jpg"]


def test_table_does_not_draw_focus_rect(window, tmp_path, monkeypatch):
    """回归：单元格不再画虚线焦点框（委托把焦点状态从绘制选项里剥掉）。"""
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import (
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
    )

    from renamer.ui.file_table import NoFocusDelegate

    assert isinstance(window.table.itemDelegate(), NoFocusDelegate)

    # 拦下 QStyledItemDelegate.paint，看 NoFocusDelegate 传下来的选项
    captured: dict[str, bool] = {}

    def spy_paint(self, painter, option, index):
        captured["has_focus"] = bool(
            option.state & QStyle.StateFlag.State_HasFocus)

    monkeypatch.setattr(QStyledItemDelegate, "paint", spy_paint)
    opt = QStyleOptionViewItem()
    opt.state |= QStyle.StateFlag.State_HasFocus
    NoFocusDelegate().paint(None, opt, QModelIndex())
    assert captured["has_focus"] is False

    # 表格能用键盘移动当前单元格（视图本身仍保有焦点）
    _seed(tmp_path, "a.jpg")
    window._add_paths([str(tmp_path)], reset=True)
    window.table.setFocus()
    window.table.setCurrentCell(0, 1)
    assert window.table.currentRow() == 0


# ------------------------------------------------------------------ 检查更新

def test_update_reports_already_latest(window, auto_yes):
    from renamer import __version__
    from renamer.update import Release

    window._on_update_checked(
        Release(f"v{__version__}", "https://example.com", "n", ""), "")
    assert "已是最新版本" in window.status_label.text()


def test_update_offers_to_open_download_page(window, auto_yes, monkeypatch):
    """有新版本时询问是否跳转下载页，选「是」就真的打开链接。"""
    from renamer.ui import main_window as mw
    from renamer.update import Release

    opened: list[str] = []

    class _FakeDesktop:
        @staticmethod
        def openUrl(url):        # noqa: N802 (Qt 命名)
            opened.append(url.toString())

    monkeypatch.setattr(mw, "QDesktopServices", _FakeDesktop)

    window._on_update_checked(
        Release("v99.0.0", "https://example.com/dl", "99", ""), "")
    assert "发现新版本" in window.status_label.text()
    assert opened == ["https://example.com/dl"]


def test_update_error_is_shown_not_raised(window, auto_yes):
    window._on_update_checked(None, "无法连接更新服务器（超时）")
    assert window.status_label.text() == "检查更新失败"


def test_update_handles_empty_release_list(window, auto_yes):
    window._on_update_checked(None, "")
    assert window.status_label.text() == "暂无发布版本"


# ------------------------------------------------------------------ 工作流

def test_preview_builds_plan(window, tmp_path):
    _seed(tmp_path, "a.jpg", "b.jpg")
    window._add_paths([str(tmp_path)])
    assert len(window.files) == 2

    window.num_fmt.setText("#")
    window.num_digits.setValue(2)
    window.preview()
    assert [f[3] for f in window.files] == ["将重命名", "将重命名"]
    assert [f[2] for f in window.files] == ["01.jpg", "02.jpg"]


def test_execute_then_undo_restores_list_state(window, tmp_path, auto_yes):
    """回归：撤销后列表的路径与名称必须回到原样，否则后续操作全部失效。"""
    _seed(tmp_path, "a.jpg", "b.jpg", "c.jpg")
    window._add_paths([str(tmp_path)], reset=True)
    window.num_fmt.setText("#")
    window.num_digits.setValue(2)

    window.preview()
    window.execute()
    assert sorted(os.listdir(tmp_path)) == ["01.jpg", "02.jpg", "03.jpg"]
    assert all(os.path.exists(f[0]) for f in window.files)

    window.undo_rename()
    assert sorted(os.listdir(tmp_path)) == ["a.jpg", "b.jpg", "c.jpg"]
    assert [f[1] for f in window.files] == ["a.jpg", "b.jpg", "c.jpg"]
    assert all(os.path.exists(f[0]) for f in window.files)


def test_preview_and_execute_work_again_after_undo(window, tmp_path, auto_yes):
    """回归：撤销之后必须还能再预览并执行一次。"""
    _seed(tmp_path, "a.jpg", "b.jpg")
    window._add_paths([str(tmp_path)], reset=True)
    window.num_fmt.setText("#")
    window.num_digits.setValue(2)

    window.preview()
    window.execute()
    window.undo_rename()

    window.preview()
    window.execute()
    assert sorted(os.listdir(tmp_path)) == ["01.jpg", "02.jpg"]


def test_existing_target_is_flagged_before_execute(window, tmp_path, auto_yes):
    """回归：目标名已被占用时，预览就要标出来，而不是执行时弹一堆报错。"""
    _seed(tmp_path, "m.txt", "n.txt")
    window._add_paths([str(tmp_path / "m.txt")], reset=True)
    window.tabsel.setCurrentIndex(6)
    window.other_entry.setText("n")
    window.preview()
    assert window.files[0][3] == "目标已存在"


def test_unchecking_all_marks_everything_same(window, tmp_path):
    _seed(tmp_path, "a.jpg", "b.jpg")
    window._add_paths([str(tmp_path)], reset=True)
    window.chk_all.setChecked(False)
    assert all(not f[4] for f in window.files)
    window.preview()
    assert all(f[3] == "不变" for f in window.files)
