<#
.SYNOPSIS
    启动 funasr_input 语音输入法

.DESCRIPTION
    激活 .venv 虚拟环境后启动 funasr_input，所有参数透传给 python -m funasr_input。

.EXAMPLE
    .\start.ps1
    .\start.ps1 --device cpu --asr-preset fast --polish --live-preview
#>

$venvPath = Join-Path $PSScriptRoot ".venv"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $activateScript)) {
    Write-Error ".venv 未找到，请先运行: py -3.12 -m venv .venv"
    exit 1
}

. $activateScript
python -m funasr_input @args
