# funasr_input

基于 FunASR 的 Windows 语音输入法——按热键说话，自动语音识别，文本注入当前焦点窗口。支持 LLM 润色和准流式预览。

## 功能

- 热键触发录音（默认 `Win+Alt+M`），静音自动停止
- FunASR 本地识别，支持 50+ 语言（nano 预设）或中文快速识别（fast 预设）
- 准流式悬浮预览：说话时实时显示粗识别结果
- LLM 润色：识别后自动修正错别字/标点/语气词，再注入
- SendInput 逐字注入当前焦点窗口，兼容任意应用
- 热键看门狗：休眠唤醒后自动恢复钩子

## 数据流

```
热键按下 (Win+Alt+M)
  └─ 保存/恢复焦点窗口
       └─ 录音开始 (sounddevice)
            ├─ [快层] 每 ~2.5s 取累积音频 → 粗识别 → 悬浮窗"识别中: …"
            └─ 静音 1s → 停止录音
                 └─ 完整识别 (FunASR)
                      └─ 提交保序润色队列
                           └─ [可选] LLM 润色
                                └─ SendInput 逐字注入焦点窗口
```

**只注入一次净本**，不做"退格改字"，彻底回避 CLI/多行场景下的错位风险。润色失败自动回退原文。

## 安装

> ⚠️ 建议使用 **Python 3.11 / 3.12**。funasr 依赖 torch 等，目前对 3.13+ 缺少可用 wheel，3.14 大概率装不上。

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

> 若 `py -3.12` 报 "No runtime installed that matches 3.12"（例如 3.12 是 uv 装的、
> 没注册到 py 启动器），可改用 uv 建环境：`uv venv --python 3.12`；或直接用 3.12
> 解释器全路径建：`& "<python3.12.exe>" -m venv .venv`（后者带 pip，后续步骤不变）。

> 默认安装的是 **CPU 版 torch**。若有 NVIDIA 显卡想用 GPU 加速，请按
> [pytorch.org](https://pytorch.org) 的指引单独安装对应 CUDA 版本的 torch/torchaudio，
> 启动时加 `--device cuda`。
>
> 国内网络下载较慢可加镜像：`pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple`

### ⚠️ 版本约束（务必遵守，否则模型加载会原生崩溃）

`pyproject.toml` 已把以下版本钉死，**不要手动升级**：

- **torch / torchaudio 锁 2.5.x**：torch ≥ 2.6 会让 funasr 1.3.9 加载模型时
  `deepcopy` 触发原生崩溃（access violation，无 Python traceback、进程静默退出）。
- **transformers 锁 4.51–4.x**：Fun-ASR-Nano 用 Qwen3 骨干（需 transformers ≥ 4.51），
  但 transformers 5.x 在 import 时硬依赖 `torch.float8_e8m0fnu`（需 torch ≥ 2.8），
  与上面的 torch 上限冲突。本项目实测可用组合：**torch 2.5.1 + transformers 4.53.3**。

### ⚠️ 磁盘与缓存（避免把系统盘塞满导致崩溃）

模型约 **2GB+**（Fun-ASR-Nano + VAD + 标点），默认下载到 `C:\Users\<你>\.cache\modelscope`。
**若 C: 盘空间不足**，下载会被截断、或加载时 pagefile 无法扩展 → 同样表现为原生崩溃。
建议把模型缓存指到空间充足的盘（持久设置，新开终端生效）：

```powershell
[Environment]::SetEnvironmentVariable("MODELSCOPE_CACHE", "D:\funasr_cache\modelscope", "User")
```

> 加载时内存占用较高（模型 + Qwen3 骨干），运行前请关闭占内存的大程序，给它留出余量。

### 启动慢？（首跑下载，之后是网络校验 + CPU 加载）

首次启动会下载约 2GB 模型；之后每次启动看到的 `Downloading Model from...` 多数**不是重新下载**，
而是 modelscope 联网核对缓存版本。冷启动约需数十秒，主要花在 CPU 上构建 Qwen3 + 读 2GB 权重，属固有开销。
两个可省的网络等待：

- funasr 联网查新版：已在代码里默认 `disable_update=True` 关闭。
- modelscope 联网校验：模型下全后，可设离线模式直接用缓存、跳过联网（缓存不全时会报错，故仅在确认下载完成后再设）：

```powershell
[Environment]::SetEnvironmentVariable("MODELSCOPE_OFFLINE", "1", "User")
```

## 使用

### 快速启动

```bash
python -m funasr_input
```

或使用启动脚本（自动激活 `.venv`）：

```powershell
.\start.ps1
```

默认行为：按 `Win+Alt+M` 开始录音，静音 1 秒自动识别，**润色和准流式预览默认开启**（需配置 API key），按 `Win+Alt+X` 退出。

> 全局热键依赖 `pynput` 库，**普通用户即可运行**（Linux 无需 root/input 组，Windows 无需管理员）。
>
> **睡眠后自愈**：Windows 在休眠/唤醒后常会让全局键盘钩子失效（表现为隔夜放置后
> 热键全部无响应）。程序内置看门狗每 30 秒重装钩子，唤醒后通常能自动恢复；若仍
> 无响应，重启程序即可。

### 命令行参数

```
python -m funasr_input [选项]

选项：
  --asr-preset {nano,fast}   识别模型预设 (nano=多语言, fast=中文快)
  --model-name MODEL         ASR 模型名 (覆盖 preset)
  --vad-model MODEL          VAD 模型名 (覆盖 preset)
  --device {cpu,cuda}        推理设备 (默认 cpu)
  --hotkey HOTKEY            录音热键 (默认 win+alt+m)
  --quit-hotkey HOTKEY       退出热键 (默认 win+alt+x)
  --silence-threshold FLOAT  静音阈值 (默认 0.015)
  --silence-duration FLOAT   静音持续秒数后停止录音 (默认 1.0)
  --max-record-sec FLOAT     最长录音秒数 (默认 30.0)
  --char-delay FLOAT         逐字注入延迟秒数 (默认 0.0)
  --no-polish                禁用 LLM 润色
  --no-live-preview          禁用准流式悬浮预览
  --live-interval FLOAT      预览刷新间隔秒数 (默认 2.5)
  --debug                    开启 DEBUG 日志
```

示例：

```bash
# 中文快速识别 + 润色 + 预览（推荐日常使用）
python -m funasr_input --asr-preset fast

# 不需要润色和预览
python -m funasr_input --no-polish --no-live-preview

# GPU 加速
python -m funasr_input --device cuda

# 自定义热键
python -m funasr_input --hotkey ctrl+alt+r --quit-hotkey ctrl+alt+q
```

### 识别模型预设：质量 or 速度

`config.toml` 的 `[asr].preset` 或 `--asr-preset` 参数二选一：

| preset | 模型 | 特点 |
|---|---|---|
| `nano`（默认） | Fun-ASR-Nano | 多语言 50+、中英混说强、质量高；自回归逐字生成，**CPU 慢、内存大**。 |
| `fast` | Paraformer（中文） | 非自回归一次出整句，**CPU 上快数倍、内存省**；多语言弱。 |

经验：**主要说中文 + CPU 机器，选 `fast`** —— 实测识别比 `nano` 快约 4~7 倍，标点/错别字交给 LLM 润色补齐即可。需要多语言/最高质量再用 `nano`。

### LLM 润色

识别结果会先用 LLM 修正错别字/标点/语气词，再写入输入框。默认走 OpenAI 兼容接口
（Ollama 本地或任何 OpenAI 兼容云端 API，如 StepFun、DeepSeek），也支持 vLLM/SGLang/llama.cpp server。

**配置：** 复制 `config.example.toml` 为项目根的 `config.toml`，填入你的值
（`config.toml` 已被 `.gitignore` 忽略，可安全存放 key）：

```toml
[polish]
# 本地 Ollama（推荐）
base_url = "http://localhost:11434/v1"
model    = "qwen3:4b"
# 云 API 改用 base_url + model 对应服务，api_key 通过 .env 注入：
# base_url = "https://api.stepfun.com/v1"
# model    = "step-1-flash"
```

说明：
- API key 通过项目根 `.env` 文件的 `LLM_API_KEY` 环境变量注入；`base_url`/`model` 缺省时回退到内置默认值。
- 配置路径可用环境变量 `FUNASR_INPUT_CONFIG` 覆盖。
- 默认在请求体里加 `"think": false`，避免 Qwen3 等推理模型先吐一长串 `` 浪费 token+延迟。Qwen2.5 / 其他模型忽略此字段无副作用。
- 任何网络/接口失败都会**自动回退到原始识别文本**，不会卡住输入。
- 未配置 API key 时润色自动跳过，不影响使用。

### 准流式预览

说话时在屏幕下方弹出置顶悬浮窗，实时显示「识别中: …」粗结果；
说完后完整识别（如开了润色再润色），把净本一次性敲进焦点窗口。

- 使用 tkinter 实现，无额外依赖
- 置顶无边框半透明，可拖拽，自动定位屏幕底部居中
- `--live-interval`（默认 2.5 秒）控制粗结果刷新间隔；CPU 较慢可调大
- 用 `--no-live-preview` 关闭

## 项目结构

```
src/funasr_input/
├── __main__.py   # CLI 入口
├── ime.py        # 核心编排器 (VoiceIME, _PolishQueue)
├── asr.py        # ASR 语音识别引擎
├── audio.py      # 音频采集 (AudioRecorder, AudioSegment)
├── input.py      # Windows 文本注入 (TextInjector, FocusGuard)
├── polish.py     # LLM 润色 (OpenAICompatPolisher)
├── live.py       # 准流式识别调度 (LiveTranscriber)
├── preview.py    # 悬浮预览窗 (PreviewWindow)
├── presets.py    # 识别模型预设
└── config.py     # TOML 配置加载
```

## 开发

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## 许可证

MIT
