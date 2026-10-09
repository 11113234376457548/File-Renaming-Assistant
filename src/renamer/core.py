"""批量重命名核心引擎。

本模块是纯逻辑实现，**不依赖任何 GUI 框架**，因此可以独立测试、
独立集成，也可以在命令行中直接调用。

设计要点
--------
1. 七个功能页（序号 / 添加 / 删除 / 替换 / 转换 / 扩展名 / 其他）各有一个
   私有方法，签名统一为 ``(orig, base, ext, idx) -> str | None``。
2. :meth:`RenameEngine.new_name` 是唯一出口，负责在返回前做一次
   “安全闸”——非法文件名（含非法字符、主体为空、系统保留名……）一律
   退回原名，避免生成 ``.jpg`` 这类在资源管理器中“消失”的文件。
3. 计划与执行分离：:func:`plan_rename` 只计算不动盘，
   :func:`apply_rename` 用两阶段提交真正落盘，天然支持交换名
   （``A→B`` 且 ``B→A``）并能整体回滚；:func:`undo` 负责撤销。
"""

from __future__ import annotations

import os
import random
import re
from collections.abc import Iterable, Sequence
from typing import Any

__all__ = [
    "STATUS_RENAME",
    "STATUS_SAME",
    "STATUS_OVER",
    "STATUS_CONFLICT",
    "STATUS_TAKEN",
    "DEFAULT_SETTINGS",
    "RenameEngine",
    "normalize_ext",
    "split_name",
    "validate_name",
    "safe_int",
    "make_number",
    "natural_sort_key",
    "plan_rename",
    "apply_rename",
    "undo",
]

# ------------------------------------------------------------------ 常量

#: 预览状态：将被重命名
STATUS_RENAME = "将重命名"
#: 预览状态：新旧同名，无需改动
STATUS_SAME = "不变"
#: 预览状态：序号超过「截止」上限
STATUS_OVER = "超过截止"
#: 预览状态：同目录内目标名与本批次其他文件冲突
STATUS_CONFLICT = "重名冲突"
#: 预览状态：目标名在磁盘上已被别的文件占用
STATUS_TAKEN = "目标已存在"

#: 与界面一一对应的默认设置。UI 与测试共用，避免两处默认值漂移。
DEFAULT_SETTINGS: dict[str, Any] = {
    "tab": 0,
    "num_fmt": "#",
    "num_start": 1,
    "num_step": 1,
    "num_end": 0,
    "num_digits": 3,
    "num_random": False,
    "add_text": "",
    # 注意：引擎侧的默认值保持「全部不勾选」，界面上的默认勾选由 UI 负责，
    # 这样引擎的默认行为永远是可预测的 no-op。
    "add_prefix": False,
    "add_suffix": False,
    "add_pos": False,
    "add_pos_idx": 1,
    "del_text": False,
    "del_entry": "",
    "del_head": False,
    "del_tail": False,
    "del_from_front": False,
    "del_from_back": False,
    "del_cnt": 0,
    "del_pos_from": 1,
    "del_pos_cnt": 1,
    "rep_find": "",
    "rep_to": "",
    "rep_regex": False,
    "rep_case": False,
    "case_mode": "全部小写",
    "ext_new": "",          # 会被 :func:`normalize_ext` 规范化后再使用
    "other_entry": "",
}

CASE_LOWER = "全部小写"
CASE_UPPER = "全部大写"
CASE_TITLE = "首字母大写"

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


# ------------------------------------------------------------------ 工具函数

def split_name(name: str) -> tuple[str, str]:
    """把文件名拆成 ``(主体, 扩展名)``。扩展名含点；无扩展名时返回 ``''``。

    >>> split_name('a.tar.gz')
    ('a.tar', '.gz')
    """
    return os.path.splitext(name)


def natural_sort_key(text: str) -> list[Any]:
    """自然排序键：``img2`` 排在 ``img10`` 之前。"""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", text)]


def _norm_path(path: str) -> str:
    """把路径归一化成「同一文件即同一字符串」的形式用于比较。

    在 Windows 上 ``normcase`` 会转小写并把 ``/`` 换成 ``\\``，于是
    ``abc.JPG`` 与 ``ABC.JPG`` 被视为同一个文件；在 POSIX 上它什么都不做，
    也就自然保持了大小写敏感的语义。所有「这个目标是不是已经存在 /
    是不是本批次自己让出来的」判断都必须走这里。
    """
    return os.path.normcase(os.path.abspath(path))


def normalize_ext(text: Any) -> str:
    """把用户输入的扩展名规范化成「合理」的形式。

    规则：去掉首尾空白与前导点号，统一转小写；剩下的内容必须全部是
    字母 / 数字 / 下划线 且不超过 15 个字符，否则返回空串表示**输入无效**。

    这样 ``PNG``、``.PNG``、``" png "`` 都会落到 ``png``，
    而 ``a/b`` 这类含非法字符的输入会被判为无效（调用方通常选择不修改）。

    >>> normalize_ext("PNG")
    'png'
    >>> normalize_ext(".JpG")
    'jpg'
    >>> normalize_ext("a/b")
    ''
    """
    cleaned = str(text or "").strip().lstrip(".").lower()
    return cleaned if re.fullmatch(r"\w{1,15}", cleaned, re.UNICODE) else ""


def validate_name(name: str) -> tuple[bool, str]:
    """校验是否为合法的 Windows 文件名。

    返回 ``(是否合法, 原因)``；合法时原因为空串。
    覆盖：空名、非法字符、结尾句点、主体为空（``.jpg``）、系统保留名、
    长度超限。
    """
    if not name or name in (".", ".."):
        return False, "文件名为空"
    bad = _INVALID_CHARS.search(name)
    if bad:
        return False, f"包含非法字符 {bad.group()!r}"
    if name.rstrip(".") != name:
        return False, "不能以句点结尾"

    # 注意：不能依赖 splitext 判断主体是否为空——它会把 ".jpg" 整体当作
    # 主体。这里手工截掉最后一个点及其后缀，剩余为空即判定为“只剩扩展名”。
    stem = name
    dot = stem.rfind(".")
    if dot >= 0:
        stem = stem[:dot]
    if not stem.strip():
        return False, "文件名主体为空（仅剩扩展名）"

    key = stem.split(".")[0].upper()
    if key in _RESERVED:
        return False, f"{key} 是系统保留名"
    if len(name) > 255:
        return False, "文件名超过 255 字符"
    return True, ""


def safe_int(text: Any, default: int = 0,
             lo: int | None = None, hi: int | None = None) -> int:
    """容错取整：空串、``None``、非数字、超范围输入全部降级而非抛异常。

    这是修复「位数输入框留空导致程序闪退」的关键。
    """
    try:
        value = int(str(text).strip())
    except (TypeError, ValueError):
        return default
    if lo is not None and value < lo:
        return lo
    if hi is not None and value > hi:
        return hi
    return value


def make_number(n: int, pad: int, randomize: bool = False,
                rng: random.Random | None = None) -> str:
    """生成编号字符串，严格按 ``pad`` 位补零。

    ``randomize=True`` 时在 ``[0, 10**pad - 1]`` 区间取随机值并补到 ``pad`` 位。
    """
    if pad <= 0:
        return str(n)
    if randomize:
        rng = rng or random
        return str(rng.randint(0, 10 ** pad - 1)).zfill(pad)
    return str(n).zfill(pad)


# ------------------------------------------------------------------ 引擎

class RenameEngine:
    """纯逻辑改名引擎。

    :param settings: 与界面控件一一对应的设置字典，键见 :data:`DEFAULT_SETTINGS`。
        缺失的键会用默认值补齐。
    """

    #: 功能页索引 -> 方法名
    PAGES = {
        0: "_page_number",
        1: "_page_add",
        2: "_page_delete",
        3: "_page_replace",
        4: "_page_case",
        5: "_page_ext",
        6: "_page_other",
    }

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        merged = dict(DEFAULT_SETTINGS)
        if settings:
            merged.update(settings)
        self.s: dict[str, Any] = merged

    # -------------------------------------------------- 各功能页

    def _page_number(self, orig: str, base: str, ext: str,
                     idx: int) -> str | None:
        """序号页：``#`` 为序号占位符，``[原文件名]`` 为原名主体。"""
        fmt = str(self.s["num_fmt"]).strip()
        if not fmt:
            return orig

        start = safe_int(self.s["num_start"], 1)
        step = safe_int(self.s["num_step"], 1)
        end = safe_int(self.s["num_end"], 0) or None

        n = start + idx * step
        if end is not None and n > end:
            return None                                  # 超过截止

        pad = safe_int(self.s["num_digits"], 3, lo=0, hi=20)
        num = make_number(n, pad, bool(self.s["num_random"]))
        return fmt.replace("#", num).replace("[原文件名]", base) + ext

    def _page_add(self, orig: str, base: str, ext: str, idx: int) -> str:
        """添加页：前缀 / 后缀 / 指定位置插入。

        界面上三个位置选项是**单选**的，因此常规使用下只会命中一条分支；
        引擎这里仍按「文件名前 → 文件名后 → 指定位置」的顺序依次应用，
        便于脚本调用方一次叠加多种插入。一个都没选时不做任何改动。
        """
        text = str(self.s["add_text"])
        if not text:
            return orig

        out = base
        touched = False
        if self.s["add_prefix"]:
            out, touched = text + out, True
        if self.s["add_suffix"]:
            out, touched = out + text, True
        if self.s["add_pos"]:
            pos = min(safe_int(self.s["add_pos_idx"], 0, lo=0), len(out))
            out, touched = out[:pos] + text + out[pos:], True
        return out + ext if touched else orig

    def _page_delete(self, orig: str, base: str, ext: str, idx: int) -> str:
        """删除页：指定文本 / 开头 N 字符 / 结尾 N 字符 / 从前数 / 从后数。

        所有模式均只作用于文件名主体，扩展名原样保留。界面上这几种模式是
        **单选**的；引擎侧对「万一同时命中」的情况按
        「指定文本 → 开头 N 字符 → 结尾 N 字符 → 从前数删除 → 从后数删除」
        的优先级取**第一个**生效——删除是破坏性操作，叠加执行容易产生意外结果。
        """
        # 指定文本：只删主体
        if self.s["del_text"]:
            kw = str(self.s["del_entry"])
            if not kw:
                return orig
            if kw in base:
                return base.replace(kw, "") + ext
            # 退一步匹配完整名，兼容用户确实想删含扩展名的片段
            return orig.replace(kw, "") if kw in orig else orig

        cnt = safe_int(self.s["del_cnt"], 0, lo=0)

        # 开头 N 字符：N ≤ 0 或 N ≥ 长度时不改动
        if self.s["del_head"]:
            if cnt <= 0 or cnt >= len(base):
                return orig
            return base[cnt:] + ext

        # 结尾 N 字符：同上
        if self.s["del_tail"]:
            if cnt <= 0 or cnt >= len(base):
                return orig
            return base[:-cnt] + ext

        pos_from = safe_int(self.s["del_pos_from"], 1, lo=1)
        pos_cnt = safe_int(self.s["del_pos_cnt"], 1, lo=1)

        # 从前数：从第 pos_from 个字起删 pos_cnt 个（1-based）
        if self.s["del_from_front"]:
            start = min(pos_from - 1, len(base))
            end = min(start + pos_cnt, len(base))
            if start >= end:
                return orig
            return base[:start] + base[end:] + ext

        # 从后数：锚定倒数第 pos_from 个，向前删 pos_cnt 个
        if self.s["del_from_back"]:
            end = len(base) - pos_from + 1
            if end <= 0:                     # 位置越界 —— 不执行任何删除
                return orig
            start = max(0, end - pos_cnt)
            if start >= end:
                return orig
            return base[:start] + base[end:] + ext

        return orig

    def _page_replace(self, orig: str, base: str, ext: str, idx: int) -> str:
        """替换页：查找替换，仅作用于主体，支持正则与大小写敏感。"""
        find = str(self.s["rep_find"])
        repl = str(self.s["rep_to"])
        if not find:
            return orig

        if self.s["rep_regex"]:
            flags = 0 if self.s["rep_case"] else re.IGNORECASE
            try:
                return re.sub(find, repl, base, flags=flags) + ext
            except re.error:
                return orig

        if self.s["rep_case"]:
            return base.replace(find, repl) + ext
        return re.compile(re.escape(find), re.IGNORECASE).sub(repl, base) + ext

    def _page_case(self, orig: str, base: str, ext: str, idx: int) -> str:
        """转换页：大小写转换，仅作用于主体。"""
        mode = self.s["case_mode"]
        if mode == CASE_LOWER:
            return base.lower() + ext
        if mode == CASE_UPPER:
            return base.upper() + ext
        if mode == CASE_TITLE:
            return base.title() + ext
        return orig

    def _page_ext(self, orig: str, base: str, ext: str, idx: int) -> str:
        """扩展名页：替换扩展名。

        输入会先过一遍 :func:`normalize_ext`（去点号、转小写），
        所以 ``PNG`` 会得到 ``.png`` 而不是 ``.PNG``；非法输入则不做改动。
        """
        new_ext = normalize_ext(self.s["ext_new"])
        if not new_ext:
            return orig
        return base + "." + new_ext

    def _page_other(self, orig: str, base: str, ext: str, idx: int) -> str:
        """其他页：按空格分隔的名称列表顺序命名。"""
        names = str(self.s["other_entry"]).strip().split()
        if not names or idx >= len(names):
            return orig
        return names[idx] + ext

    # -------------------------------------------------- 统一出口

    def new_name(self, orig: str, idx: int) -> str | None:
        """计算新文件名。

        :returns: 新文件名；``None`` 表示超过截止；非法结果退回 ``orig``。
        """
        base, ext = split_name(orig)
        method = self.PAGES.get(int(self.s["tab"]))
        if method is None:
            return orig

        out = getattr(self, method)(orig, base, ext, idx)
        if out is None:
            return None

        # 最终安全闸：非法结果一律退回原名
        ok, _ = validate_name(out)
        return out if ok else orig


# ------------------------------------------------------------------ 计划

def plan_rename(items: Sequence[tuple[str, str, bool]],
                engine: RenameEngine) -> list[tuple[str, str, str, str]]:
    """生成重命名计划（只读，不触碰磁盘）。

    :param items: ``[(绝对路径, 原文件名, 是否勾选), ...]``，保持列表原顺序。
    :returns: ``[(路径, 原名, 新名, 状态), ...]``，状态取值见 ``STATUS_*``。

    三条关键语义：

    * **序号只随已勾选项递增**——未勾选的文件不占号，避免出现 02、04 这类跳号。
    * **冲突键为 ``(目录, 新名小写)``**——不同文件夹下的同名文件可以共存，
      只有同一目录内的真冲突才会被拦截。
    * **磁盘占用同样判为冲突**——若目标名已被一个*不在本批次*的文件占用，
      提前标成 ``目标已存在``，而不是等到执行时才逐个弹窗报错。
      本批次内部的目标（例如交换名 ``A→B`` 且 ``B→A``）不算冲突。

    路径比较统一走 :func:`os.path.normcase`：Windows 的文件名不区分大小写，
    「转换」页把 ``ABC.JPG`` 改成 ``abc.JPG`` 时，目标路径其实就是它自己，
    用大小写敏感的比较会被误判成 ``目标已存在``，导致大小写转换根本没法做。
    """
    order: dict[str, int | None] = {}
    seq = 0
    for path, _orig, checked in items:
        order[path] = seq if checked else None
        if checked:
            seq += 1

    drafts: list[tuple[str, str, str, str]] = []
    for path, orig, checked in items:
        if not checked:
            drafts.append((path, orig, orig, STATUS_SAME))
            continue

        idx = order[path]
        assert idx is not None
        new_name = engine.new_name(orig, idx)
        if new_name is None:
            drafts.append((path, orig, orig, STATUS_OVER))
            continue
        if new_name == orig:
            drafts.append((path, orig, new_name, STATUS_SAME))
            continue
        drafts.append((path, orig, new_name, "待定"))

    # 本批次会让出哪些路径——这些名字可以被其他条目接管（交换名）
    vacated = {_norm_path(path)
               for path, _o, _n, status in drafts if status == "待定"}

    # 同目录内第 2 个及以后的重名判为冲突
    seen: dict[tuple[str, str], int] = {}
    result: list[tuple[str, str, str, str]] = []
    for path, orig, new_name, status in drafts:
        if status != "待定":
            result.append((path, orig, new_name, status))
            continue

        folder = os.path.dirname(os.path.abspath(path))
        key = (folder, new_name.lower())
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            result.append((path, orig, new_name, STATUS_CONFLICT))
            continue

        target = os.path.join(folder, new_name)
        if os.path.exists(target) and _norm_path(target) not in vacated:
            result.append((path, orig, new_name, STATUS_TAKEN))
            continue

        result.append((path, orig, new_name, STATUS_RENAME))
    return result


# ------------------------------------------------------------------ 执行

def apply_rename(plan: Iterable[tuple[str, str, str, str]],
                 history: list[tuple[str, str]]) -> tuple[int, list[tuple[str, str, str]]]:
    """执行重命名，采用两阶段提交以支持交换名并保证可回滚。

    阶段 1：把每个待改文件先改成同目录下唯一的临时名；
    阶段 2：再把临时名改成最终名。这样 ``A→B`` 且 ``B→A`` 也能正确完成。

    :param plan: :func:`plan_rename` 的结果（仅处理状态为 ``将重命名`` 的项）。
    :param history: 会被就地追加 ``(当前路径, 原路径)``，供 :func:`undo` 使用。
    :returns: ``(成功数, [(路径, 目标名, 失败原因), ...])``
    """
    todo = [item for item in plan if item[3] == STATUS_RENAME]
    if not todo:
        return 0, []

    errors: list[tuple[str, str, str]] = []
    staged: list[tuple[str, str, str]] = []          # (临时路径, 最终路径, 原路径)
    todo_paths = {_norm_path(item[0]) for item in todo}

    # 阶段 1：预检 + 暂存为临时名
    for seq, (path, _orig, new_name, _status) in enumerate(todo):
        final = os.path.join(os.path.dirname(path), new_name)
        # 注意这里用逐字符比较：大小写转换（ABC.JPG -> abc.JPG）在 Windows 上
        # 路径归一化后是同一个文件，但**确实要执行**，不能当成「无需改动」跳过。
        if os.path.abspath(final) == os.path.abspath(path):
            continue
        # 目标被本批次其他文件占用属正常（交换名），阶段 2 会处理
        if os.path.exists(final) and _norm_path(final) not in todo_paths:
            errors.append((path, new_name, "目标已存在"))
            continue

        tmp = os.path.join(
            os.path.dirname(path),
            f".renamer_tmp_{os.getpid()}_{seq}{os.path.splitext(new_name)[1]}")
        try:
            os.rename(path, tmp)
            staged.append((tmp, final, path))
        except OSError as exc:
            errors.append((path, new_name, f"重命名失败: {exc.strerror or exc}"))

    # 阶段 2：提交
    success = 0
    for tmp, final, origin in staged:
        try:
            os.rename(tmp, final)
            history.append((final, origin))          # 记录 (现名, 原名)，供撤销
            success += 1
        except OSError as exc:
            try:                                     # 回滚：把暂存文件放回原处
                os.rename(tmp, origin)
            except OSError:
                pass
            errors.append((origin, os.path.basename(final),
                           f"提交失败: {exc.strerror or exc}"))

    return success, errors


def undo(history: list[tuple[str, str]]) -> tuple[int, int]:
    """按逆序把文件改回原名。

    同样采用两阶段提交：先统一改为临时名，再统一改回原名。这样即使上一次
    操作是交换名（``A→B`` 且 ``B→A``），撤销时也不会因为“目标已被本批次的
    另一个文件占用”而失败（Windows 上 ``os.rename`` 不允许覆盖已存在文件）。

    :returns: ``(成功数, 失败数)``；无论成败都会清空 ``history``。
    """
    ok = fail = 0
    staged: list[tuple[str, str, str]] = []      # (临时路径, 目标原名, 当前路径)

    entries: list[tuple[str, str]] = []
    for current, original in reversed(history):
        if os.path.exists(current):
            entries.append((current, original))
        else:
            fail += 1

    # 阶段 1：当前名 -> 唯一临时名
    for seq, (current, original) in enumerate(entries):
        tmp = os.path.join(
            os.path.dirname(current),
            f".renamer_undo_{os.getpid()}_{seq}{os.path.splitext(original)[1]}")
        try:
            os.rename(current, tmp)
            staged.append((tmp, original, current))
        except OSError:
            fail += 1

    # 阶段 2：临时名 -> 原名
    for tmp, original, current in staged:
        try:
            os.rename(tmp, original)
            ok += 1
        except OSError:
            try:                                  # 尽量回滚到撤销前状态
                os.rename(tmp, current)
            except OSError:
                pass
            fail += 1

    history.clear()
    return ok, fail
