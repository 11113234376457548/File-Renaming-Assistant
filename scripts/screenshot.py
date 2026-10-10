"""生成文档用的界面截图。

在 ``QT_QPA_PLATFORM=offscreen`` 下渲染主窗口的每一个标签页并存为 PNG，
因此可以在无显示器的 CI 环境中运行。::

    QT_QPA_PLATFORM=offscreen python scripts/screenshot.py --out docs/screenshots

生成的是**真实界面**截图（非设计稿），便于 README 展示与回归比对。
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from renamer import settings  # noqa: E402
from renamer.theme import Theme  # noqa: E402
from renamer.ui.main_window import MainWindow, fix_palette  # noqa: E402

# 无头渲染时系统字体回退可能找不到中文字形，这里显式加载常见中文字体。
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\Deng.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def load_cjk_font() -> str | None:
    """加载一款中文字体并返回其家族名；失败时返回 ``None``。"""
    for path in FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
    return None


SAMPLE_FILES = [
    "IMG_20240101_全家福 副本.jpg",
    "IMG_20240102 会议记录.JPG",
    "会议记录_终稿_v2.docx",
    "Screenshot (12).png",
    "报告 final final(1).pdf",
    "vlog-001.mp4",
]

TAB_FILES = {
    0: "01-序号.png",
    1: "02-添加.png",
    2: "03-删除.png",
    3: "04-替换.png",
    4: "05-转换.png",
    5: "06-扩展名.png",
    6: "07-其他.png",
    7: "08-关于.png",
}


def build_samples(folder: str) -> list[str]:
    paths = []
    for name in SAMPLE_FILES:
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("sample")
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="生成界面截图")
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "screenshots"))
    parser.add_argument("--theme", default=Theme.DEFAULT,
                        choices=Theme.keys(),
                        help="皮肤名（默认 %(default)s）")
    parser.add_argument("--width", type=int, default=1160)
    parser.add_argument("--height", type=int, default=730)
    parser.add_argument("--gallery", action="store_true",
                        help="给每套皮肤各截一张（第一页），输出 <out>/<皮肤名>.png，"
                             "用于 README 里的皮肤一览")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    app = QApplication(sys.argv)
    family = load_cjk_font()
    if family:
        app.setFont(QFont(family, 10))
        print(f"[info] 使用中文字体：{family}")
    else:
        print("[warn] 未找到中文字体，截图中文字可能显示为方块")
    # 截图必须可复现，也不该动开发者本机存下的皮肤：把配置目录指到临时位置。
    os.environ[settings.ENV_OVERRIDE] = os.path.join(
        tempfile.gettempdir(), "file-renaming-assistant-screenshot-cfg")
    fix_palette(app, args.theme)

    with tempfile.TemporaryDirectory() as tmp:
        window = MainWindow()
        window.set_skin(args.theme)
        window.resize(args.width, args.height)
        window.show()
        window._add_paths(build_samples(tmp))

        if args.gallery:
            return _shoot_gallery(window, app, args.out)

        for index, filename in TAB_FILES.items():
            window.tabsel.setCurrentIndex(index)
            if index == 0:
                window.preview()          # 序号页展示预览结果
            app.processEvents()
            target = os.path.join(args.out, filename)
            ok = window.grab().save(target)
            print(f"{'[OK] ' if ok else '[FAIL]'} {target}")

    return 0


def _shoot_gallery(window, app, out_dir: str) -> int:
    """每套皮肤截一张第一页，文件名就是皮肤键（``eye.png`` / ``midnight.png`` …）。"""
    failed = 0
    for key in Theme.keys():
        window.set_skin(key)
        window.tabsel.setCurrentIndex(0)
        window.preview()
        app.processEvents()
        target = os.path.join(out_dir, f"{key}.png")
        ok = window.grab().save(target)
        failed += not ok
        print(f"{'[OK] ' if ok else '[FAIL]'} {target}  ({Theme.name(key)})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
