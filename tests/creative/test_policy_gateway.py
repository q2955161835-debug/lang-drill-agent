from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from langdrill_agent.creative.models import CreativeModeSettings, PermissionProfile
from langdrill_agent.creative.policy import (
    ApprovalGrant,
    ToolPolicyGateway,
    ToolRequest,
)


def settings(profile: PermissionProfile | str, *, rules: list[dict] | None = None):
    return CreativeModeSettings(
        enabled=True,
        permission_profile=profile,
        rules=rules or [],
    )


def read_file(path: Path, workspace: Path) -> ToolRequest:
    return ToolRequest(
        tool_name="read",
        arguments={"path": str(path)},
        workspace_root=str(workspace),
        cwd=str(workspace),
        run_id="run-1",
    )


def write_file(path: Path, workspace: Path) -> ToolRequest:
    return ToolRequest(
        tool_name="write",
        arguments={"path": str(path), "content": "hello"},
        workspace_root=str(workspace),
        cwd=str(workspace),
        run_id="run-1",
    )


def bash(command: str, workspace: Path) -> ToolRequest:
    return ToolRequest(
        tool_name="bash",
        arguments={"command": command},
        workspace_root=str(workspace),
        cwd=str(workspace),
        run_id="run-1",
    )


@pytest.mark.parametrize(
    ("profile", "request_factory", "expected"),
    [
        (
            PermissionProfile.REQUEST_APPROVAL,
            lambda workspace, outside: bash("git status", workspace),
            "require_approval",
        ),
        (
            PermissionProfile.SMART_APPROVAL,
            lambda workspace, outside: read_file(workspace / "README.md", workspace),
            "allow",
        ),
        (
            PermissionProfile.SMART_APPROVAL,
            lambda workspace, outside: write_file(outside / "note.txt", workspace),
            "require_approval",
        ),
        (
            PermissionProfile.FULL_ACCESS,
            lambda workspace, outside: write_file(outside / "note.txt", workspace),
            "allow",
        ),
    ],
)
def test_permission_profiles(tmp_path, profile, request_factory, expected):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()

    decision = ToolPolicyGateway().evaluate(
        request_factory(workspace, outside),
        settings(profile),
    )

    assert decision.action == expected
    assert decision.normalized_targets


def test_custom_rule_precedence_denies_matching_write(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    request = write_file(workspace / "protected.txt", workspace)

    decision = ToolPolicyGateway().evaluate(
        request,
        settings(
            PermissionProfile.CUSTOM,
            rules=[
                {
                    "id": "allow-workspace",
                    "priority": 10,
                    "effect": "allow",
                    "tool": "write",
                    "path_prefix": str(workspace),
                },
                {
                    "id": "deny-protected",
                    "priority": 100,
                    "effect": "deny",
                    "tool": "write",
                    "path_prefix": str(workspace / "protected.txt"),
                },
            ],
        ),
    )

    assert decision.action == "deny"
    assert decision.reason_code == "custom_rule_deny"


def test_approval_is_bound_to_exact_request_and_expiry(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    request = bash("git status", workspace)
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    grant = ApprovalGrant.issue(
        request,
        expires_at=now + timedelta(minutes=5),
    )

    assert grant.authorizes(request, now=now) is True
    modified = request.model_copy(
        update={"arguments": {"command": "git clean -fd"}},
    )
    assert grant.authorizes(modified, now=now) is False
    assert grant.authorizes(request, now=now + timedelta(minutes=6)) is False
