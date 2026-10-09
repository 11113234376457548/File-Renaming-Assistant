"""一键打包脚本。

会先清理 ``build/`` 与 ``dist/``（PyInstaller 缓存会导致“改了源码却打包出旧内容”），
再调用 ``packaging/File-Renaming-Assistant.spec`` 生成单文件可执行程序。

用法::

    python scripts/build_exe.py

产物位于 ``dist/File-Renaming-Assistant.exe``（Windows）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "packaging", "File-Renaming-Assistant.spec")


def clean(*names: str) -> None:
    for name in names:
        path = os.path.join(ROOT, name)
        if os.path.isdir(path):
            print(f"[clean] 删除 {path}")
            shutil.rmtree(path, ignore_errors=True)


def main() -> int:
    if not os.path.exists(SPEC):
        print(f"[error] 找不到 spec 文件：{SPEC}", file=sys.stderr)
        return 1

    # 必须先清理，否则 PyInstaller 会命中缓存、把旧内容打进产物
    clean("build", "dist")

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", SPEC]
    print("[build]", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    print("\n[ok] 打包完成，产物：")
    dist = os.path.join(ROOT, "dist")
    for name in sorted(os.listdir(dist)):
        full = os.path.join(dist, name)
        size = os.path.getsize(full) / 1024 / 1024
        print(f"     {name}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
