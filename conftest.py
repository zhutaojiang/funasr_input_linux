"""Pytest 配置：把 src/ 加入导入路径。

这样在未执行 ``pip install -e`` 的情况下也能直接运行 ``pytest``。
"""

import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
