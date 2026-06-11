# LLM 润色 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在识别结果注入输入框前，可选地用国内 LLM（StepFun）修正错别字与标点。

**Architecture:** 新增可插拔 `Polisher` 接口 + `StepFunPolisher`（stdlib urllib，显式绕过系统代理）。`VoiceIME` 加 `polish` 开关，在 `recognize() → write()` 之间插一步；任何润色失败都回退原始文本，不阻断输入。默认关闭，现有流程与 23 个测试不受影响。

**Tech Stack:** Python 3.11+，stdlib `urllib.request` / `json`（零新依赖），pytest。

本计划对应 spec：`docs/superpowers/specs/2026-06-09-streaming-preview-llm-polish-design.md`（第三节 Polisher + 第四节开关 + 失败降级）。准流式预览是单独的第二份计划，不在本计划内。

---

## File Structure

- **Create** `src/funasr_input/polish.py` — `Polisher` 接口、`StepFunPolisher` 实现、`_make_opener()` 代理绕过。单一职责：把文本送 LLM 润色。
- **Modify** `src/funasr_input/ime.py` — 构造参数 `polish`/`polisher`，在 `_on_hotkey` 注入前插入润色步骤。
- **Create** `tests/unit/test_polish.py` — Polisher 单测。
- **Create** `tests/unit/test_ime_polish.py` — VoiceIME 接线单测。

---

## Task 1: Polisher 接口与代理绕过 opener

**Files:**
- Create: `src/funasr_input/polish.py`
- Test: `tests/unit/test_polish.py`

- [ ] **Step 1: 写失败测试（代理绕过）**

`tests/unit/test_polish.py`:
```python
"""LLM 润色模块单元测试。"""

from __future__ import annotations

import urllib.request

from funasr_input.polish import _make_opener


def test_make_opener_bypasses_system_proxy():
    # 关键：必须绕过 *_PROXY 环境变量（环境里那个境外代理已失效）
    opener = _make_opener()
    proxy_handlers = [
        h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)
    ]
    assert proxy_handlers, "应当显式安装 ProxyHandler"
    assert proxy_handlers[0].proxies == {}, "ProxyHandler 必须为空（禁用所有代理）"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_polish.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'funasr_input.polish'`

- [ ] **Step 3: 写最小实现**

`src/funasr_input/polish.py`:
```python
"""LLM 润色模块：把语音识别的粗文本送给 LLM 修正错别字与标点。

默认实现 StepFunPolisher 走 StepFun（阶跃星辰）的 OpenAI 兼容接口，
用 stdlib urllib 直接发请求，并显式绕过系统代理（避免被失效的 *_PROXY 拦截）。
"""

from __future__ import annotations

import urllib.request


def _make_opener() -> urllib.request.OpenerDirector:
    """构造绕过系统代理的 opener（空 ProxyHandler 关闭所有代理）。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_polish.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/funasr_input/polish.py tests/unit/test_polish.py
git commit -m "feat(polish): 代理绕过 opener"
```

---

## Task 2: 请求构造与响应解析（纯逻辑）

**Files:**
- Modify: `src/funasr_input/polish.py`
- Test: `tests/unit/test_polish.py`

- [ ] **Step 1: 写失败测试（构造 + 解析）**

追加到 `tests/unit/test_polish.py`:
```python
import json

from funasr_input.polish import StepFunPolisher, DEFAULT_PROMPT


def test_build_request_body_and_headers():
    p = StepFunPolisher(api_key="k-123", model="step-1-flash")
    url, data, headers = p._build_request("识别原文")

    assert url.endswith("/chat/completions")
    assert headers["Authorization"] == "Bearer k-123"
    assert headers["Content-Type"] == "application/json"

    body = json.loads(data.decode("utf-8"))
    assert body["model"] == "step-1-flash"
    assert body["messages"][0] == {"role": "system", "content": DEFAULT_PROMPT}
    assert body["messages"][1] == {"role": "user", "content": "识别原文"}


def test_parse_response_extracts_and_strips():
    raw = json.dumps(
        {"choices": [{"message": {"content": "  润色后的文本。 "}}]}
    ).encode("utf-8")
    assert StepFunPolisher._parse_response(raw) == "润色后的文本。"


def test_parse_response_empty_choices():
    raw = json.dumps({"choices": []}).encode("utf-8")
    assert StepFunPolisher._parse_response(raw) == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_polish.py -q`
Expected: FAIL — `ImportError: cannot import name 'StepFunPolisher'`

- [ ] **Step 3: 写最小实现**

追加到 `src/funasr_input/polish.py`（顶部 import 改为）：
```python
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, Optional, Protocol


DEFAULT_PROMPT = (
    "你是语音识别后处理器。修正下面这段语音识别结果里的明显错别字和标点，"
    "保持原意，不要增删内容，只输出修正后的文本本身。"
)
```

在 `_make_opener` 之后追加：
```python
class Polisher(Protocol):
    """文本润色接口。"""

    def polish(self, text: str) -> str:
        ...


class StepFunPolisher:
    """StepFun（OpenAI 兼容）润色实现。"""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "step-1-flash",
        base_url: str = "https://api.stepfun.com/v1",
        timeout: float = 10.0,
        prompt: str = DEFAULT_PROMPT,
        post: Optional[Callable[[str, bytes, dict], bytes]] = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("STEPFUN_API_KEY", "")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._prompt = prompt
        self._post = post or self._http_post

    def _build_request(self, text: str) -> tuple[str, bytes, dict]:
        url = f"{self._base_url}/chat/completions"
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.3,
            "stream": False,
        }
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        return url, data, headers

    @staticmethod
    def _parse_response(raw: bytes) -> str:
        obj = json.loads(raw.decode("utf-8"))
        choices = obj.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message", {}).get("content") or "").strip()

    def _http_post(self, url: str, data: bytes, headers: dict) -> bytes:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        opener = _make_opener()
        with opener.open(req, timeout=self._timeout) as resp:
            return resp.read()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_polish.py -q`
Expected: PASS（4 个测试）

- [ ] **Step 5: 提交**

```bash
git add src/funasr_input/polish.py tests/unit/test_polish.py
git commit -m "feat(polish): StepFun 请求构造与响应解析"
```

---

## Task 3: polish() 编排与失败降级

**Files:**
- Modify: `src/funasr_input/polish.py`
- Test: `tests/unit/test_polish.py`

- [ ] **Step 1: 写失败测试（编排 + 降级）**

追加到 `tests/unit/test_polish.py`:
```python
def test_polish_empty_text_skips_request():
    calls = []
    p = StepFunPolisher(api_key="k", post=lambda u, d, h: calls.append(1) or b"{}")
    assert p.polish("") == ""
    assert calls == []  # 空文本不发请求


def test_polish_returns_parsed_result():
    def fake_post(url, data, headers):
        return json.dumps(
            {"choices": [{"message": {"content": "净本"}}]}
        ).encode("utf-8")

    p = StepFunPolisher(api_key="k", post=fake_post)
    assert p.polish("毛本") == "净本"


def test_polish_degrades_to_original_on_error():
    def boom(url, data, headers):
        raise TimeoutError("proxy/network down")

    p = StepFunPolisher(api_key="k", post=boom)
    assert p.polish("原始文本") == "原始文本"  # 失败回退原文，不抛异常


def test_polish_degrades_when_result_empty():
    p = StepFunPolisher(api_key="k", post=lambda u, d, h: b'{"choices": []}')
    assert p.polish("原始文本") == "原始文本"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_polish.py -q`
Expected: FAIL — `AttributeError: 'StepFunPolisher' object has no attribute 'polish'`

- [ ] **Step 3: 写最小实现**

在 `StepFunPolisher` 内 `__init__` 之后插入 `polish` 方法：
```python
    def polish(self, text: str) -> str:
        if not text:
            return text
        try:
            url, data, headers = self._build_request(text)
            raw = self._post(url, data, headers)
            result = self._parse_response(raw)
            return result or text
        except Exception:
            return text  # 任意失败 → 回退原文，不阻断输入
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_polish.py -q`
Expected: PASS（8 个测试）

- [ ] **Step 5: 提交**

```bash
git add src/funasr_input/polish.py tests/unit/test_polish.py
git commit -m "feat(polish): polish() 编排与失败降级回原文"
```

---

## Task 4: VoiceIME 接线（开关 + 注入前润色）

**Files:**
- Modify: `src/funasr_input/ime.py`
- Test: `tests/unit/test_ime_polish.py`

- [ ] **Step 1: 写失败测试（接线）**

`tests/unit/test_ime_polish.py`:
```python
"""VoiceIME 润色接线单元测试。"""

from __future__ import annotations

from pathlib import Path


class _FakeSegment:
    def to_wav(self, path):
        return Path(path)


class _FakePolisher:
    def __init__(self, out: str):
        self._out = out
        self.seen = None

    def polish(self, text: str) -> str:
        self.seen = text
        return self._out


def _make_ime(monkeypatch, **kwargs):
    from funasr_input.ime import VoiceIME

    ime = VoiceIME(device="cpu", on_status=lambda m: None, **kwargs)
    monkeypatch.setattr(ime._recorder, "record", lambda: _FakeSegment())
    monkeypatch.setattr(ime._asr, "recognize", lambda p: "原始文本")
    written = {}
    monkeypatch.setattr(ime._injector, "write", lambda t: written.__setitem__("text", t))
    return ime, written


def test_polish_disabled_injects_raw(monkeypatch):
    ime, written = _make_ime(monkeypatch)  # polish 默认关闭
    ime._on_hotkey()
    assert written["text"] == "原始文本"


def test_polish_enabled_injects_polished(monkeypatch):
    polisher = _FakePolisher("润色后文本")
    ime, written = _make_ime(monkeypatch, polish=True, polisher=polisher)
    ime._on_hotkey()
    assert polisher.seen == "原始文本"      # 润色收到的是原始识别结果
    assert written["text"] == "润色后文本"   # 注入的是润色后的
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/test_ime_polish.py -q`
Expected: FAIL — `TypeError: VoiceIME.__init__() got an unexpected keyword argument 'polish'`

- [ ] **Step 3: 写最小实现**

修改 `src/funasr_input/ime.py`：

顶部 import 增加：
```python
from funasr_input.polish import Polisher, StepFunPolisher
```

`__init__` 签名增加两个参数（放在 `on_status` 之前）：
```python
        polish: bool = False,
        polisher: Optional[Polisher] = None,
        on_status: Optional[Callable[[str], None]] = None,
```

`__init__` 体内、`self._injector = ...` 之后增加：
```python
        if polish:
            self._polisher: Optional[Polisher] = polisher or StepFunPolisher()
        else:
            self._polisher = None
```

`_on_hotkey` 中，把识别成功后、注入之前那段改为：
```python
            if not text:
                self._notify("❌ 未识别到语音")
                return

            if self._polisher is not None:
                self._notify("✍ 正在润色...")
                text = self._polisher.polish(text)

            self._notify(f"✅ {text}")
            self._injector.write(text)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/test_ime_polish.py -q`
Expected: PASS（2 个测试）

- [ ] **Step 5: 全量回归**

Run: `python -m pytest tests/ -q`
Expected: PASS（既有 23 + 新增 10 = 33）

- [ ] **Step 6: 提交**

```bash
git add src/funasr_input/ime.py tests/unit/test_ime_polish.py
git commit -m "feat(ime): 注入前可选 LLM 润色（默认关闭，失败回退原文）"
```

---

## Task 5: README 用法 + 手动验证

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README 使用说明**

在 README「使用」一节后追加：
```markdown
### 可选：LLM 润色

设置 StepFun API key 后开启润色，识别结果会先被修正错别字/标点再输入：

\`\`\`powershell
$env:STEPFUN_API_KEY = "你的key"
\`\`\`

并在代码里用 `VoiceIME(polish=True)` 启动（或自定义 `polisher=`）。
润色走国内直连并绕过系统代理；任何网络/接口失败都会自动回退到原始识别文本。
```

- [ ] **Step 2: 手动验证（需真实 key 与麦克风）**

1. `$env:STEPFUN_API_KEY = "..."`
2. 临时入口：`python -c "from funasr_input.ime import VoiceIME; VoiceIME(device='cpu', polish=True).start()"`
3. 焦点放记事本，按 Ctrl+Alt+Space 说一句带口头语/错字的话。
4. 预期：终端出现「✍ 正在润色...」→「✅ <净本>」，记事本里是润色后的文本。
5. 断网或乱填 key 再试一次：应回退为原始识别文本、不卡死。

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: LLM 润色用法说明"
```

---

## Self-Review

**Spec coverage（第三节 Polisher / 第四节开关与降级）：**
- Polisher 接口 + StepFunPolisher → Task 1–3 ✅
- stdlib urllib + 绕过代理 → Task 1（`_make_opener`）+ Task 2（`_http_post`）✅
- 固定 prompt → Task 2（`DEFAULT_PROMPT`）✅
- key 从环境变量 → Task 2（`STEPFUN_API_KEY`）✅
- VoiceIME 开关，默认关、不破坏现状 → Task 4（`polish=False`）+ Step 5 回归 ✅
- 润色失败降级回原文 → Task 3 + Task 4（`_FakePolisher` 不触发，降级逻辑在 polish 内）✅

**Placeholder scan:** 无 TBD/TODO；每个代码步骤均给出完整代码。

**Type consistency:** `Polisher.polish(text)->str`、`StepFunPolisher.__init__(post=...)`、`_build_request->(url,data,headers)`、`_parse_response(raw)->str` 在各任务间一致；`VoiceIME(polish, polisher)` 与 Task 4 测试一致。

**Scope:** 聚焦润色单一子系统，独立可交付。准流式预览另起计划。
