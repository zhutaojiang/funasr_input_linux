"""LLM 润色模块：把语音识别的粗文本送给 LLM 修正错别字与标点。

默认实现 StepFunPolisher 走 StepFun（阶跃星辰）的 OpenAI 兼容接口，
用 stdlib urllib 直接发请求，并显式绕过系统代理（避免被失效的 *_PROXY 拦截）。
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Callable, Optional, Protocol

logger = logging.getLogger("funasr_input")


DEFAULT_PROMPT = (
    "你是语音输入的文本润色器。把下面这段语音识别的口语结果整理成通顺的书面文本。规则：\n"
    "1. 删去无意义的语气词和口头禅，如 嗯、啊、呀、呃、哦、那个、就是说、然后那个 等；\n"
    "2. 去掉口吃、重复和明显赘语；\n"
    "3. 修正错别字，补全正确标点；\n"
    "4. 在不改变原意、不新增信息的前提下，可适当调整语序和措辞，使表达更通顺自然；\n"
    "5. 口语转书面：组合键中的「加」转成「+」并规范按键名（如 Control、Alt、Shift、Space），"
    "数字和单位按常规书写；\n"
    "6. 只输出整理后的文本本身，不要解释、不要加引号或任何前后缀。\n"
    "示例：\n"
    "输入：嗯，试一下中文混输，按 control 加 alt 加 space 切换录音模式。\n"
    "输出：试一下中文混输，按 Control+Alt+Space 切换录音模式。"
)


class _NoProxyHandler(urllib.request.ProxyHandler):
    """显式禁用所有代理的 ProxyHandler 子类。

    urllib.request.ProxyHandler({}) 因无协议方法不会进入 opener.handlers，
    需要子类显式定义 http_open / https_open 才能被正确注册。
    """

    def http_open(self, req: urllib.request.Request) -> None:  # type: ignore[override]
        """HTTP 请求不走代理，返回 None 交由后续 handler 处理。"""
        return None

    def https_open(self, req: urllib.request.Request) -> None:  # type: ignore[override]
        """HTTPS 请求不走代理，返回 None 交由后续 handler 处理。"""
        return None


def _make_opener() -> urllib.request.OpenerDirector:
    """构造绕过系统代理的 opener（空 ProxyHandler 关闭所有代理）。"""
    return urllib.request.build_opener(_NoProxyHandler({}))


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
        timeout: float = 8.0,
        prompt: str = DEFAULT_PROMPT,
        post: Optional[Callable[[str, bytes, dict], bytes]] = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("STEPFUN_API_KEY", "")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._prompt = prompt
        self._post = post or self._http_post

    def polish(self, text: str) -> str:
        if not text:
            return text
        try:
            url, data, headers = self._build_request(text)
            logger.info(
                "LLM 请求发送: model=%s base_url=%s 输入%d字",
                self._model, self._base_url, len(text),
            )
            t0 = time.time()
            raw = self._post(url, data, headers)
            dt = time.time() - t0
            result = self._parse_response(raw)
            logger.info("LLM 响应返回: 用时%.2fs 输出%d字", dt, len(result or ""))
            return result or text
        except Exception:
            logger.exception("LLM 润色失败，回退原文")
            return text  # 任意失败 → 回退原文，不阻断输入

    def warmup(self) -> None:
        """预热模型：发一条极短请求触发模型加载，消除首次润色的延迟。"""
        try:
            logger.info("LLM 预热中：触发模型加载...")
            t0 = time.time()
            self.polish("hello")
            dt = time.time() - t0
            logger.info("LLM 预热完成：用时%.2fs", dt)
        except Exception:
            logger.exception("LLM 预热失败（不影响正常使用）")

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
            "keep_alive": -1,
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


def make_polisher_from_config(config: dict) -> StepFunPolisher:
    """根据配置 dict 的 ``[polish]`` 段构造 StepFunPolisher。

    缺失字段回退到 StepFunPolisher 的默认值（api_key 进一步回退到
    环境变量 ``STEPFUN_API_KEY``）。
    """
    section = config.get("polish", {}) or {}
    kwargs: dict = {}
    for key in ("api_key", "base_url", "model", "prompt"):
        value = section.get(key)
        if value:
            kwargs[key] = value
    if (t := section.get("timeout")) is not None:
        kwargs["timeout"] = float(t)
    return StepFunPolisher(**kwargs)
