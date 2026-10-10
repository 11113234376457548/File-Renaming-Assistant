"""皮肤（调色板）与样式表生成测试。

皮肤加错的方式都很安静：漏一个色键要到用户切到那套皮肤时才 ``KeyError``，
明暗标志写反只是「白底白字」，对比度不足更是没人会报 bug。所以这里把四件事
钉死：**色键集合一致、明暗判定正确、QSS 能完整渲染、文字对比度够用**。
"""

from __future__ import annotations

import re

import pytest

from renamer.theme import Theme, build_qss

#: 所有皮肤都必须具备的色键（以经典浅色为基准）
BASE_KEYS = set(Theme.LIGHT)

#: 每套皮肤应该是深色还是浅色 —— 与 Theme.is_dark 的实现互相独立，
#: 写在这里是为了防止「把亮度算法改坏了但所有皮肤跟着一起错」
EXPECTED_DARK = {
    "light": False,
    "eye": False,
    "sand": False,
    "contrast": False,
    "dark": True,
    "midnight": True,
}


def _relative_luminance(hex_color: str) -> float:
    """独立实现一遍 sRGB 相对亮度，用来交叉验证 ``theme._luminance``。"""

    def channel(raw: int) -> float:
        value = raw / 255
        return (value / 12.92 if value <= 0.04045
                else ((value + 0.055) / 1.055) ** 2.4)

    red, green, blue = (channel(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(fg: str, bg: str) -> float:
    """WCAG 对比度（1 ~ 21）。"""
    a, b = _relative_luminance(fg), _relative_luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# ------------------------------------------------------------------ 注册表

@pytest.mark.parametrize("key", Theme.keys())
def test_every_skin_has_identical_keys(key):
    """皮肤之间必须只有取值不同，色键集合必须完全一致。

    少一个键 → build_qss 里 f-string 直接 KeyError；多一个键 → 说明有人
    往某套皮肤里塞了「专属色」，那套皮肤就成了特例，后续维护必然分叉。
    """
    assert set(Theme.get(key)) == BASE_KEYS


@pytest.mark.parametrize("key", Theme.keys())
def test_values_are_plain_hex_colours(key):
    for name, value in Theme.get(key).items():
        assert re.fullmatch(r"#[0-9a-f]{6}", value), f"{key}.{name} = {value!r}"


def test_default_skin_is_registered():
    assert Theme.has(Theme.DEFAULT)
    assert Theme.SKINS[Theme.DEFAULT] is Theme.LIGHT


def test_order_and_names_cover_every_skin_exactly_once():
    assert sorted(Theme.ORDER) == sorted(Theme.SKINS)
    assert len(Theme.ORDER) == len(set(Theme.ORDER))
    assert set(Theme.NAMES) == set(Theme.SKINS)


def test_toggle_pair_is_registered():
    assert Theme.TOGGLE_PAIR[0] == "light"
    assert Theme.TOGGLE_PAIR[1] == "dark"
    assert all(Theme.has(k) for k in Theme.TOGGLE_PAIR)


def test_unknown_key_falls_back_to_default():
    """未知皮肤名（配置被手改过）不能抛异常，回退默认皮肤即可。"""
    assert Theme.get("nope") == Theme.LIGHT
    assert Theme.name("nope") == Theme.NAMES[Theme.DEFAULT]
    assert Theme.is_dark("nope") is False
    assert not Theme.has("nope")


@pytest.mark.parametrize("key", Theme.keys())
def test_get_returns_an_independent_copy(key):
    """取出来的必须是副本，否则随便一处改动就会污染整个注册表。"""
    theme = Theme.get(key)
    theme["bg_base"] = "#123456"
    assert Theme.get(key)["bg_base"] != "#123456"


# ------------------------------------------------------------------ 明暗

@pytest.mark.parametrize("key,dark", sorted(EXPECTED_DARK.items()))
def test_is_dark_matches_design(key, dark):
    assert Theme.is_dark(key) is dark


# ------------------------------------------------------------------ 样式表

@pytest.mark.parametrize("key", Theme.keys())
def test_build_qss_renders_every_skin(key):
    """每套皮肤都能铺出完整样式表，且没有残留占位符。"""
    theme = Theme.get(key)
    qss = build_qss(theme, "C:/icons")

    assert "{t[" not in qss, "有 f-string 占位符没被替换"
    assert qss.count("{") == qss.count("}"), "花括号不配对，样式表被截断了"
    for colour_key in ("bg_base", "bg_surface", "accent", "border",
                       "text_primary", "success_hover"):
        assert theme[colour_key] in qss, f"{key} 的 {colour_key} 没进样式表"


@pytest.mark.parametrize("key", Theme.keys())
def test_primary_text_contrast_is_readable(key):
    """正文与次级文字的对比度要够，否则新皮肤容易调出「灰得看不清」。"""
    theme = Theme.get(key)
    assert _contrast(theme["text_primary"], theme["bg_base"]) >= 4.5
    assert _contrast(theme["text_secondary"], theme["bg_base"]) >= 3.0


@pytest.mark.parametrize("key", Theme.keys())
def test_white_text_on_accent_buttons(key):
    """「预览」按钮是白字压在强调色上，强调色太浅就看不见字了。"""
    assert _contrast("#ffffff", Theme.get(key)["accent"]) >= 3.0


@pytest.mark.parametrize("key", Theme.keys())
def test_placeholder_text_colour_is_declared(key):
    """占位提示色必须写进 QSS。

    调色板里的 ``PlaceholderText`` 角色在这套界面里**是无效的** —— 控件带了
    样式表、样式表里又写了 ``color`` 时，``QStyleSheetStyle`` 会盖掉那个角色
    （实测：改调色板角色后渲染结果纹丝不动）。所以只有这条 QSS 属性管用，
    它一旦被删掉，深色皮肤的占位提示就掉回约 2.5:1 的糊状。
    """
    theme = Theme.get(key)
    qss = build_qss(theme, "C:/icons")
    assert f"placeholder-text-color: {theme['text_muted']};" in qss


@pytest.mark.parametrize("key", Theme.keys())
def test_placeholder_contrast_does_not_regress(key):
    """占位提示的对比度只需**不比原版浅色主题差**。

    这里刻意不套 WCAG 的 3:1：``text_muted`` 是从原版 v4.0 截图上采样的
    （浅色主题 2.40:1），把它调深虽然能过 3:1，却会连带把「相同」「拖拽文件
    到此」这些同色提示一起改掉，偏离参考截图。所以下限取原版已有水平，
    作用只是拦住"新皮肤更糊"。
    """
    theme = Theme.get(key)
    assert _contrast(theme["text_muted"], theme["bg_input"]) >= 2.3
