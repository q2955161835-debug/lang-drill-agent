from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PermissionProfile(str, Enum):
    REQUEST_APPROVAL = "request_approval"
    SMART_APPROVAL = "smart_approval"
    FULL_ACCESS = "full_access"
    CUSTOM = "custom"


class PiRuntimeStatus(BaseModel):
    state: Literal[
        "not_installed",
        "installing",
        "ready",
        "install_failed",
        "corrupt",
    ] = "not_installed"
    version: str | None = None
    error_code: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    updated_at: str = ""


class CreativeModeSettings(BaseModel):
    enabled: bool = False
    permission_profile: PermissionProfile = PermissionProfile.REQUEST_APPROVAL
    rules_version: int = Field(default=1, ge=1)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class PolicyDecision(BaseModel):
    action: Literal["allow", "require_approval", "deny"]
    reason_code: str
    normalized_targets: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class CreativeAuditEvent(BaseModel):
    id: str
    run_id: str = ""
    session_id: str = ""
    event_type: str
    reason_code: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
