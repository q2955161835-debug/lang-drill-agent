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
    def __init__(self, provider_id: str, model: str):
        self.provider_id = provider_id
        self.model = model

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

    def _openai_compatible(self, pack: PromptPack) -> ModelResult:
        started = time.perf_counter()
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        api_key = os.getenv("OPENAI_API_KEY", "")
        if self.provider_id == "local":
            base_url = os.getenv("LOCAL_LLM_BASE_URL", base_url).rstrip("/")
            api_key = os.getenv("LOCAL_LLM_API_KEY", api_key)
        if not api_key:
            raise RuntimeError("缺少 API key，请写入 .env。")

        system = "\n\n".join(module["content"] for module in pack.system_modules)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "developer", "content": dumps({"context_pack": pack.context_pack})},
                {"role": "user", "content": pack.user_content},
            ],
        }
        if pack.output_schema:
            payload["response_format"] = {"type": "json_object"}

        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
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
