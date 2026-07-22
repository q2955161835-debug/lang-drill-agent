from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import dumps, loads, new_id
from .models import AgentRunRecord, RunStatus, RuntimeEvent


class AgentRunRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(
        self,
        *,
        session_id: str | None,
        task_type: str,
        goal: str = "",
        completion_criteria: list[str] | None = None,
    ) -> AgentRunRecord:
        run_id = new_id("run")
        self.conn.execute(
            """
            INSERT INTO agent_runs
            (id, session_id, task_type, status, goal, completion_criteria_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                task_type,
                RunStatus.queued.value,
                goal,
                dumps(completion_criteria or []),
            ),
        )
        return self.get(run_id)

    def get(self, run_id: str) -> AgentRunRecord:
        row = self.conn.execute(
            "SELECT * FROM agent_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return AgentRunRecord(
            id=row["id"],
            session_id=row["session_id"],
            task_type=row["task_type"],
            status=row["status"],
            goal=row["goal"],
            completion_criteria=loads(row["completion_criteria_json"], []),
            error_code=row["error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def set_status(
        self,
        run_id: str,
        status: RunStatus | str,
        *,
        error_code: str = "",
    ) -> AgentRunRecord:
        normalized_status = RunStatus(status)
        cursor = self.conn.execute(
            """
            UPDATE agent_runs
            SET status = ?, error_code = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (normalized_status.value, error_code, run_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(run_id)
        run = self.get(run_id)
        if normalized_status is RunStatus.completed:
            from ..memory.hooks import MemoryHooks

            MemoryHooks(self.conn).on_agent_run_complete(
                run_id=run.id,
                goal=run.goal or run.task_type,
                outcome="completed",
            )
        return run

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        self.get(run_id)
        cursor = self.conn.execute(
            """
            INSERT INTO agent_run_events (run_id, event_type, payload_json)
            VALUES (?, ?, ?)
            """,
            (run_id, event_type, dumps(payload or {})),
        )
        row = self.conn.execute(
            "SELECT * FROM agent_run_events WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to load appended runtime event")
        return self._event_from_row(row)

    def events_after(self, run_id: str, event_id: int) -> list[RuntimeEvent]:
        self.get(run_id)
        rows = self.conn.execute(
            """
            SELECT * FROM agent_run_events
            WHERE run_id = ? AND id > ?
            ORDER BY id
            """,
            (run_id, event_id),
        ).fetchall()
        return [self._event_from_row(row) for row in rows]

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> RuntimeEvent:
        return RuntimeEvent(
            id=row["id"],
            run_id=row["run_id"],
            event_type=row["event_type"],
            payload=loads(row["payload_json"], {}),
            created_at=row["created_at"],
        )
