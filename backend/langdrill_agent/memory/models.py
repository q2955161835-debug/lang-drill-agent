from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MemoryCategory = Literal[
    "core",
    "semantic",
    "episodic",
    "procedural",
    "temporal",
    "preference",
    "profile",
    "learning_weakness",
]
MemoryStatus = Literal["active", "archived", "superseded", "deleted"]


class MemoryCandidate(BaseModel):
    id: str = ""
    category: MemoryCategory
    scope: str = "global"
    content: str = Field(min_length=1, max_length=20_000)
    normalized_key: str = ""
    confidence: float = Field(default=0.7, ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    status: str = "staged"
    reason: str = ""
    valid_from: str | None = None
    valid_to: str | None = None
    expires_at: str | None = None
    pinned: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class MemoryItem(BaseModel):
    id: str
    category: MemoryCategory
    scope: str = "global"
    content: str
    normalized_key: str = ""
    confidence: float = 0.7
    importance: float = 0.5
    status: MemoryStatus = "active"
    valid_from: str | None = None
    valid_to: str | None = None
    expires_at: str | None = None
    supersedes_id: str | None = None
    pinned: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class MemoryEvidence(BaseModel):
    id: str
    candidate_id: str | None = None
    memory_id: str | None = None
    evidence_type: str = "reference"
    evidence_ref: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class MemoryRevision(BaseModel):
    id: int
    memory_id: str
    operation: Literal["ADD", "UPDATE", "SUPERSEDE", "DELETE", "RESTORE", "ARCHIVE"]
    content: str
    snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
