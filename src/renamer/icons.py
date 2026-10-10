"""Lucide 图标访问层。

图标全部取自 `Lucide <https://lucide.dev>`_（ISC 协议），以 SVG 源码形式存放在
``resources/icons/`` 下，**运行时才着色渲染**。这样做有三个好处：

* 一套矢量图标同时服务浅色与深色主题，不需要为每种颜色各存一份位图；
* 任意尺寸都清晰，不受原始素材分辨率限制；
* 图标是标准开源素材，可随 MIT 协议一同分发（见 ``resources/icons/LICENSE``）。

Lucide 的 SVG 把描边颜色写成 ``stroke="currentColor"``，因此换色只需做一次
字符串替换。渲染依赖 ``QtSvg``（PySide6 自带）。

需要注意的是：QSS 的 ``image: url(...)`` 只认磁盘上的位图，无法直接引用内存
里的 SVG。所以这里额外提供 :func:`theme_icon_dir` —— 它把微调按钮、下拉箭头、
复选框这几张图按当前主题色渲染到缓存目录，再把目录路径交给
``theme.build_qss()``。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer

from .paths import resource_path
from .theme import Theme

__all__ = [
    "ICON_ADD_FILES",
    "ICON_ABOUT",
    "ICON_APP",
    "ICON_BROWSE",
    "ICON_CHECK_ALL",
    "ICON_CLEAR",
    "ICON_EXECUTE",
    "ICON_MORE",
    "ICON_PALETTE",
    "ICON_PREVIEW",
    "ICON_REFRESH",
    "ICON_THEME",
    "ICON_UNDO",
    "ICON_UNCHECK_ALL",
    "ICON_UPDATE",
    "app_icon_path",
    "icon",
    "pixmap",
    "svg_bytes",
    "theme_icon_dir",
]

# ---------------------------------------------------------------- 语义别名

ICON_BROWSE = "folder-open"
ICON_ADD_FILES = "file-plus"
ICON_REFRESH = "refresh-cw"
ICON_CLEAR = "trash-2"
ICON_PREVIEW = "eye"
ICON_EXECUTE = "circle-check"
ICON_UNDO = "undo-2"
ICON_THEME = "sun-moon"
ICON_PALETTE = "palette"
ICON_ABOUT = "info"
ICON_UPDATE = "cloud-download"
ICON_CHECK_ALL = "square-check"
ICON_UNCHECK_ALL = "square-x"
ICON_MORE = "chevron-down"
ICON_APP = "file-pen-line"

#: Lucide 的 24×24 视图框，边框内缩量（用于让复选框的填充色与描边对齐）
_VIEWBOX = 24.0
#: Lucide ``square`` 描边覆盖到的范围：2/24 ~ 22/24
_INK_INSET = 2.0
#: 复选框圆角（原版截图约为 2~3 px，此处按 24 视图给 3.5）
_CHECKBOX_RADIUS = 3.5

#: QSS 位图缓存根目录（放临时目录，随系统清理，不污染用户目录）
_CACHE_ROOT = os.path.join(
    tempfile.gettempdir(), "file-renaming-assistant-icons")

#: QSS 用到的图标：文件名 -> (Lucide 名, 主题色键, 渲染像素, stroke-width)
#: 渲染像素取显示尺寸的 3 倍做超采样，这样 125% / 150% 缩放下依然锐利；
#: stroke-width 则要加大 —— Lucide 默认的 2 是为大尺寸设计的，缩到 10 px
#: 后会细得几乎看不清。
_QSS_GLYPHS: dict[str, tuple[str, str, int, float]] = {
    "spin_plus": ("plus", "text_primary", 42, 3.2),
    "spin_minus": ("minus", "text_primary", 42, 3.2),
    "dropdown_arrow": ("chevron-down", "accent", 33, 2.6),
}
#: 复选框勾的加粗值
_CHECK_STROKE = 3.0
#: 复选框的位图尺寸（QSS 里显示为 15px）
_CHECKBOX_PX = 45


# ---------------------------------------------------------------- SVG 读取


@lru_cache(maxsize=64)
def _svg_text(name: str) -> str:
    """读取 ``resources/icons/<name>.svg`` 的源码。"""
    path = resource_path("icons", f"{name}.svg")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@lru_cache(maxsize=512)
def svg_bytes(name: str, color: str,
              stroke: float | None = None) -> bytes:
    """返回把 ``currentColor`` 换成 ``color`` 之后的 SVG 源码。

    这一步是整套主题化图标的关键：同一份矢量为任意主题色复用。

    ``stroke`` 用来覆盖 Lucide 默认的 ``stroke-width="2"``。小尺寸场景
    （微调按钮、下拉箭头）里 2 会被缩得几乎看不见，需要适当加粗。
    """
    text = _svg_text(name).replace("currentColor", color)
    if stroke is not None:
        text = text.replace('stroke-width="2"', f'stroke-width="{stroke}"')
    return text.encode("utf-8")


# ---------------------------------------------------------------- 渲染


def _device_pixel_ratio() -> float:
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    return float(screen.devicePixelRatio()) if screen is not None else 1.0


def _render(name: str, color: str, px: int,
            stroke: float | None = None) -> QImage:
    """把图标渲染成 ``px × px`` 的透明底位图。"""
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg_bytes(name, color, stroke)))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    return image


@lru_cache(maxsize=512)
def pixmap(name: str, size: int = 16, color: str = "#2c2c2c",
           stroke: float | None = None) -> QPixmap:
    """返回按屏幕缩放比渲染好的图标位图。"""
    ratio = _device_pixel_ratio()
    px = max(1, int(round(size * ratio)))
    pm = QPixmap.fromImage(_render(name, color, px, stroke))
    pm.setDevicePixelRatio(ratio)
    return pm


@lru_cache(maxsize=512)
def icon(name: str, color: str = "#2c2c2c", size: int = 16,
         stroke: float | None = None) -> QIcon:
    """返回用于 ``QAction`` / ``QPushButton`` 的图标。"""
    return QIcon(pixmap(name, size, color, stroke))


def app_icon_path() -> str:
    """应用图标（``resources/icon.png``）的绝对路径。"""
    return resource_path("icon.png")


# ---------------------------------------------------------------- QSS 位图


def _checkbox_checked(color: str) -> QImage:
    """选中态复选框：圆角方底 + Lucide ``check`` 白色描边。

    底色的内缩量刻意与 Lucide ``square`` 的描边范围一致，这样勾选与未勾选两态
    的方框边缘恰好对齐，切换时不会「跳一下」。
    """
    px = _CHECKBOX_PX
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    inset = px * _INK_INSET / _VIEWBOX
    radius = px * _CHECKBOX_RADIUS / _VIEWBOX
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(
        QRectF(inset, inset, px - 2 * inset, px - 2 * inset), radius, radius)
    painter.end()

    renderer = QSvgRenderer(QByteArray(
        svg_bytes("check", "#ffffff", _CHECK_STROKE)))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    return image


def _write_png(image: QImage, path: str) -> None:
    image.save(path, "PNG")


def _cache_key(t: dict[str, str]) -> str:
    """缓存目录名 = 配色 + 渲染配方 的摘要。

    把渲染参数也算进去，是为了避免「改了字号/描边粗细却读到上一版位图」
    这种只在开发时出现、上线后极难复现的问题。
    """
    payload = [f"{k}={t[k]}" for k in sorted(t)]
    payload += [
        f"{name}|{glyph}|{color_key}|{px}|{stroke}"
        for name, (glyph, color_key, px, stroke) in sorted(_QSS_GLYPHS.items())
    ]
    payload.append(f"check|{_CHECK_STROKE}|{_CHECKBOX_PX}")
    return hashlib.md5("|".join(payload).encode("utf-8")).hexdigest()[:10]


def theme_icon_dir(mode: str = "light") -> str:
    """把 QSS 需要的位图按 ``mode`` 主题着色后写进缓存目录并返回该目录。

    目录名由配色与渲染配方共同决定，任何一项变化都会落到新目录，
    不存在「读到上一版颜色 / 尺寸」的问题。
    """
    t = Theme.get(mode)
    out = os.path.join(_CACHE_ROOT, _cache_key(t))
    os.makedirs(out, exist_ok=True)

    for name, (glyph, color_key, px, stroke) in _QSS_GLYPHS.items():
        path = os.path.join(out, f"{name}.png")
        if not os.path.exists(path):
            _write_png(_render(glyph, t[color_key], px, stroke), path)

    jobs = {
        "chk_checked": lambda: _checkbox_checked(t["accent"]),
        "chk_unchecked": lambda: _render("square", t["border"], _CHECKBOX_PX),
    }
    for name, factory in jobs.items():
        path = os.path.join(out, f"{name}.png")
        if not os.path.exists(path):
            _write_png(factory(), path)

    return out.replace("\\", "/")
