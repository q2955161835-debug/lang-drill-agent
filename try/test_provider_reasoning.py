from __future__ import annotations

from typing import Any

import pytest

from langdrill_agent.models import PromptPack
from langdrill_agent.providers import ModelProvider


class _FakeResponse:
    status_code = 200
    text = "{}"

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def _pack() -> PromptPack:
    return PromptPack(
        system_modules=[{"id": "system.core", "content": "只输出 JSON。"}],
        context_pack={"task_type": "daily_drill"},
        user_content="blood: n. 血液",
        output_schema={"type": "object"},
    )


def test_openai_reasoning_is_native_and_not_prompt_instruction(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _FakeResponse(
            {
                "choices": [{"message": {"content": "{\"ok\": true}"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            }
        )

    monkeypatch.setattr("langdrill_agent.providers.httpx.post", fake_post)

    provider = ModelProvider(
        "openai",
        "gpt-5.5",
        "https://api.openai.com/v1",
        "test-key",
        thinking_level="xhigh",
        api_format="openai-chat-completions",
        reasoning_parameter="openai_reasoning_effort",
    )

    provider.complete(_pack())

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    payload_text = str(captured["json"])
    assert "thinking_instruction" not in payload_text
    assert captured["json"]["reasoning_effort"] == "xhigh"


def test_deepseek_v4_reasoning_uses_thinking_payload(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["json"] = kwargs["json"]
        return _FakeResponse({"choices": [{"message": {"content": "{\"ok\": true}"}}]})

    monkeypatch.setattr("langdrill_agent.providers.httpx.post", fake_post)

    provider = ModelProvider(
        "deepseek",
        "deepseek-v4-pro",
        "https://api.deepseek.com",
        "test-key",
        thinking_level="max",
        api_format="openai-chat-completions",
        reasoning_parameter="deepseek_thinking",
    )

    provider.complete(_pack())

    assert captured["json"]["thinking"] == {"type": "enabled"}
    assert captured["json"]["reasoning_effort"] == "max"
    assert [message["role"] for message in captured["json"]["messages"]] == ["system", "user"]
    assert "context_pack" in captured["json"]["messages"][1]["content"]


def test_anthropic_messages_reasoning_uses_adaptive_thinking(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return _FakeResponse(
            {
                "content": [{"type": "text", "text": "{\"ok\": true}"}],
                "usage": {"input_tokens": 7, "output_tokens": 3},
            }
        )

    monkeypatch.setattr("langdrill_agent.providers.httpx.post", fake_post)

    provider = ModelProvider(
        "claude",
        "claude-sonnet-4.7",
        "https://api.anthropic.com",
        "apikey：test-key",
        thinking_level="high",
        api_format="anthropic-messages",
        reasoning_parameter="anthropic_adaptive_thinking",
    )

    provider.complete(_pack())

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["json"]["thinking"] == {"type": "adaptive"}
    assert captured["json"]["output_config"] == {"effort": "high"}
    assert captured["json"]["messages"][0]["role"] == "user"


def test_non_ascii_api_key_is_rejected_before_http(monkeypatch):
    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        raise AssertionError("httpx.post should not run for invalid header values")

    monkeypatch.setattr("langdrill_agent.providers.httpx.post", fake_post)

    provider = ModelProvider(
        "mimo",
        "mimo-v2.5",
        "https://api.xiaomimimo.com/anthropic",
        "mimo密钥",
        thinking_level="enabled",
        api_format="anthropic-messages",
        reasoning_parameter="anthropic_thinking_switch",
    )

    with pytest.raises(RuntimeError, match="非 ASCII"):
        provider.complete(_pack())


def test_unknown_non_native_reasoning_parameter_is_rejected():
    with pytest.raises(ValueError, match="不支持的原生思考参数"):
        ModelProvider(
            "custom_x",
            "custom-model",
            "https://example.com/v1",
            "test-key",
            thinking_level="high",
            api_format="openai-chat-completions",
            reasoning_parameter="prompt_instruction",
        )
