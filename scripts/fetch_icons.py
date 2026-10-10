"""抓取 Lucide 图标（SVG 源码）。

仓库里已经带有生成好的 SVG，**日常开发不需要运行本脚本**。
只有在想升级图标版本、或新增引用某个 Lucide 图标时才需要执行。

用法::

    python scripts/fetch_icons.py                # 用默认版本
    python scripts/fetch_icons.py --version 1.54.0
    python scripts/fetch_icons.py --mirror registry.npmmirror.com

抓取的是 npm 上的 ``lucide-static`` 包（内含全部图标 SVG 与许可原文），
解包后只复制本程序用到的图标，其余丢弃。

图标来自 https://lucide.dev ，ISC 协议；部分源自 Feather（MIT）。
许可原文会一并复制到 ``resources/icons/LICENSE``。
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "src", "renamer", "resources", "icons")

#: 锁定版本，保证图标可复现
DEFAULT_VERSION = "1.54.0"
#: 国内镜像优先，GitHub 直连在部分网络下不稳定
DEFAULT_MIRROR = "registry.npmmirror.com"

#: 需要抓取的图标（与 renamer/icons.py 中的语义别名一致）
ICONS = [
    "plus", "minus", "chevron-down", "check", "square",
    "square-check", "square-x", "folder-open", "file-plus",
    "refresh-cw", "trash-2", "eye", "circle-check", "undo-2",
    "sun-moon", "info", "file-pen-line", "cloud-download",
    "palette",
]


def download(url: str) -> bytes:
    """下载二进制内容；先试 urllib，失败则退回 curl。"""
    try:
        with urllib.request.urlopen(url, timeout=90) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001 — 需要兜底到 curl
        print(f"[warn] urllib 失败（{exc}），改用 curl 重试")

    # Windows 上 schannel 常因「吊销列表离线」握手失败，--ssl-no-revoke 可绕过
    out = os.path.join(tempfile.gettempdir(), "lucide-static.tgz")
    cmd = ["curl", "-sSL", "--ssl-no-revoke", "--max-time", "300",
           "-o", out, url]
    if subprocess.run(cmd, check=False).returncode != 0:
        raise SystemExit(f"[error] 下载失败：{url}")
    with open(out, "rb") as fh:
        return fh.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 Lucide 图标 SVG")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--mirror", default=DEFAULT_MIRROR)
    args = parser.parse_args()

    url = (f"https://{args.mirror}/lucide-static/-/"
           f"lucide-static-{args.version}.tgz")
    print(f"[fetch] {url}")
    blob = download(url)
    print(f"[fetch] 已下载 {len(blob) / 1024 / 1024:.1f} MB，开始解包")

    os.makedirs(DEST, exist_ok=True)
    wanted = {f"package/icons/{name}.svg" for name in ICONS}
    wanted.add("package/LICENSE")

    extracted = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name not in wanted:
                continue
            name = os.path.basename(member.name)
            target = os.path.join(DEST, name)
            src = tar.extractfile(member)
            if src is None:
                continue
            with open(target, "wb") as fh:
                shutil.copyfileobj(src, fh)
            print("  ->", os.path.relpath(target, ROOT))
            extracted += 1

    missing = [name for name in ICONS
               if not os.path.exists(os.path.join(DEST, f"{name}.svg"))]
    if missing:
        print(f"[warn] 只解出 {extracted} 个文件，以下图标缺失：{missing}")
        return 1
    if not os.path.exists(os.path.join(DEST, "LICENSE")):
        print("[warn] 未取到 Lucide 许可原文（LICENSE）")
        return 1

    print(f"[ok] 完成，共 {extracted} 个文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
