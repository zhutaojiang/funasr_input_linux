"""配置加载与 Polisher 工厂单元测试。"""

from __future__ import annotations

from funasr_input.config import load_config
from funasr_input.polish import make_polisher_from_config, StepFunPolisher


def test_load_config_missing_file_returns_empty(tmp_path):
    assert load_config(tmp_path / "nope.toml") == {}


def test_load_config_parses_toml(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[polish]\n'
        'api_key = "k-abc"\n'
        'base_url = "https://api.example.com/v1"\n'
        'model = "my-model"\n',
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg["polish"]["api_key"] == "k-abc"
    assert cfg["polish"]["base_url"] == "https://api.example.com/v1"
    assert cfg["polish"]["model"] == "my-model"


def test_make_polisher_reads_section(tmp_path):
    cfg = {
        "polish": {
            "api_key": "k-xyz",
            "base_url": "https://api.example.com/v1",
            "model": "my-model",
        }
    }
    p = make_polisher_from_config(cfg)
    assert isinstance(p, StepFunPolisher)
    url, _data, headers = p._build_request("x")
    assert url == "https://api.example.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer k-xyz"
    body = __import__("json").loads(_data.decode("utf-8"))
    assert body["model"] == "my-model"


def test_make_polisher_empty_config_uses_defaults(monkeypatch):
    monkeypatch.delenv("STEPFUN_API_KEY", raising=False)
    p = make_polisher_from_config({})
    url, _data, _headers = p._build_request("x")
    # 缺失字段回退到 StepFunPolisher 默认值
    assert url == "https://api.stepfun.com/v1/chat/completions"
    body = __import__("json").loads(_data.decode("utf-8"))
    assert body["model"] == "step-1-flash"
