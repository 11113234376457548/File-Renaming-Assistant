"""生成应用图标。

图标沿用了原版「吃瓜批量改名器」的吃瓜表情，源图存放在
``packaging/app_icon_source.png``（从原版 exe 的图标资源中导出）。
本脚本只做三件事：**补齐成正方形 → 缩放到各尺寸 → 写出 PNG / ICO**，
不做任何重新绘制，保证成品与原版视觉完全一致。

用法::

    python scripts/make_app_icon.py
    python scripts/make_app_icon.py --source 其它图.png

输出到 ``src/renamer/resources/``：``app_icon.png``（256，README 展示用）、
``icon.png``（64，运行时窗口图标）、``icon.ico``（多尺寸，供 PyInstaller
写进 exe）。
"""

from __future__ import annotations

import argparse
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "src", "renamer", "resources")
#: 源图：原版 exe 图标资源里尺寸最大的一张（256×248，非正方形）
DEFAULT_SOURCE = os.path.join(ROOT, "packaging", "app_icon_source.png")

#: 大图边长
BIG = 256
#: 运行时窗口图标的边长
SMALL = 64
#: 写进 exe 的全部尺寸（Windows 会按 DPI 自动挑最合适的一张）
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
             (128, 128), (256, 256)]


def square(source: str) -> Image.Image:
    """把源图居中贴到透明正方形画布上（源图非正方形时保持等比、不拉伸）。"""
    img = Image.open(source).convert("RGBA")
    if img.width == img.height:
        return img
    side = max(img.width, img.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description="生成应用图标")
    parser.add_argument("--source", default=DEFAULT_SOURCE,
                        help="图标源图（默认 packaging/app_icon_source.png）")
    args = parser.parse_args()

    if not os.path.exists(args.source):
        raise SystemExit(f"[error] 找不到源图：{args.source}")

    base = square(args.source)
    print(f"[icon] 源图 {Image.open(args.source).size} -> 正方形 {base.size}")

    big = os.path.join(RES, "app_icon.png")
    base.resize((BIG, BIG), Image.LANCZOS).save(big, "PNG")
    print("  ->", os.path.relpath(big, ROOT))

    small = os.path.join(RES, "icon.png")
    base.resize((SMALL, SMALL), Image.LANCZOS).save(small, "PNG")
    print("  ->", os.path.relpath(small, ROOT))

    ico = os.path.join(RES, "icon.ico")
    base.resize((BIG, BIG), Image.LANCZOS).save(ico, sizes=ICO_SIZES)
    print("  ->", os.path.relpath(ico, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
