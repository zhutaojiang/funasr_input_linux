"""配置加载。

从项目根的 ``config.toml`` 读取设置（如 LLM 润色的 base_url / model / api_key）。
可用环境变量 ``FUNASR_INPUT_CONFIG`` 指定其他路径。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - 仅 <3.11
    import tomli as tomllib  # type: ignore[no-redef]

# src/funasr_input/config.py -> 仓库根
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config.toml"


def config_path() -> Path:
    """解析配置文件路径（环境变量优先）。"""
    env = os.environ.get("FUNASR_INPUT_CONFIG")
    return Path(env) if env else DEFAULT_CONFIG_PATH


def load_config(path: Optional[Union[str, Path]] = None) -> dict:
    """加载 TOML 配置；文件不存在则返回空 dict。"""
    p = Path(path) if path is not None else config_path()
    if not p.exists():
        return {}
    with p.open("rb") as f:
        return tomllib.load(f)
