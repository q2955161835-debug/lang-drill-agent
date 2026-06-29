from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .models import PromptPack
from .utils import dumps, estimate_tokens


@dataclass(frozen=True)
class ModelResult:
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str


class ModelProvider:
    def __init__(
        self,
        provider_id: str,
        model: str,
        base_url: str = "",
        api_key: str = "",
        thinking_level: str = "auto",
    ):
        self.provider_id = provider_id
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.thinking_level = thinking_level if thinking_level in {"auto", "low", "medium", "high"} else "auto"

    def complete(self, pack: PromptPack) -> ModelResult:
        if self.provider_id == "mock":
            return self._mock_complete(pack)
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

    def _thinking_instruction(self) -> str:
        if self.thinking_level == "low":
            return "优先快速响应，只做必要推理，答案保持简洁。"
        if self.thinking_level == "medium":
            return "进行适中推理，兼顾速度和准确性。"
        if self.thinking_level == "high":
            return "进行更充分的内部推理与校验，但只输出最终结论和必要解释。"
        return ""

    def _supports_reasoning_effort(self) -> bool:
        model_name = self.model.lower()
        return self.provider_id in {"openai", "local", "custom"} and any(
            keyword in model_name for keyword in ("o1", "o3", "o4", "gpt-5")
        )

    def _openai_compatible(self, pack: PromptPack) -> ModelResult:
        started = time.perf_counter()
        base_url = (self.base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        api_key = self.api_key or os.getenv("LANGDRILL_PROVIDER_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        if self.provider_id == "local":
            base_url = (self.base_url or os.getenv("LOCAL_LLM_BASE_URL", base_url)).rstrip("/")
            api_key = self.api_key or os.getenv("LOCAL_LLM_API_KEY", api_key)
        if not api_key:
            raise RuntimeError("缺少 API key，请写入 .env。")

        system = "\n\n".join(module["content"] for module in pack.system_modules)
        developer_context: dict[str, Any] = {"context_pack": pack.context_pack}
        thinking_instruction = self._thinking_instruction()
        if thinking_instruction:
            developer_context["thinking_level"] = self.thinking_level
            developer_context["thinking_instruction"] = thinking_instruction
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "developer", "content": dumps(developer_context)},
                {"role": "user", "content": pack.user_content},
            ],
        }
        if self._supports_reasoning_effort() and self.thinking_level != "auto":
            payload["reasoning_effort"] = self.thinking_level
        if pack.output_schema:
            payload["response_format"] = {"type": "json_object"}

        response = httpx.post(
            f"{base_url}/chat/completions",
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
