# 设计：准流式预览 + LLM 润色

日期：2026-06-09
状态：已确认（待写实现计划）

## 背景与目标

当前 `funasr_input` 是「按热键 → 整段录音 → 静音 1s 停止 → 离线识别 → SendInput 注入」的批处理流程。本设计新增两项**默认关闭、可选开启**的能力，且不改变现有简单流程：

1. **准流式预览**：说话时在悬浮窗实时显示「粗识别结果」，边说边看到字。
2. **LLM 润色**：整句说完后，用国内 LLM（StepFun，阶跃星辰）修正识别错误与标点，把**净本一次性**敲进焦点窗口。

关键约束：进输入框的永远是润色后的净本，**只注入一次**——彻底回避「退格改字」在 CLI/多行场景下的错位风险。

## 非目标

- 不做真正的逐字流式（不更换为流式 ASR 模型，沿用现有离线模型）。
- 不做「边说边直接写进输入框 + 退格修订」。
- 长语音/连续口述的窗口截断策略**本次不做**（见「已知取舍」），先服务输入法的短语音场景。

## 整体数据流

```
热键按下
  └─ start_stream() 持续采集音频到 buffer（复用已有钩子）
       ├─ [快层] 每 ~live_interval(≈2.5s) 取「当前全部 buffer」识别一次（离线模型）
       │         → 更新悬浮预览窗："识别中: <粗结果>"
       └─ 静音 silence_duration 后 → stop_stream()
            └─ [慢层] 整句完整识别 → 预览"润色中..."
                 └─ Polisher(StepFun) 润色 → 预览显示净本
                      └─ SendInput 一次性敲进焦点窗口
```

快层只驱动悬浮窗的实时反馈；慢层产出最终净本并注入。

## 组件设计

各模块单一职责、接口清晰、可独立测试。

### 1. 准流式识别调度（快层）

- 复用 `AudioRecorder.start_stream()/stop_stream()` 与 `on_chunk` 钩子，把音频块累积进 buffer。
- 后台「实时识别」线程：每 `live_interval` 秒取**当前全部 buffer**（增长窗口），写临时 WAV，调 `ASREngine.recognize()`，把结果回调给预览。
- **增长窗口**策略（已确认）：每次都从头重识别整段，结果连贯且越来越准，最后一次≈整句。代价是 CPU 上的重复计算，对短语音可接受。
- 静音停止后由慢层做最终识别（可复用最后一次结果或重识一次完整 buffer）。

### 2. 悬浮预览窗（tkinter，无新依赖）

- 无边框、置顶、半透明小条，显示状态/文字（如「🎤 录音中」「识别中: …」「润色中…」「✅ 净本」）。
- **线程模型调整（本设计唯一较大结构改动）**：
  - 现状：主线程阻塞在 `keyboard.wait("esc")`。
  - 调整后：**主线程运行 tkinter 事件循环**；热键回调在工作线程录音/识别；通过线程安全的 `widget.after()` 把更新推给预览窗。
  - 退出（ESC）需与 tkinter 循环协调关闭。
- 抽出**纯逻辑**（预览状态机 / 文本更新）便于单测；tkinter 实际渲染不做强测试。

### 3. Polisher（LLM 润色，可插拔）

- 新增 `polish.py`：
  - `Polisher` 抽象接口：`polish(text: str) -> str`。
  - `StepFunPolisher` 实现：OpenAI 兼容的 chat/completions 接口，`base_url` 指向 StepFun，默认快模型（如 `step-1-flash`，**可配置**），key 从环境变量读取。
  - **用 stdlib `urllib.request` 直接发 HTTP，不引入 `openai` SDK**：保持零新依赖，并能精确控制「绕过系统代理」（自建 opener、不读 `*_PROXY` 环境变量）。
- Prompt（固定）：「修正这段语音识别结果里的明显错别字与标点，保持原意，只输出结果」。
- **网络坑（必须处理）**：环境内 `HTTP_PROXY/HTTPS_PROXY` 指向已失效的境外节点。StepFun 为国内直连，HTTP 客户端必须**显式绕过系统代理**（`trust_env=False` / no_proxy），否则请求被塞进死代理而卡住。

### 4. VoiceIME 编排与开关

- 新增构造参数：`live_preview: bool = False`、`polish: bool = False`（或传入 `polisher` 对象）。
- 默认两者关闭 → 行为与当前完全一致，现有 23 个测试不受影响。
- **失败降级**：
  - 润色超时/报错 → 注入**原始识别文本**（LLM 故障不卡死输入）。
  - 快层识别报错 → 预览提示，不影响慢层最终结果与注入。

## 测试策略（TDD）

- `Polisher`：mock StepFun HTTP — 验证 prompt 组装、净本提取、超时/错误降级回原文、**确认绕过系统代理**。
- 准流式调度：mock `recognize` — 验证增长窗口按 `live_interval` 被调用、静音触发慢层。
- 预览状态机：纯逻辑单测（文本/状态流转）。
- 注入：沿用已有 SendInput 测试。
- 回归：默认关闭时，既有流程与测试全绿。

## 已知取舍 / 待后续讨论

- **增长窗口的 CPU 成本**：长篇连续口述会随 buffer 增长变慢。后续讨论「窗口截断/滑动窗口」策略来支持长语音（本次不做）。
- **快层在 CPU 上的实时性**：每次重识别需 ~1–2s，`live_interval` 需按机器调参；若过慢可调大间隔或关闭快层。

## 影响的文件（预估）

- 新增：`src/funasr_input/polish.py`、`src/funasr_input/preview.py`（预览窗 + 状态机）、`src/funasr_input/live.py`（准流式调度，或并入 ime）。
- 改动：`src/funasr_input/ime.py`（编排、线程模型、开关）。`pyproject.toml` 预计**无需新增依赖**（润色走 stdlib HTTP，预览用 stdlib tkinter）。
- 测试：对应新增单测；既有测试保持绿。
