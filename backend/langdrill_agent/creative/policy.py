from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..utils import dumps
from .command_rules import (
    catastrophic_reason,
    command_executable,
    command_network_hosts,
    is_read_only_command,
    normalize_command,
)
from .models import CreativeModeSettings, PermissionProfile, PolicyDecision
from .path_rules import is_within, normalize_path, tool_path_targets


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    workspace_root: str = Field(min_length=1)
    cwd: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str = ""


class NormalizedToolRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    workspace_root: str
    cwd: str
    run_id: str
    session_id: str = ""
    targets: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    command: str = ""
    executable: str = ""
    network_hosts: list[str] = Field(default_factory=list)


class ApprovalGrant(BaseModel):
    request_hash: str
    run_id: str
    expires_at: datetime

    @classmethod
    def issue(cls, request: ToolRequest, *, expires_at: datetime) -> ApprovalGrant:
        normalized = normalize_tool_request(request)
        return cls(
            request_hash=_request_hash(normalized),
            run_id=normalized.run_id,
            expires_at=expires_at,
        )

    def authorizes(self, request: ToolRequest, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        normalized = normalize_tool_request(request)
        return (
            current < expires_at
            and normalized.run_id == self.run_id
            and _request_hash(normalized) == self.request_hash
        )


class ToolPolicyGateway:
    def evaluate(
        self,
        request: ToolRequest,
        settings: CreativeModeSettings,
    ) -> PolicyDecision:
        try:
            normalized = normalize_tool_request(request)
        except ValueError as exc:
            return PolicyDecision(
                action="deny",
                reason_code="tool_target_invalid",
                details={"error": str(exc)},
            )
        if not settings.enabled:
            return self._decision("deny", "creative_mode_disabled", normalized)
        if normalized.command:
            hard_block = catastrophic_reason(normalized.command)
            if hard_block:
                return self._decision("deny", hard_block, normalized)

        custom = self._custom_rule_decision(normalized, settings)
        if custom is not None:
            return custom

        profile = settings.permission_profile
        if profile is PermissionProfile.REQUEST_APPROVAL:
            return self._decision(
                "require_approval",
                "profile_request_approval",
                normalized,
            )
        if profile is PermissionProfile.FULL_ACCESS:
            return self._decision("allow", "profile_full_access", normalized)
        if profile is PermissionProfile.SMART_APPROVAL:
            return self._smart_decision(normalized)
        return self._decision(
            "require_approval",
            "custom_profile_no_matching_rule",
            normalized,
        )

    def _smart_decision(self, request: NormalizedToolRequest) -> PolicyDecision:
        if request.tool_name == "read" and all(
            is_within(path, request.workspace_root) for path in request.paths
        ):
            return self._decision("allow", "smart_workspace_read", request)
        if request.tool_name in {"write", "edit"}:
            if all(is_within(path, request.workspace_root) for path in request.paths):
                return self._decision("allow", "smart_workspace_write", request)
            return self._decision(
                "require_approval",
                "smart_outside_workspace_write",
                request,
            )
        if request.tool_name == "bash" and is_read_only_command(request.command):
            return self._decision("allow", "smart_read_only_command", request)
        return self._decision(
            "require_approval",
            "smart_approval_required",
            request,
        )

    def _custom_rule_decision(
        self,
        request: NormalizedToolRequest,
        settings: CreativeModeSettings,
    ) -> PolicyDecision | None:
        if settings.permission_profile is not PermissionProfile.CUSTOM:
            return None
        rules = sorted(
            settings.rules,
            key=lambda item: (int(item.get("priority", 0)), str(item.get("id", ""))),
            reverse=True,
        )
        for rule in rules:
            if not self._rule_matches(rule, request):
                continue
            effect = str(rule.get("effect", "require_approval"))
            if effect not in {"allow", "require_approval", "deny"}:
                continue
            return self._decision(
                effect,
                f"custom_rule_{effect}",
                request,
                rule_id=str(rule.get("id", "")),
            )
        return None

    @staticmethod
    def _rule_matches(rule: dict[str, Any], request: NormalizedToolRequest) -> bool:
        tool_name = str(rule.get("tool", "")).strip()
        if tool_name and tool_name != request.tool_name:
            return False
        path_prefix = str(rule.get("path_prefix", "")).strip()
        if path_prefix:
            try:
                prefix = normalize_path(path_prefix, cwd=request.cwd)
            except ValueError:
                return False
            if not request.paths or not any(is_within(path, prefix) for path in request.paths):
                return False
        command_prefix = str(rule.get("command_prefix", "")).strip()
        if command_prefix and not request.command.casefold().startswith(command_prefix.casefold()):
            return False
        network_domain = str(rule.get("network_domain", "")).strip().casefold()
        if network_domain and network_domain not in request.network_hosts:
            return False
        return True

    @staticmethod
    def _decision(
        action: str,
        reason_code: str,
        request: NormalizedToolRequest,
        **details: Any,
    ) -> PolicyDecision:
        return PolicyDecision(
            action=action,
            reason_code=reason_code,
            normalized_targets=request.targets,
            details=details,
        )


def normalize_tool_request(request: ToolRequest) -> NormalizedToolRequest:
    tool_name = request.tool_name.strip().casefold()
    cwd = normalize_path(request.cwd, cwd=request.cwd)
    workspace_root = normalize_path(request.workspace_root, cwd=cwd)
    arguments = dict(request.arguments)
    paths = tool_path_targets(tool_name, arguments, cwd=cwd)
    command = ""
    executable = ""
    network_hosts: list[str] = []
    targets = list(paths)
    if tool_name == "bash":
        raw_command = arguments.get("command")
        if not isinstance(raw_command, str):
            raise ValueError("bash requires a string command")
        command = normalize_command(raw_command)
        executable = command_executable(command)
        network_hosts = command_network_hosts(command)
        targets.append(f"command:{executable}")
        targets.extend(f"network:{host}" for host in network_hosts)
        arguments["command"] = command
    elif tool_name not in {"read", "write", "edit"}:
        targets.append(f"tool:{tool_name}")
    return NormalizedToolRequest(
        tool_name=tool_name,
        arguments=arguments,
        workspace_root=workspace_root,
        cwd=cwd,
        run_id=request.run_id,
        session_id=request.session_id,
        targets=targets,
        paths=paths,
        command=command,
        executable=executable,
        network_hosts=network_hosts,
    )


def _request_hash(request: NormalizedToolRequest) -> str:
    payload = {
        "tool_name": request.tool_name,
        "arguments": request.arguments,
        "workspace_root": request.workspace_root,
        "cwd": request.cwd,
        "run_id": request.run_id,
        "session_id": request.session_id,
        "targets": request.targets,
    }
    return hashlib.sha256(dumps(payload).encode("utf-8")).hexdigest()
