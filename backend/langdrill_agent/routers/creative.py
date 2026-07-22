from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import PROJECT_ROOT
from ..creative.models import PermissionProfile
from ..creative.repository import CreativeRepository, CreativeRuntimeUnavailable
from ..db import init_db, transaction
from ..runtime.repository import AgentRunRepository

router = APIRouter(prefix="/api/creative", tags=["creative"])


class CreativeSettingsPatch(BaseModel):
    enabled: bool | None = None
    permission_profile: PermissionProfile | None = None
    rules: list[dict[str, Any]] | None = None
    rules_version: int | None = Field(default=None, ge=1)


class ApprovalResolveRequest(BaseModel):
    action: Literal["approve", "deny"]


def _desktop_pi_status_path() -> Path | None:
    appdata = os.getenv("APPDATA", "").strip()
    if not appdata:
        return None
    return Path(appdata) / "Lang Drill Agent" / "pi-runtime" / "status.json"


def _desktop_log_dir() -> Path | None:
    appdata = os.getenv("APPDATA", "").strip()
    if not appdata:
        return None
    return Path(appdata) / "Lang Drill Agent" / "logs"


def _read_desktop_pi_status() -> dict[str, Any] | None:
    status_path = _desktop_pi_status_path()
    if status_path is None or not status_path.is_file():
        return None
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _runtime_payload(conn) -> dict[str, Any]:
    repo = CreativeRepository(conn)
    db_status = repo.get_runtime_status()
    desktop = _read_desktop_pi_status() or {}
    state = str(desktop.get("state") or db_status.state)
    version = str(desktop.get("version") or db_status.version or "")
    updated_at = str(desktop.get("updated_at") or db_status.updated_at)
    detail = str(desktop.get("detail") or db_status.details.get("detail") or "")
    log_dir = _desktop_log_dir()
    log_path = str(log_dir / "pi-runtime.log") if log_dir else ""
    manual_install_command = (
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
        "\"scripts/desktop/repair-pi-runtime.ps1\""
    )
    failure_code = str(
        desktop.get("failure_code")
        or db_status.error_code
        or ("install_failed" if state == "install_failed" else "")
    )
    attempted_steps_raw = desktop.get("attempted_steps")
    if isinstance(attempted_steps_raw, list):
        attempted_steps = [str(item) for item in attempted_steps_raw]
    elif detail:
        attempted_steps = [detail]
    else:
        attempted_steps = []
    return {
        "state": state,
        "version": version,
        "error_code": db_status.error_code,
        "details": {**db_status.details, "detail": detail},
        "updated_at": updated_at,
        "ready": state == "ready",
        "log_path": log_path,
        "failure_code": failure_code,
        "attempted_steps": attempted_steps,
        "manual_install_command": manual_install_command,
    }


def _settings_payload(conn) -> dict[str, Any]:
    return CreativeRepository(conn).get_settings().model_dump(mode="json")


def _approval_payload(approval) -> dict[str, Any]:
    payload = approval.model_dump(mode="json")
    request_payload = payload.get("request_payload") or {}
    if isinstance(request_payload, dict):
        payload["request_payload"] = {
            "tool_call_id": str(request_payload.get("tool_call_id") or approval.tool_call_id or ""),
            "arguments": request_payload.get("arguments", {}),
            "normalized_targets": request_payload.get("normalized_targets", []),
        }
    else:
        payload["request_payload"] = {
            "tool_call_id": str(approval.tool_call_id or ""),
            "arguments": {},
            "normalized_targets": [],
        }
    if "expires_at" not in payload:
        payload["expires_at"] = ""
    return payload


@router.get("/status")
def creative_status() -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        settings = _settings_payload(conn)
        runtime = _runtime_payload(conn)
        approvals = [
            _approval_payload(item)
            for item in AgentRunRepository(conn).pending_approvals()
        ]
    return {"settings": settings, "runtime": runtime, "approvals": approvals}


@router.get("/runtime-status")
def creative_runtime_status() -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        runtime = _runtime_payload(conn)
    return {"runtime": runtime}


@router.post("/settings")
def save_creative_settings(patch: CreativeSettingsPatch) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repo = CreativeRepository(conn)
        current = repo.get_settings()
        enabled = current.enabled if patch.enabled is None else patch.enabled
        profile = (
            current.permission_profile
            if patch.permission_profile is None
            else patch.permission_profile
        )
        try:
            saved = repo.save_settings(
                enabled=enabled,
                permission_profile=profile,
                rules=patch.rules,
                rules_version=patch.rules_version,
            )
        except CreativeRuntimeUnavailable as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CREATIVE_RUNTIME_UNAVAILABLE",
                    "params": {"reason": str(exc.status.error_code or exc.status.state)},
                },
            ) from exc
        repo.record_audit_event(
            event_type="settings_saved",
            reason_code="creative_settings_updated",
            payload={
                "enabled": saved.enabled,
                "permission_profile": saved.permission_profile.value,
            },
        )
    return {"settings": saved.model_dump(mode="json")}


@router.get("/approvals")
def list_creative_approvals() -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        approvals = [
            _approval_payload(item)
            for item in AgentRunRepository(conn).pending_approvals()
        ]
    return {"approvals": approvals}


@router.post("/approvals/{approval_id}/resolve")
def resolve_creative_approval(
    approval_id: str,
    request: ApprovalResolveRequest,
) -> dict[str, Any]:
    init_db()
    decision = "approved" if request.action == "approve" else "denied"
    with transaction() as conn:
        repo = AgentRunRepository(conn)
        creative_repo = CreativeRepository(conn)
        try:
            approval = repo.resolve_approval(
                approval_id,
                decision=decision,
                decision_payload={"source": "user", "action": request.action},
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "CREATIVE_APPROVAL_NOT_FOUND",
                    "params": {"approval_id": approval_id},
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CREATIVE_APPROVAL_NOT_PENDING",
                    "params": {"approval_id": approval_id, "reason": str(exc)},
                },
            ) from exc
        creative_repo.record_audit_event(
            event_type="approval_resolved",
            run_id=approval.run_id,
            reason_code=f"approval_{decision}",
            payload={
                "approval_id": approval_id,
                "capability": approval.capability,
                "decision": decision,
            },
        )
    return {"ok": True, "approval": _approval_payload(approval)}


@router.get("/audit")
def list_creative_audit_events(
    run_id: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repo = CreativeRepository(conn)
        events = repo.list_audit_events(limit=limit)
    if run_id:
        events = [event for event in events if event.run_id == run_id]
    return {"events": [event.model_dump(mode="json") for event in events]}


@router.post("/runtime/repair")
def repair_creative_runtime() -> dict[str, Any]:
    init_db()
    log_dir = _desktop_log_dir()
    log_path = str(log_dir / "pi-runtime.log") if log_dir else ""
    status_path = _desktop_pi_status_path()
    if status_path is None or not status_path.is_file():
        return {
            "ok": False,
            "log_path": log_path,
            "detail": (
                "Pi 运行时修复仅在桌面版可用；Web 开发模式下请确保 Node.js 可用且 "
                "runtime/pi-bridge/dist/src/index.js 已构建。"
            ),
        }
    script_path = PROJECT_ROOT / "scripts" / "desktop" / "repair-pi-runtime.ps1"
    if not script_path.is_file():
        return {
            "ok": False,
            "log_path": log_path,
            "detail": f"修复脚本缺失：{script_path}",
        }
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-TargetRoot",
                str(Path(os.getenv("LOCALAPPDATA", "")) / "Lang Drill Agent" / "runtime" / "pi"),
                "-ManifestPath",
                str(PROJECT_ROOT / "runtime" / "pi-runtime-manifest.json"),
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        ok = completed.returncode == 0
        detail = (completed.stdout + completed.stderr).strip()[-2000:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        ok = False
        detail = f"修复脚本执行失败：{exc}"
    return {"ok": ok, "log_path": log_path, "detail": detail}


@router.post("/runtime/open-log")
def open_creative_runtime_log() -> dict[str, Any]:
    log_dir = _desktop_log_dir()
    log_path = str(log_dir / "pi-runtime.log") if log_dir else ""
    if log_dir and log_dir.is_dir() and os.name == "nt":
        try:
            os.startfile(str(log_dir))  # type: ignore[attr-defined]
        except OSError:
            pass
    return {"path": log_path}
