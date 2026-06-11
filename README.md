# funasr_input

基于 FunASR 的 Windows 语音输入法。

## 功能

- 热键触发录音（默认 Win+Alt+Space）
- 自动静音检测停止
- FunASR 本地识别，支持 50+ 语言
- SendInput 逐字注入当前焦点窗口
- 兼容 Claude Code CLI / Codex CLI / 终端 / GUI 程序

## 安装

> ⚠️ 建议使用 **Python 3.11 / 3.12**。funasr 依赖 torch 等，目前对 3.13+ 缺少可用 wheel，3.14 大概率装不上。

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

> 若 `py -3.12` 报 “No runtime installed that matches 3.12”（例如 3.12 是 uv 装的、
> 没注册到 py 启动器），可改用 uv 建环境：`uv venv --python 3.12`；或直接用 3.12
> 解释器全路径建：`& "<python3.12.exe>" -m venv .venv`（后者带 pip，后续步骤不变）。

> 默认安装的是 **CPU 版 torch**。若有 NVIDIA 显卡想用 GPU 加速，请按
> [pytorch.org](https://pytorch.org) 的指引单独安装对应 CUDA 版本的 torch/torchaudio，
> 并把 `VoiceIME(device="cuda")`。
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

```bash
python -m funasr_input
```

按 `Win+Alt+Space` 开始录音，静音 1 秒自动识别并输入，按 `Win+Alt+X` 退出。
首次运行会联网下载 FunASR 模型，请耐心等待。

> 全局热键依赖 `keyboard` 库，通常需要**以管理员身份运行终端**才能捕获按键。
> 退出键默认 `Win+Alt+X`（避免裸 ESC 误碰），可用 `VoiceIME(quit_hotkey="…")` 自定义。
>
> **睡眠后自愈**：Windows 在休眠/唤醒后常会让全局键盘钩子失效（表现为隔夜放置后
> 热键全部无响应）。程序内置看门狗每 30 秒重装钩子，唤醒后通常能自动恢复；若仍
> 无响应，重启程序即可。

### 识别模型预设：质量 or 速度

`config.toml` 的 `[asr].preset` 二选一：

| preset | 模型 | 特点 |
|---|---|---|
| `nano`（默认） | Fun-ASR-Nano | 多语言 50+、中英混说强、质量高；自回归逐字生成，**CPU 慢、内存大**。 |
| `fast` | Paraformer（中文） | 非自回归一次出整句，**CPU 上快数倍、内存省**；多语言弱。 |

```toml
[asr]
preset = "fast"
```

经验：**主要说中文 + CPU 机器，选 `fast`** —— 实测识别比 `nano` 快约 4~7 倍，标点/错别字交给 LLM 润色补齐即可。需要多语言/最高质量再用 `nano`。
也可在代码里临时覆盖：`VoiceIME(asr_preset="fast", ...)` 或 `VoiceIME(model_name="paraformer-zh", ...)`。

### 可选：LLM 润色

开启后，识别结果会先用 LLM 修正错别字/标点，再写入输入框。默认走 StepFun
（阶跃星辰，国内直连并自动绕过系统代理）。

**配置（推荐）：** 复制 `config.example.toml` 为项目根的 `config.toml`，填入你的值
（`config.toml` 已被 `.gitignore` 忽略，可安全存放 key）：

```toml
[polish]
api_key  = "你的 StepFun API key"
base_url = "https://api.stepfun.com/v1"
model    = "step-1-flash"
```

然后以 `polish=True` 启动：

```bash
python -c "from funasr_input.ime import VoiceIME; VoiceIME(device='cpu', polish=True).start()"
```

说明：
- `api_key` 也可改用环境变量 `STEPFUN_API_KEY`；`base_url`/`model` 缺省时回退到内置默认值。
- 配置路径可用环境变量 `FUNASR_INPUT_CONFIG` 覆盖。
- 也可传入自定义 `polisher=`（任何实现 `polish(text)->str` 的对象）。
- 任何网络/接口失败都会**自动回退到原始识别文本**，不会卡住输入。

### 可选：准流式预览

开启后，说话时会在屏幕下方弹出置顶悬浮窗，实时显示「识别中: …」粗结果；
说完（静音停止）后完整识别（如开了润色再润色），把净本一次性敲进焦点窗口。

```bash
python -c "from funasr_input.ime import VoiceIME; VoiceIME(device='cpu', live_preview=True, polish=True).start()"
```

- `live_interval`（默认 2.5 秒）控制粗结果刷新间隔；CPU 较慢可调大。
- 悬浮窗用 tkinter（无新依赖），置顶无边框，按 `Win+Alt+X` 退出。

## 开发

```bash
# 安装依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 打包
python -m build
```

## 许可证

MIT
