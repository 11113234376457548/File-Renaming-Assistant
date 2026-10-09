"""改名引擎单元测试。

用例按下述缺陷编号组织（编号沿用仓库 docs/缺陷分析报告.md）：

==================  ==========================================
编号                 缺陷
==================  ==========================================
B1                   随机编号位数失控
B2                   位数输入框留空导致闪退
B3                   指定文本删除误删扩展名
B4                   开头 / 结尾删除超额产生空文件名
B5                   从后数删除位置越界时误删首字符
B6                   跨目录同名被误判为冲突
B7                   大小写转换破坏扩展名
B8                   序号跳号（未勾选项占号）
B9                   交换名执行失败
B10                  撤销记录的是临时名
B11                  非法文件名未被拦截
==================  ==========================================
"""

from __future__ import annotations

import pytest

from renamer.core import (
    CASE_LOWER,
    CASE_TITLE,
    CASE_UPPER,
    RenameEngine,
    make_number,
    natural_sort_key,
    normalize_ext,
    safe_int,
    split_name,
    validate_name,
)

# ------------------------------------------------------------------ 工具函数

@pytest.mark.parametrize("name,expected", [
    ("a.tar.gz", ("a.tar", ".gz")),
    ("noext", ("noext", "")),
    ("a.jpg", ("a", ".jpg")),
])
def test_split_name(name, expected):
    assert split_name(name) == expected


def test_natural_sort_orders_numbers_numerically():
    names = ["img10", "img2", "img1", "img20"]
    assert sorted(names, key=natural_sort_key) == ["img1", "img2", "img10", "img20"]


# ------------------------------------------------------------------ B2 safe_int

@pytest.mark.parametrize("raw,expected", [
    ("", 3), ("   ", 3), ("abc", 3), (None, 3), ("5", 5), (7, 7),
    ("-5", 0), ("999", 20),
])
def test_safe_int_never_raises(raw, expected):
    """B2：空串 / None / 非数字 / 越界输入都必须降级而非抛异常。"""
    assert safe_int(raw, 3, lo=0, hi=20) == expected


def test_safe_int_negative_digits_downgrades():
    """B2：-5 低于下限 0，降级为 0。"""
    assert safe_int("-5", 3, lo=0, hi=20) == 0


class TestB2EmptyDigits:
    """B2：位数留空/非法时不得崩溃，且降级为默认位数。"""

    @pytest.mark.parametrize("raw", ["", "abc", None])
    def test_defaults_to_three(self, make_settings, raw):
        engine = RenameEngine(make_settings(tab=0, num_fmt="#", num_digits=raw))
        assert engine.new_name("a.jpg", 0) == "001.jpg"

    def test_negative_becomes_zero_padding(self, make_settings):
        engine = RenameEngine(make_settings(tab=0, num_fmt="#", num_digits="-5"))
        assert engine.new_name("a.jpg", 0) == "1.jpg"


# ------------------------------------------------------------------ B1 随机编号

def test_b1_random_number_respects_pad(make_settings):
    """B1：位数设为 2，随机编号必须恰好 2 位。"""
    engine = RenameEngine(make_settings(
        tab=0, num_fmt="IMG_#", num_digits=2, num_random=True))
    for i in range(300):
        result = engine.new_name("a.jpg", i)
        digits = result[len("IMG_"):-len(".jpg")]
        assert len(digits) == 2, f"第 {i} 次生成了 {digits!r}"


@pytest.mark.parametrize("pad,expected", [(0, "7"), (2, "07"), (4, "0007")])
def test_make_number_padding(pad, expected):
    assert make_number(7, pad) == expected


# ------------------------------------------------------------------ B3 指定文本删除

class TestB3DeleteText:
    def test_keyword_in_extension_keeps_ext(self, make_settings):
        """B3：删除 'jpg' 不得伤及扩展名。"""
        engine = RenameEngine(make_settings(
            tab=2, del_text=True, del_entry="jpg"))
        assert engine.new_name("abc.jpg", 0) == "abc.jpg"

    def test_keyword_in_stem(self, make_settings):
        engine = RenameEngine(make_settings(
            tab=2, del_text=True, del_entry="IMG"))
        assert engine.new_name("IMG_001.jpg", 0) == "_001.jpg"

    def test_keyword_absent(self, make_settings):
        engine = RenameEngine(make_settings(
            tab=2, del_text=True, del_entry="不存在"))
        assert engine.new_name("abc.jpg", 0) == "abc.jpg"


# ------------------------------------------------------------------ B4 超额删除

class TestB4HeadTailDelete:
    @pytest.mark.parametrize("mode,count,expected", [
        ("del_head", 20, "abcdefgh.jpg"),
        ("del_tail", 20, "abcdefgh.jpg"),
        ("del_head", 0, "abcdefgh.jpg"),
        ("del_tail", 0, "abcdefgh.jpg"),
        ("del_head", 3, "defgh.jpg"),
        ("del_tail", 3, "abcde.jpg"),
    ])
    def test_delete(self, make_settings, mode, count, expected):
        """B4：超额或零删除不得产出空主体，正常区间结果一致。"""
        engine = RenameEngine(make_settings(
            tab=2, del_cnt=count, **{mode: True}))
        assert engine.new_name("abcdefgh.jpg", 0) == expected


# ------------------------------------------------------------------ B5 从后数删除

class TestB5DeleteFromBack:
    @pytest.mark.parametrize("pos_from,cnt,expected", [
        (1, 1, "abcdefg.jpg"),
        (2, 3, "abcdh.jpg"),
        (7, 2, "cdefgh.jpg"),
        (8, 2, "bcdefgh.jpg"),
        (9, 2, "abcdefgh.jpg"),      # 越界 -> 不执行
        (99, 2, "abcdefgh.jpg"),     # 越界 -> 不执行
    ])
    def test_delete_from_back(self, make_settings, pos_from, cnt, expected):
        """B5：位置越界时应返回原名，而非误删首字符。"""
        engine = RenameEngine(make_settings(
            tab=2, del_from_back=True, del_pos_from=pos_from, del_pos_cnt=cnt))
        assert engine.new_name("abcdefgh.jpg", 0) == expected

    def test_delete_from_front(self, make_settings):
        engine = RenameEngine(make_settings(
            tab=2, del_from_front=True, del_pos_from=2, del_pos_cnt=3))
        assert engine.new_name("abcdefgh.jpg", 0) == "aefgh.jpg"


# ------------------------------------------------------------------ B7 大小写

@pytest.mark.parametrize("mode,source,expected", [
    (CASE_LOWER, "ABC.JPG", "abc.JPG"),
    (CASE_UPPER, "abc.jpg", "ABC.jpg"),
    (CASE_TITLE, "abc.jpg", "Abc.jpg"),
])
def test_b7_case_never_touches_extension(make_settings, mode, source, expected):
    """B7：三种模式都只改主体，扩展名原样保留。"""
    engine = RenameEngine(make_settings(tab=4, case_mode=mode))
    assert engine.new_name(source, 0) == expected


# ------------------------------------------------------------------ 其它功能页

def test_add_prefix_and_suffix(make_settings):
    assert RenameEngine(make_settings(
        tab=1, add_text="p_", add_prefix=True)).new_name("a.txt", 0) == "p_a.txt"
    assert RenameEngine(make_settings(
        tab=1, add_text="_s", add_suffix=True)).new_name("a.txt", 0) == "a_s.txt"


def test_add_prefix_and_suffix_combine(make_settings):
    """同时勾选「文件名前」和「文件名后」时，两端都要插入。

    这里用「-」而不是「*」：后者是 Windows 非法字符，会被 B11 安全闸拦下。
    """
    engine = RenameEngine(make_settings(
        tab=1, add_text="-", add_prefix=True, add_suffix=True))
    assert engine.new_name("a.txt", 0) == "-a-.txt"


def test_add_position_needs_add_pos_checked(make_settings):
    """仅填了位置却没勾选「指定位置」时不应偷偷插入（历史缺陷）。"""
    engine = RenameEngine(make_settings(
        tab=1, add_text="-", add_prefix=False, add_suffix=False,
        add_pos=False, add_pos_idx=2))
    assert engine.new_name("abcd.txt", 0) == "abcd.txt"


def test_add_at_position(make_settings):
    engine = RenameEngine(make_settings(
        tab=1, add_text="-", add_prefix=False, add_suffix=False,
        add_pos=True, add_pos_idx=2))
    assert engine.new_name("abcd.txt", 0) == "ab-cd.txt"


def test_add_empty_text_is_noop(make_settings):
    """内容为空时无论勾选什么都不得改动文件名。"""
    engine = RenameEngine(make_settings(
        tab=1, add_text="", add_prefix=True, add_suffix=True, add_pos=True))
    assert engine.new_name("a.txt", 0) == "a.txt"


def test_replace_plain_is_case_insensitive_by_default(make_settings):
    engine = RenameEngine(make_settings(
        tab=3, rep_find="AB", rep_to="X", rep_case=False))
    assert engine.new_name("abab.txt", 0) == "XX.txt"


def test_replace_case_sensitive(make_settings):
    engine = RenameEngine(make_settings(
        tab=3, rep_find="AB", rep_to="X", rep_case=True))
    assert engine.new_name("abAB.txt", 0) == "abX.txt"


def test_replace_regex_invalid_pattern_falls_back(make_settings):
    engine = RenameEngine(make_settings(
        tab=3, rep_find="([", rep_to="X", rep_regex=True))
    assert engine.new_name("abc.txt", 0) == "abc.txt"


@pytest.mark.parametrize("raw,expected", [
    ("PNG", "png"),
    (".JpG", "jpg"),
    ("  png  ", "png"),
    ("tar.gz", ""),              # 含点号（非前导）—— 不是合理的扩展名
    ("a/b", ""),                 # 含非法字符
    ("", ""),
    ("A" * 20, ""),              # 超过 15 字符
])
def test_normalize_ext(raw, expected):
    assert normalize_ext(raw) == expected


def test_change_extension(make_settings):
    """输入会规范化：大写与多余点号都会被改正。"""
    engine = RenameEngine(make_settings(tab=5, ext_new="JPEG"))
    assert engine.new_name("a.JPG", 0) == "a.jpeg"
    engine = RenameEngine(make_settings(tab=5, ext_new=".PNG"))
    assert engine.new_name("a.png", 0) == "a.png"


def test_change_extension_invalid_is_ignored(make_settings):
    engine = RenameEngine(make_settings(tab=5, ext_new="a/b"))
    assert engine.new_name("a.jpg", 0) == "a.jpg"


def test_sequential_naming(make_settings):
    engine = RenameEngine(make_settings(tab=6, other_entry="张三 李四"))
    assert engine.new_name("a.jpg", 0) == "张三.jpg"
    assert engine.new_name("b.jpg", 1) == "李四.jpg"
    assert engine.new_name("c.jpg", 2) == "c.jpg"     # 名称用尽 -> 保持原名


def test_number_end_limit_returns_none(make_settings):
    """超过「截止」时返回 None，供 plan 标记为『超过截止』。"""
    engine = RenameEngine(make_settings(
        tab=0, num_fmt="#", num_start=1, num_step=1, num_end=2, num_digits=1))
    assert engine.new_name("a.jpg", 0) == "1.jpg"
    assert engine.new_name("b.jpg", 1) == "2.jpg"
    assert engine.new_name("c.jpg", 2) is None


# ------------------------------------------------------------------ B11 安全闸

class TestB11ValidateName:
    @pytest.mark.parametrize("name", [
        "", ".", "..", ".jpg", "end.", "a/b.jpg", "x<y.txt",
        "a:b.txt", "CON.txt", "com1.txt", "aux", "a" * 300 + ".txt",
    ])
    def test_rejects(self, name):
        ok, reason = validate_name(name)
        assert not ok, f"{name!r} 本应被拒绝（{reason}）"

    @pytest.mark.parametrize("name", [
        "正常文件.txt", "正常 文件.jpg", "a.tar.gz", "报告-v2.pdf",
    ])
    def test_accepts(self, name):
        ok, reason = validate_name(name)
        assert ok, f"{name!r} 本应通过，却报：{reason}"


def test_b11_pipeline_blocks_illegal_result(make_settings):
    """B11：生成含非法字符的名字时，安全闸应退回原名。"""
    engine = RenameEngine(make_settings(tab=1, add_text="?", add_prefix=True))
    assert engine.new_name("a.jpg", 0) == "a.jpg"


def test_b11_blocks_emptied_stem(make_settings):
    engine = RenameEngine(make_settings(tab=2, del_text=True, del_entry="abc"))
    assert engine.new_name("abc.jpg", 0) == "abc.jpg"
