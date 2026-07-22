from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..models import PromptPack
from .workflows import WorkflowResolver


class PlanValidationError(ValueError):
    pass


class PlannerProvider(Protocol):
    def complete(self, pack: PromptPack): ...


class PlannedStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(default=1, ge=1, le=20)
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=1000)
    tool_names: list[str] = Field(min_length=1, max_length=12)
    completion_criteria: list[str] = Field(min_length=1, max_length=12)
    max_attempts: int = Field(default=2, ge=1, le=5)


class AgentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=3, max_length=500)
    completion_criteria: list[str] = Field(min_length=1, max_length=20)
    steps: list[PlannedStep] = Field(min_length=1, max_length=20)
    workflow_skill_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_unique_titles(self) -> AgentPlan:
        titles = [" ".join(step.title.split()).casefold() for step in self.steps]
        if len(titles) != len(set(titles)):
            raise ValueError("agent plan step titles must be unique")
        return self


class AgentRunPlanner:
    def __init__(
        self,
        provider: PlannerProvider,
        *,
        workflow_resolver: WorkflowResolver | None = None,
    ) -> None:
        self.provider = provider
        self.workflow_resolver = workflow_resolver or WorkflowResolver()

    def plan(
        self,
        request: str,
        *,
        context: dict[str, Any],
        tools: Iterable[str | object],
    ) -> AgentPlan:
        clean_request = request.strip()
        if not clean_request:
            raise PlanValidationError("agent plan request cannot be empty")
        tool_names = _tool_names(tools)
        if not tool_names:
            raise PlanValidationError("agent plan requires at least one registered tool")
        pack = PromptPack(
            system_modules=[
                {
                    "id": "runtime.agent_planner",
                    "version": "1.0.0",
                    "content": (
                        "Create a JSON execution plan using only registered tools. "
                        "Every plan and step needs deterministic completion criteria. "
                        "Do not claim work is complete and do not execute tools."
                    ),
                }
            ],
            context_pack={
                "task_type": "agentic_planning",
                "registered_tools": sorted(tool_names),
                "runtime_context": context,
            },
            user_content=clean_request,
            output_schema=AgentPlan.model_json_schema(),
        )
        try:
            result = self.provider.complete(pack)
            payload = _json_payload(str(result.content))
            plan = AgentPlan.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
            raise PlanValidationError(f"agent plan validation failed: {exc}") from exc

        unknown_tools = sorted(
            {
                tool_name
                for step in plan.steps
                for tool_name in step.tool_names
                if tool_name not in tool_names
            }
        )
        if unknown_tools:
            raise PlanValidationError(
                "agent plan references unknown tool: " + ", ".join(unknown_tools)
            )
        normalized_steps = [
            step.model_copy(update={"sequence": index})
            for index, step in enumerate(plan.steps, start=1)
        ]
        workflow_skill_ids = [
            skill.id for skill in self.workflow_resolver.resolve(clean_request)
        ]
        return plan.model_copy(
            update={
                "steps": normalized_steps,
                "workflow_skill_ids": workflow_skill_ids,
            }
        )


def _tool_names(tools: Iterable[str | object]) -> set[str]:
    names: set[str] = set()
    for tool in tools:
        name = tool if isinstance(tool, str) else getattr(tool, "name", "")
        clean_name = str(name).strip()
        if clean_name:
            names.add(clean_name)
    return names


def _json_payload(content: str) -> dict[str, Any]:
    clean = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", clean, re.DOTALL | re.IGNORECASE)
    if fenced:
        clean = fenced.group(1).strip()
    payload = json.loads(clean)
    if not isinstance(payload, dict):
        raise TypeError("agent plan response must be a JSON object")
    return payload
