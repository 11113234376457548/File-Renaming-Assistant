"""计划 / 执行 / 撤销 的集成测试（B6、B8、B9、B10）。"""

from __future__ import annotations

from renamer.core import (
    STATUS_CONFLICT,
    STATUS_RENAME,
    STATUS_SAME,
    STATUS_TAKEN,
    RenameEngine,
    apply_rename,
    plan_rename,
    undo,
)


def _touch(path, content: str = "") -> str:
    path.write_text(content, encoding="utf-8")
    return str(path)


def _fs_is_case_insensitive(tmp_path) -> bool:
    """探测当前文件系统是否不区分大小写（Windows / macOS 默认为真）。

    引擎判定「目标是否已被占用」用的是 ``normcase(abspath(...))``，
    在 Windows 上 ``b.txt`` 与 ``B.txt`` 会归一成同一个键，在 Linux 上
    则是两个不同的文件——这是**平台语义**而非缺陷，所以相关用例要按
    文件系统能力分平台断言，否则 CI 的 Linux 任务必然红。
    """
    probe = tmp_path / "CaseProbe.tmp"
    probe.write_text("x", encoding="utf-8")
    try:
        return (tmp_path / "caseprobe.TMP").exists()
    finally:
        probe.unlink()


# ------------------------------------------------------------------ B6 冲突检测

class TestB6ConflictDetection:
    def test_same_name_in_different_dirs_both_pass(self, make_settings, tmp_path):
        """B6：不同文件夹下的同名文件可以共存，不应误判冲突。"""
        dir_a = tmp_path / "A"
        dir_b = tmp_path / "B"
        dir_a.mkdir()
        dir_b.mkdir()
        fa = _touch(dir_a / "x.jpg")
        fb = _touch(dir_b / "y.jpg")

        engine = RenameEngine(make_settings(tab=0, num_fmt="固定名"))
        plan = plan_rename([(fa, "x.jpg", True), (fb, "y.jpg", True)], engine)
        assert [p[3] for p in plan] == [STATUS_RENAME, STATUS_RENAME]

    def test_real_conflict_in_same_dir_is_blocked(self, make_settings, tmp_path):
        """B6：同一目录内目标名重复时，第二个应被判为冲突。"""
        fa = _touch(tmp_path / "a.jpg")
        fb = _touch(tmp_path / "b.jpg")

        engine = RenameEngine(make_settings(tab=0, num_fmt="固定名"))
        plan = plan_rename([(fa, "a.jpg", True), (fb, "b.jpg", True)], engine)
        assert [p[3] for p in plan] == [STATUS_RENAME, STATUS_CONFLICT]

    def test_unchecked_items_are_marked_same(self, make_settings, tmp_path):
        fa = _touch(tmp_path / "a.jpg")
        engine = RenameEngine(make_settings(tab=0, num_fmt="#"))
        plan = plan_rename([(fa, "a.jpg", False)], engine)
        assert plan[0][3] == STATUS_SAME


class TestExistingTargetDetection:
    """目标名已被磁盘上的其它文件占用时，必须在预览阶段就拦下来。"""

    def test_target_taken_by_outsider(self, make_settings, tmp_path):
        fa = _touch(tmp_path / "a.txt", "a")
        _touch(tmp_path / "b.txt", "b")          # 不在本批次里
        plan = plan_rename(
            [(fa, "a.txt", True)],
            RenameEngine(make_settings(tab=6, other_entry="b")))
        assert plan[0][3] == STATUS_TAKEN

    def test_target_taken_by_same_name_other_case(self, make_settings, tmp_path):
        """不区分大小写的文件系统上，``b.txt`` 会被盘上的 ``B.txt`` 挡住。

        Linux 区分大小写，两者是两个不同的文件，改名理应放行——所以
        这里按文件系统能力分平台断言，而不是无脑认定必须冲突。
        """
        fa = _touch(tmp_path / "a.txt", "a")
        _touch(tmp_path / "B.txt", "b")
        plan = plan_rename(
            [(fa, "a.txt", True)],
            RenameEngine(make_settings(tab=6, other_entry="b")))
        expected = STATUS_TAKEN if _fs_is_case_insensitive(tmp_path) else STATUS_RENAME
        assert plan[0][3] == expected

    def test_swap_is_not_taken(self, make_settings, tmp_path):
        """交换名中目标虽已存在，但会被本批次让出来，不算冲突。"""
        fa = _touch(tmp_path / "a.jpg", "a")
        fb = _touch(tmp_path / "b.jpg", "b")
        plan = plan_rename(
            [(fa, "a.jpg", True), (fb, "b.jpg", True)],
            RenameEngine(make_settings(tab=6, other_entry="b a")))
        assert [p[3] for p in plan] == [STATUS_RENAME, STATUS_RENAME]

    def test_unchecked_outsider_still_blocks(self, make_settings, tmp_path):
        """同名文件在列表里但没勾选 -> 它不会被让出来，仍是冲突。"""
        fa = _touch(tmp_path / "a.txt", "a")
        fb = _touch(tmp_path / "b.txt", "b")
        plan = plan_rename(
            [(fa, "a.txt", True), (fb, "b.txt", False)],
            RenameEngine(make_settings(tab=6, other_entry="b")))
        assert plan[0][3] == STATUS_TAKEN


# ------------------------------------------------------------------ B8 序号连续

def test_b8_sequence_counts_only_checked(make_settings, tmp_path):
    """B8：未勾选的文件不占序号，编号保持连续。"""
    items = []
    for name, checked in [("a", False), ("b", True), ("c", False), ("d", True)]:
        items.append((_touch(tmp_path / f"{name}.jpg"), f"{name}.jpg", checked))

    engine = RenameEngine(make_settings(tab=0, num_fmt="#", num_digits=2))
    plan = plan_rename(items, engine)
    numbers = [p[2] for p in plan if p[3] == STATUS_RENAME]
    assert numbers == ["01.jpg", "02.jpg"]


# ------------------------------------------------------------------ B9 / B10 执行与撤销

class TestB9SwapNames:
    def test_swap_succeeds(self, make_settings, tmp_path):
        """B9：A→B 且 B→A 的交换名必须全部成功，且内容不串位。"""
        fa = _touch(tmp_path / "A.txt", "content-A")
        fb = _touch(tmp_path / "B.txt", "content-B")

        plan = [(fa, "A.txt", "B.txt", STATUS_RENAME),
                (fb, "B.txt", "A.txt", STATUS_RENAME)]
        history: list = []
        ok, errors = apply_rename(plan, history)

        assert ok == 2 and errors == []
        assert (tmp_path / "A.txt").read_text(encoding="utf-8") == "content-B"
        assert (tmp_path / "B.txt").read_text(encoding="utf-8") == "content-A"

    def test_undo_restores_original_names(self, tmp_path):
        """B10：撤销后必须还原为原名，不得残留临时名。"""
        fa = _touch(tmp_path / "A.txt", "content-A")
        fb = _touch(tmp_path / "B.txt", "content-B")
        plan = [(fa, "A.txt", "B.txt", STATUS_RENAME),
                (fb, "B.txt", "A.txt", STATUS_RENAME)]
        history: list = []
        apply_rename(plan, history)

        ok, fail = undo(history)
        assert (ok, fail) == (2, 0)
        assert (tmp_path / "A.txt").read_text(encoding="utf-8") == "content-A"
        assert (tmp_path / "B.txt").read_text(encoding="utf-8") == "content-B"
        assert not any(p.name.startswith(".renamer_")
                       for p in tmp_path.iterdir())

    def test_history_records_final_not_temp_name(self, tmp_path):
        """B10：history 记录的是最终名与原路径，而非临时名。"""
        fa = _touch(tmp_path / "A.txt")
        plan = [(fa, "A.txt", "B.txt", STATUS_RENAME)]
        history: list = []
        apply_rename(plan, history)
        assert history == [(str(tmp_path / "B.txt"), str(tmp_path / "A.txt"))]


def test_apply_reports_existing_target(tmp_path):
    """目标文件已存在且不属于本批次时应报错，且不改动任何文件。"""
    fa = _touch(tmp_path / "a.txt", "a")
    _touch(tmp_path / "b.txt", "b")
    plan = [(fa, "a.txt", "b.txt", STATUS_RENAME)]
    history: list = []
    ok, errors = apply_rename(plan, history)

    assert ok == 0
    assert errors and errors[0][2] == "目标已存在"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "a"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "b"


def test_apply_ignores_same_and_conflict_items(tmp_path):
    fa = _touch(tmp_path / "a.txt")
    plan = [(fa, "a.txt", "a.txt", STATUS_SAME),
            (fa, "a.txt", "x.txt", STATUS_CONFLICT)]
    ok, errors = apply_rename(plan, [])
    assert (ok, errors) == (0, [])


def test_undo_with_empty_history(tmp_path):
    assert undo([]) == (0, 0)
