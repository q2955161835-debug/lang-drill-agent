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
    error_code: str = ""
    created_at: str = ""
    updated_at: str = ""


class RuntimeEvent(BaseModel):
    id: int
    run_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str
