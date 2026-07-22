from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import AgentRunStep

ToolInput = TypeVar("ToolInput", bound=BaseModel)


class ToolInputValidationError(ValueError):
    pass


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    output: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error_code: str = ""


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    step_id: str
    cancellation_requested: Callable[[], bool]
    trace: Callable[[str, dict[str, Any]], None]


class RuntimeTool(Generic[ToolInput]):
    def __init__(
        self,
        *,
        name: str,
        input_model: type[ToolInput],
        execute: Callable[[ToolInput, ToolExecutionContext], ToolExecutionResult],
        input_factory: Callable[[AgentRunStep], dict[str, Any]] | None = None,
    ) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("runtime tool name is required")
        self.name = clean_name
        self.input_model = input_model
        self.execute = execute
        self.input_factory = input_factory

    def input_for(self, step: AgentRunStep) -> dict[str, Any]:
        if self.input_factory is None:
            return {}
        payload = self.input_factory(step)
        if not isinstance(payload, dict):
            raise ToolInputValidationError("runtime tool input factory must return an object")
        return payload

    def validate_input(self, payload: dict[str, Any]) -> ToolInput:
        unknown = sorted(set(payload) - set(self.input_model.model_fields))
        if unknown:
            raise ToolInputValidationError(
                "runtime tool input has unknown fields: " + ", ".join(unknown)
            )
        try:
            return self.input_model.model_validate(payload)
        except ValidationError as exc:
            raise ToolInputValidationError(
                f"runtime tool input validation failed: {exc}"
            ) from exc


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RuntimeTool] = {}

    def register(self, tool: RuntimeTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"runtime tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> RuntimeTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"runtime tool is not registered: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._tools)
