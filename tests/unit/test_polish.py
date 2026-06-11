"""LLM 润色模块单元测试。"""

from __future__ import annotations

import json
import urllib.request

from funasr_input.polish import _make_opener, StepFunPolisher, DEFAULT_PROMPT


def test_make_opener_bypasses_system_proxy():
    # 关键：必须绕过 *_PROXY 环境变量（环境里那个境外代理已失效）
    opener = _make_opener()
    proxy_handlers = [
        h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)
    ]
    assert proxy_handlers, "应当显式安装 ProxyHandler"
    assert proxy_handlers[0].proxies == {}, "ProxyHandler 必须为空（禁用所有代理）"


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
