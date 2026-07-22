from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuntimeErrorPayload(BaseModel):
    code: str
    detail: str
    params: dict[str, Any] = Field(default_factory=dict)


class RuntimeServiceError(RuntimeError):
    def __init__(self, code: str, detail: str, **params: Any) -> None:
        super().__init__(detail)
        self.payload = RuntimeErrorPayload(code=code, detail=detail, params=params)
