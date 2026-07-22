from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentRunRecord(BaseModel):
    id: str
    session_id: str | None
    task_type: str
    status: RunStatus
    goal: str
    completion_criteria: list[str] = Field(default_factory=list)
    plan_version: int = 0
    error_code: str = ""
    created_at: str = ""
    updated_at: str = ""


class AgentRunStep(BaseModel):
    id: str
    run_id: str
    plan_version: int = 0
    sequence: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    tool_names: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = Field(default=2, ge=1, le=5)
    lease_owner: str = ""
    lease_expires_at: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    error_code: str = ""
    created_at: str = ""
    updated_at: str = ""


class ToolCallRecord(BaseModel):
    id: str
    run_id: str
    step_id: str
    tool_name: str
    status: str = "pending"
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error_code: str = ""
    created_at: str = ""
    updated_at: str = ""


class ApprovalRequest(BaseModel):
    id: str
    run_id: str
    step_id: str
    tool_call_id: str | None = None
    capability: str
    risk_level: str = "medium"
    status: str = "pending"
    request_payload: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class RuntimeEvent(BaseModel):
    id: int
    run_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str
