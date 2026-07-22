from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field

from .supervisor import PiProcessExited, PiProcessSupervisor

_SENSITIVE_KEYS = {
    "apikey",
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
}


class PiRunRequest(BaseModel):
    request_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    thinking_level: str = "off"
    api_key: str = ""


class PiAdapter:
    def __init__(self, supervisor: PiProcessSupervisor, *, max_restarts: int = 1) -> None:
        self.supervisor = supervisor
        self.max_restarts = max_restarts

    def run(self, request: PiRunRequest) -> Iterator[dict[str, Any]]:
        command = {
            "type": "run",
            "requestId": request.request_id,
            "prompt": request.prompt,
            "provider": request.provider,
            "model": request.model,
            "thinkingLevel": request.thinking_level,
            "apiKey": request.api_key,
        }
        restarts = 0
        while True:
            try:
                self.supervisor.start()
                self.supervisor.send(command)
                while True:
                    event = self.supervisor.read_event(timeout=120)
                    if event.get("requestId") not in {None, request.request_id}:
                        continue
                    clean = _redact(event)
                    yield clean
                    if event.get("type") in {
                        "run.completed",
                        "run.failed",
                        "run.cancelled",
                    }:
                        return
            except PiProcessExited as exc:
                if restarts >= self.max_restarts:
                    yield {
                        "type": "run.failed",
                        "requestId": request.request_id,
                        "errorCode": "PI_PROCESS_EXITED",
                        "error": str(exc),
                    }
                    return
                restarts += 1
                self.supervisor.restart()
                yield {
                    "type": "runtime.restarted",
                    "requestId": request.request_id,
                    "attempt": restarts,
                }

    def cancel(self, request_id: str) -> None:
        self.supervisor.send(
            {
                "type": "cancel",
                "requestId": f"cancel-{request_id}",
                "targetRequestId": request_id,
            }
        )

    def send_tool_result(
        self,
        *,
        request_id: str,
        tool_call_id: str,
        output: str,
        is_error: bool,
    ) -> None:
        self.supervisor.send(
            {
                "type": "tool.result",
                "requestId": f"tool-result-{tool_call_id}",
                "targetRequestId": request_id,
                "toolCallId": tool_call_id,
                "output": output,
                "isError": is_error,
            }
        )


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.casefold() in _SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
