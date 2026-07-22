from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import dumps, loads, new_id
from .models import (
    CreativeAuditEvent,
    CreativeModeSettings,
    PermissionProfile,
    PiRuntimeStatus,
)


class CreativeRuntimeUnavailable(RuntimeError):
    def __init__(self, status: PiRuntimeStatus) -> None:
        reason = status.error_code or status.state
        super().__init__(f"creative runtime is unavailable: {reason}")
        self.status = status


class CreativeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_runtime_status(self) -> PiRuntimeStatus:
        row = self.conn.execute(
            "SELECT * FROM creative_runtime_status WHERE singleton_id=1"
        ).fetchone()
        if row is None:
            raise RuntimeError("creative runtime status is not initialized")
        return PiRuntimeStatus(
            state=row["state"],
            version=row["version"] or None,
            error_code=row["error_code"],
            details=loads(row["details_json"], {}),
            updated_at=row["updated_at"],
        )

    def save_runtime_status(
        self,
        *,
        state: str,
        version: str | None,
        error_code: str = "",
        details: dict[str, Any] | None = None,
    ) -> PiRuntimeStatus:
        status = PiRuntimeStatus(
            state=state,
            version=version,
            error_code=error_code,
            details=details or {},
        )
        self.conn.execute(
            """
            UPDATE creative_runtime_status
            SET state=?, version=?, error_code=?, details_json=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE singleton_id=1
            """,
            (
                status.state,
                status.version or "",
                status.error_code,
                dumps(status.details),
            ),
        )
        return self.get_runtime_status()

    def get_settings(self) -> CreativeModeSettings:
        row = self.conn.execute(
            "SELECT * FROM creative_mode_settings WHERE singleton_id=1"
        ).fetchone()
        if row is None:
            raise RuntimeError("creative mode settings are not initialized")
        return CreativeModeSettings(
            enabled=bool(row["enabled"]),
            permission_profile=row["permission_profile"],
            rules_version=int(row["rules_version"]),
            rules=loads(row["rules_json"], []),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_settings(
        self,
        *,
        enabled: bool,
        permission_profile: PermissionProfile | str,
        rules: list[dict[str, Any]] | None = None,
        rules_version: int | None = None,
    ) -> CreativeModeSettings:
        current = self.get_settings()
        profile = PermissionProfile(permission_profile)
        if enabled:
            status = self.get_runtime_status()
            if status.state != "ready":
                raise CreativeRuntimeUnavailable(status)
        next_rules = current.rules if rules is None else rules
        next_version = current.rules_version if rules_version is None else rules_version
        validated = CreativeModeSettings(
            enabled=enabled,
            permission_profile=profile,
            rules_version=next_version,
            rules=next_rules,
        )
        self.conn.execute(
            """
            UPDATE creative_mode_settings
            SET enabled=?, permission_profile=?, rules_version=?, rules_json=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE singleton_id=1
            """,
            (
                int(validated.enabled),
                validated.permission_profile.value,
                validated.rules_version,
                dumps(validated.rules),
            ),
        )
        return self.get_settings()

    def record_audit_event(
        self,
        *,
        event_type: str,
        run_id: str = "",
        session_id: str = "",
        reason_code: str = "",
        payload: dict[str, Any] | None = None,
    ) -> CreativeAuditEvent:
        clean_event_type = event_type.strip()
        if not clean_event_type:
            raise ValueError("creative audit event type is required")
        event_id = new_id("creativeaudit")
        self.conn.execute(
            """
            INSERT INTO creative_audit_events
            (id, run_id, session_id, event_type, reason_code, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                run_id,
                session_id,
                clean_event_type,
                reason_code,
                dumps(payload or {}),
            ),
        )
        return self._get_audit_event(event_id)

    def list_audit_events(self, *, limit: int = 100) -> list[CreativeAuditEvent]:
        if limit < 1 or limit > 1000:
            raise ValueError("creative audit event limit must be between 1 and 1000")
        rows = self.conn.execute(
            """
            SELECT * FROM creative_audit_events
            ORDER BY created_at DESC, id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._audit_event_from_row(row) for row in rows]

    def _get_audit_event(self, event_id: str) -> CreativeAuditEvent:
        row = self.conn.execute(
            "SELECT * FROM creative_audit_events WHERE id=?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return self._audit_event_from_row(row)

    @staticmethod
    def _audit_event_from_row(row: sqlite3.Row) -> CreativeAuditEvent:
        return CreativeAuditEvent(
            id=row["id"],
            run_id=row["run_id"],
            session_id=row["session_id"],
            event_type=row["event_type"],
            reason_code=row["reason_code"],
            payload=loads(row["payload_json"], {}),
            created_at=row["created_at"],
        )
