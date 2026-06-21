#!/usr/bin/env bash
# 启动 funasr_input 语音输入法（Linux）
#
# 虚拟环境与项目目录解耦：默认放在 ~/.local/share/funasr_input/venv，
# 因此移动或改名项目目录都不会破坏 venv。可用环境变量 FUNASR_VENV 覆盖。
#
# 前置条件：
#   1. 已创建虚拟环境并安装依赖（venv 在项目目录之外）：
#        python3 -m venv ~/.local/share/funasr_input/venv
#        ~/.local/share/funasr_input/venv/bin/pip install -e .
#   2. 全局热键用 pynput，普通用户即可运行，无需 root / input 组。
#   3. 预览窗需要 tkinter：sudo apt install python3-tk
#   4. 录音需要 PortAudio 运行库：sudo apt install libportaudio2
#   5. X11 后端还需安装系统工具：
#        sudo apt install xdotool xclip
#   6. Wayland 后端还需安装：
#        sudo apt install wtype wl-clipboard

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# venv 位置：优先 FUNASR_VENV，其次默认的家目录位置，最后回退到项目内 .venv。
DEFAULT_VENV="${XDG_DATA_HOME:-$HOME/.local/share}/funasr_input/venv"
VENV="${FUNASR_VENV:-$DEFAULT_VENV}"
if [[ ! -x "$VENV/bin/python3" && -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
    VENV="$SCRIPT_DIR/.venv"
fi

if [[ ! -x "$VENV/bin/python3" ]]; then
    echo "错误：虚拟环境未找到（已查找 $VENV）。请先运行：" >&2
    echo "  python3 -m venv $DEFAULT_VENV && $DEFAULT_VENV/bin/pip install -e ." >&2
    exit 1
fi

# 直接调用 venv 内的 Python（绝对路径），不依赖会因迁移而失效的 activate 脚本。
# 项目源码通过 PYTHONPATH 相对 start.sh 注入，因此 venv 内不保存任何项目路径，
# 项目可被移动到任意目录而无需重装。
export VIRTUAL_ENV="$VENV"
export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

exec "$VENV/bin/python3" -m funasr_input "$@"
