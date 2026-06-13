#!/usr/bin/env bash
# 启动 funasr_input 语音输入法（Linux）
#
# 前置条件：
#   1. 已创建并激活虚拟环境：python3 -m venv .venv
#   2. 已安装依赖：.venv/bin/pip install -e .
#   3. keyboard 库需要访问 /dev/input，二选一：
#        a) 将当前用户加入 input 组（推荐，重新登录后生效）：
#              sudo usermod -aG input $USER
#        b) 直接以 sudo 运行本脚本
#   4. X11 后端还需安装系统工具：
#        sudo apt install xdotool xclip
#   5. Wayland 后端还需安装：
#        sudo apt install wtype wl-clipboard

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
ACTIVATE="$VENV/bin/activate"

if [[ ! -f "$ACTIVATE" ]]; then
    echo "错误：虚拟环境未找到，请先运行：python3 -m venv .venv && .venv/bin/pip install -e ." >&2
    exit 1
fi

# shellcheck source=/dev/null
source "$ACTIVATE"

exec python -m funasr_input "$@"
