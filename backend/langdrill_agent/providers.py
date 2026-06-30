from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .models import PromptPack
from .utils import dumps, estimate_tokens, normalize_api_key, validate_http_header_value


@dataclass(frozen=True)
class ModelResult:
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str


class ModelProvider:
    SUPPORTED_API_FORMATS = {"openai-chat-completions", "anthropic-messages"}
    SUPPORTED_REASONING_PARAMETERS = {
        "",
        "openai_reasoning_effort",
        "deepseek_thinking",
        "anthropic_adaptive_thinking",
        "anthropic_thinking_switch",
    }

    def __init__(
        self,
        provider_id: str,
        model: str,
        base_url: str = "",
        api_key: str = "",
        thinking_level: str = "auto",
        *,
        api_format: str = "openai-chat-completions",
        reasoning_parameter: str = "",
        thinking_api_value: str = "",
    ):
        self.provider_id = provider_id
        self.model = model
        self.base_url = base_url
        self.api_key = normalize_api_key(api_key)
        self.thinking_level = thinking_level
        self.api_format = api_format or "openai-chat-completions"
        self.reasoning_parameter = reasoning_parameter or ""
        self.thinking_api_value = thinking_api_value or thinking_level
        if self.reasoning_parameter not in self.SUPPORTED_REASONING_PARAMETERS:
            raise ValueError(f"不支持的原生思考参数: {self.reasoning_parameter}")
        if self.api_format not in self.SUPPORTED_API_FORMATS and self.provider_id != "mock":
            raise ValueError(f"不支持的 API 格式: {self.api_format}")

    def complete(self, pack: PromptPack) -> ModelResult:
        if self.provider_id == "mock":
            return self._mock_complete(pack)
        if self.api_format == "anthropic-messages":
            return self._anthropic_messages(pack)
        return self._openai_compatible(pack)

    def _mock_complete(self, pack: PromptPack) -> ModelResult:
        started = time.perf_counter()
        content = dumps(
            {
                "message": "已根据当前学习目标整理好下一步。mock provider 用于本地无密钥调试。",
                "task": pack.context_pack.get("task_type", "unknown"),
            }
        )
        latency = int((time.perf_counter() - started) * 1000)
        prompt_text = dumps(pack.model_dump())
        return ModelResult(
            content=content,
            input_tokens=estimate_tokens(prompt_text),
            output_tokens=estimate_tokens(content),
            latency_ms=latency,
            model=self.model,
        )

    def _reasoning_value(self) -> str:
        return (self.thinking_api_value or self.thinking_level or "").strip()

    def _apply_openai_reasoning(self, payload: dict[str, Any]) -> None:
        value = self._reasoning_value()
        if self.reasoning_parameter == "openai_reasoning_effort" and value and self.thinking_level not in {"", "auto", "off"}:
            payload["reasoning_effort"] = value
        elif self.reasoning_parameter == "deepseek_thinking":
            if self.thinking_level == "off" or not value:
                payload["thinking"] = {"type": "disabled"}
                return
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = value

    def _apply_anthropic_reasoning(self, payload: dict[str, Any]) -> None:
        value = self._reasoning_value()
        if not value or self.thinking_level in {"", "off", "auto"}:
            return
        if self.reasoning_parameter == "anthropic_adaptive_thinking":
            payload["thinking"] = {"type": "adaptive"}
            payload["output_config"] = {"effort": value}
        elif self.reasoning_parameter == "anthropic_thinking_switch":
            payload["thinking"] = {"type": "enabled"}

    def _endpoint(self, base_url: str, suffix: str) -> str:
        clean_base = base_url.rstrip("/")
        clean_suffix = suffix if suffix.startswith("/") else f"/{suffix}"
        if clean_base.endswith("/v1") and clean_suffix.startswith("/v1/"):
            clean_suffix = clean_suffix[3:]
        return f"{clean_base}{clean_suffix}"

    def _openai_compatible(self, pack: PromptPack) -> ModelResult:
        started = time.perf_counter()
        base_url = (self.base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        api_key = normalize_api_key(self.api_key or os.getenv("LANGDRILL_PROVIDER_API_KEY", "") or os.getenv("OPENAI_API_KEY", ""))
        if self.provider_id == "local":
            base_url = (self.base_url or os.getenv("LOCAL_LLM_BASE_URL", base_url)).rstrip("/")
            api_key = normalize_api_key(self.api_key or os.getenv("LOCAL_LLM_API_KEY", api_key))
        if not api_key:
            raise RuntimeError("缺少 API key，请写入 .env。")
        api_key = validate_http_header_value(api_key, "API Key")

        system = "\n\n".join(module["content"] for module in pack.system_modules)
        developer_context: dict[str, Any] = {"context_pack": pack.context_pack}
        user_content = pack.user_content
        messages = [{"role": "system", "content": system}]
        if self.provider_id == "openai":
            messages.append({"role": "developer", "content": dumps(developer_context)})
        else:
            user_content = f"{dumps(developer_context)}\n\n{pack.user_content}"
        messages.append({"role": "user", "content": user_content})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        self._apply_openai_reasoning(payload)
        if pack.output_schema:
            payload["response_format"] = {"type": "json_object"}

        response = httpx.post(
            self._endpoint(base_url, "/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=60,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise RuntimeError("模型 API 密钥无效或未授权 (401)。请检查 API Key 配置。")
            raise RuntimeError(f"模型 API 请求失败 ({e.response.status_code}): {e.response.text[:200]}")
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        latency = int((time.perf_counter() - started) * 1000)
        return ModelResult(
            content=content,
            input_tokens=int(usage.get("prompt_tokens") or estimate_tokens(dumps(payload))),
            output_tokens=int(usage.get("completion_tokens") or estimate_tokens(content)),
            latency_ms=latency,
            model=self.model,
        )

    def _anthropic_messages(self, pack: PromptPack) -> ModelResult:
        started = time.perf_counter()
        base_url = (self.base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")).rstrip("/")
        api_key = normalize_api_key(self.api_key or os.getenv("LANGDRILL_PROVIDER_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", ""))
        if not api_key:
            raise RuntimeError("缺少 API key，请写入 .env。")
        api_key = validate_http_header_value(api_key, "API Key")

        system = "\n\n".join(module["content"] for module in pack.system_modules)
        developer_context = dumps({"context_pack": pack.context_pack})
        user_content = f"{developer_context}\n\n{pack.user_content}"
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system,
            "messages": [
                {"role": "user", "content": user_content},
            ],
        }
        self._apply_anthropic_reasoning(payload)
        response = httpx.post(
            self._endpoint(base_url, "/v1/messages"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json=payload,
            timeout=60,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise RuntimeError("模型 API 密钥无效或未授权 (401)。请检查 API Key 配置。")
            raise RuntimeError(f"模型 API 请求失败 ({e.response.status_code}): {e.response.text[:200]}")
        data = response.json()
        content_items = data.get("content", [])
        content = "\n".join(
            str(item.get("text", "")) for item in content_items if isinstance(item, dict) and item.get("type") == "text"
        ).strip()
        usage = data.get("usage", {})
        latency = int((time.perf_counter() - started) * 1000)
        return ModelResult(
            content=content,
            input_tokens=int(usage.get("input_tokens") or estimate_tokens(dumps(payload))),
            output_tokens=int(usage.get("output_tokens") or estimate_tokens(content)),
            latency_ms=latency,
            model=self.model,
        )
