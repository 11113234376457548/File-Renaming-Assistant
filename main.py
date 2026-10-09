"""便捷启动脚本：``python main.py`` 等价于 ``python -m renamer``。

源码运行时（未安装为包）可直接用它，避免手动设置 ``PYTHONPATH``。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from renamer.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
