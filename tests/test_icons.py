"""Lucide 图标层测试。

图标是「素材 + 运行时着色」的组合，出错方式比较隐蔽（缺文件不会崩、
只是不显示），所以这里把三件事钉死：SVG 齐全、着色正确、两套主题的
QSS 位图确实不同。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过图标测试")

from renamer import icons  # noqa: E402
from renamer.theme import Theme  # noqa: E402

#: 代码里引用到的全部 Lucide 图标
REFERENCED = [
    icons.ICON_BROWSE, icons.ICON_ADD_FILES, icons.ICON_REFRESH,
    icons.ICON_CLEAR, icons.ICON_PREVIEW, icons.ICON_EXECUTE,
    icons.ICON_UNDO, icons.ICON_THEME, icons.ICON_ABOUT, icons.ICON_UPDATE,
    icons.ICON_CHECK_ALL, icons.ICON_UNCHECK_ALL, icons.ICON_MORE,
    icons.ICON_APP,
    # QSS 位图用到的字形
    "plus", "minus", "chevron-down", "check", "square",
]


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.mark.parametrize("name", sorted(set(REFERENCED)))
def test_svg_file_exists(name):
    """每个被引用的图标都必须在 resources/icons 下有对应文件。"""
    from renamer.paths import resource_path
    assert os.path.exists(resource_path("icons", f"{name}.svg"))


def test_lucide_license_is_shipped():
    """Lucide 是 ISC 协议，随包分发时必须带上许可原文。"""
    from renamer.paths import resource_path
    text = open(resource_path("icons", "LICENSE"), encoding="utf-8").read()
    assert "ISC License" in text
    assert "Lucide" in text


def test_recolour_replaces_current_color():
    raw = icons.svg_bytes("plus", "#123456")
    assert b"#123456" in raw
    assert b"currentColor" not in raw


def test_stroke_width_override():
    """小尺寸场景要能覆盖 Lucide 默认的 stroke-width="2"。"""
    assert b'stroke-width="2"' in icons.svg_bytes("plus", "#000000")
    assert b'stroke-width="3.2"' in icons.svg_bytes("plus", "#000000", 3.2)


def test_theme_icon_dir_produces_all_qss_bitmaps(app):
    for mode in ("light", "dark"):
        out = icons.theme_icon_dir(mode)
        for name in ("spin_plus", "spin_minus", "dropdown_arrow",
                     "chk_checked", "chk_unchecked"):
            assert os.path.exists(os.path.join(out, f"{name}.png"))


def test_light_and_dark_bitmaps_differ(app):
    """两套主题各自着色，不能共用同一份位图。"""
    light = icons.theme_icon_dir("light")
    dark = icons.theme_icon_dir("dark")
    assert light != dark
    for name in ("spin_plus", "chk_unchecked"):
        a = open(os.path.join(light, f"{name}.png"), "rb").read()
        b = open(os.path.join(dark, f"{name}.png"), "rb").read()
        assert a != b


def test_checked_box_uses_accent_colour(app):
    """选中态复选框的方底必须是主题强调色，而不是描边色。"""
    from PySide6.QtGui import QColor

    from renamer.paths import resource_path  # noqa: F401  (确保资源可定位)
    image = icons._checkbox_checked(Theme.LIGHT["accent"])  # noqa: SLF001
    # 取方底左上角内部的一点，避开中间的白色勾
    px = image.pixelColor(6, 6)
    assert px.alpha() > 200
    assert abs(px.red() - QColor(Theme.LIGHT["accent"]).red()) <= 6


def test_icon_and_pixmap_are_not_null(app):
    assert not icons.icon(icons.ICON_BROWSE, "#2c2c2c").isNull()
    pm = icons.pixmap(icons.ICON_PREVIEW, 14, "#ffffff")
    assert not pm.isNull()
    assert pm.width() >= 14


def test_app_icon_exists():
    assert os.path.exists(icons.app_icon_path())


def test_app_icon_is_square():
    """应用图标必须是正方形。

    源图（原版 exe 里导出的吃瓜表情）是 256×248，直接拿来当图标在任务栏上
    会被拉变形，所以 scripts/make_app_icon.py 会先补齐画布；这里把结果钉住。
    """
    from PySide6.QtGui import QImage

    for path in (icons.app_icon_path(),
                 os.path.join(os.path.dirname(icons.app_icon_path()),
                              "app_icon.png")):
        image = QImage(path)
        assert not image.isNull(), path
        assert image.width() == image.height(), path
