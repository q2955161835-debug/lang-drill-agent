from __future__ import annotations

import base64
import binascii
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .models import PromptPack
from .utils import dumps, estimate_tokens, normalize_api_key, validate_http_header_value


class ModelProviderError(RuntimeError):
    """模型供应商调用失败。

    继承 RuntimeError，让既有的 `except RuntimeError` 兜底处理器（api.py 与 agents.py
    共 12 处）保持兼容，同时给出一个明确的类型供新代码使用。

    所有出站调用的失败都必须在本模块归一化成这个异常：httpx 的超时、连接错误和
    响应体解析错误都不继承 RuntimeError，若直接向上抛出会绕过全部兜底逻辑。
    """


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

    REQUEST_TIMEOUT_SECONDS = 60

    def _post(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> httpx.Response:
        """发起模型请求，并把所有 httpx 传输层异常归一化成 ModelProviderError。"""
        try:
            return httpx.post(url, headers=headers, json=payload, timeout=self.REQUEST_TIMEOUT_SECONDS)
        except httpx.TimeoutException as exc:
            # 必须排在 HTTPError 之前：TimeoutException 是 HTTPError 的子类。
            raise ModelProviderError(
                f"模型 API 请求超时（{self.REQUEST_TIMEOUT_SECONDS} 秒未返回）。请检查网络或稍后重试。"
            ) from exc
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise ModelProviderError(
                f"无法连接模型 API（{type(exc).__name__}）：{exc}。请检查 Base URL 和网络。"
            ) from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ModelProviderError(
                    "模型 API 密钥无效或未授权 (401)。请检查 API Key 配置。"
                ) from e
            raise ModelProviderError(
                f"模型 API 请求失败 ({e.response.status_code}): {e.response.text[:200]}"
            ) from e

    @staticmethod
    def _decode_json(response: httpx.Response) -> Any:
        """解析响应体。代理或错误页可能在 HTTP 200 下返回 HTML，必须归一化而不是抛 ValueError。"""
        try:
            return response.json()
        except ValueError as exc:
            preview = response.text[:200].strip().replace("\n", " ")
            raise ModelProviderError(
                f"模型 API 返回的不是合法 JSON（HTTP {response.status_code}）：{preview}"
            ) from exc

    def _endpoint(self, base_url: str, suffix: str) -> str:
        clean_base = base_url.rstrip("/")
        clean_suffix = suffix if suffix.startswith("/") else f"/{suffix}"
        if clean_base.endswith("/v1") and clean_suffix.startswith("/v1/"):
            clean_suffix = clean_suffix[3:]
        return f"{clean_base}{clean_suffix}"

    def _openai_user_content(self, text: str, pack: PromptPack) -> str | list[dict[str, Any]]:
        image_items = [item for item in pack.attachments if item.type == "image" and item.data_url]
        if not image_items:
            return text
        content: list[dict[str, Any]] = [
            {"type": "text", "text": text or "请识别并说明这些图片内容。"}
        ]
        for item in image_items:
            content.append({"type": "image_url", "image_url": {"url": item.data_url}})
        return content

    def _anthropic_user_content(self, text: str, pack: PromptPack) -> str | list[dict[str, Any]]:
        image_items = [item for item in pack.attachments if item.type == "image" and item.data_url]
        if not image_items:
            return text
        content: list[dict[str, Any]] = [
            {"type": "text", "text": text or "请识别并说明这些图片内容。"}
        ]
        for item in image_items:
            media_type, data = self._image_data_url_parts(item.data_url, item.mime_type)
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                }
            )
        return content

    def _image_data_url_parts(self, data_url: str, fallback_mime: str = "") -> tuple[str, str]:
        clean = data_url.strip()
        media_type = (fallback_mime or "image/png").strip() or "image/png"
        data = clean
        if clean.startswith("data:"):
            try:
                header, data = clean.split(",", 1)
            except ValueError as exc:
                raise RuntimeError("图片附件 data URL 格式不正确。") from exc
            header_mime = header.removeprefix("data:").split(";", 1)[0].strip()
            media_type = header_mime or media_type
        try:
            base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError("图片附件不是有效的 base64 数据。") from exc
        return media_type, data

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
        messages.append({"role": "user", "content": self._openai_user_content(user_content, pack)})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        self._apply_openai_reasoning(payload)
        if pack.output_schema:
            payload["response_format"] = {"type": "json_object"}

        response = self._post(
            self._endpoint(base_url, "/chat/completions"),
            {"Authorization": f"Bearer {api_key}"},
            payload,
        )
        self._raise_for_status(response)
        data = self._decode_json(response)
        try:
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens") or estimate_tokens(dumps(payload)))
            output_tokens = int(usage.get("completion_tokens") or estimate_tokens(content or ""))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise ModelProviderError(
                f"模型 API 响应结构不符合 OpenAI Chat Completions 约定：{str(data)[:200]}"
            ) from exc
        if not isinstance(content, str):
            raise ModelProviderError("模型 API 未返回文本内容（content 为空或非文本）。")
        latency = int((time.perf_counter() - started) * 1000)
        return ModelResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
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
                {"role": "user", "content": self._anthropic_user_content(user_content, pack)},
            ],
        }
        self._apply_anthropic_reasoning(payload)
        response = self._post(
            self._endpoint(base_url, "/v1/messages"),
            {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            payload,
        )
        self._raise_for_status(response)
        data = self._decode_json(response)
        try:
            content_items = data.get("content") or []
            content = "\n".join(
                str(item.get("text", ""))
                for item in content_items
                if isinstance(item, dict) and item.get("type") == "text"
            ).strip()
            usage = data.get("usage") or {}
            input_tokens = int(usage.get("input_tokens") or estimate_tokens(dumps(payload)))
            output_tokens = int(usage.get("output_tokens") or estimate_tokens(content))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise ModelProviderError(
                f"模型 API 响应结构不符合 Anthropic Messages 约定：{str(data)[:200]}"
            ) from exc
        latency = int((time.perf_counter() - started) * 1000)
        return ModelResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency,
            model=self.model,
        )
