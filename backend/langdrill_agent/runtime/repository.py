from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import dumps, loads, new_id
from .models import (
    AgentRunRecord,
    AgentRunStep,
    ApprovalRequest,
    RunStatus,
    RuntimeEvent,
    ToolCallRecord,
)


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
            plan_version=int(row["plan_version"]),
            error_code=row["error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def set_completion_criteria(
        self,
        run_id: str,
        completion_criteria: list[str],
    ) -> AgentRunRecord:
        if not completion_criteria:
            raise ValueError("agent run completion criteria are required")
        cursor = self.conn.execute(
            """
            UPDATE agent_runs
            SET completion_criteria_json=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (dumps(completion_criteria), run_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(run_id)
        return self.get(run_id)

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

    def replace_plan(
        self,
        run_id: str,
        steps: list[AgentRunStep],
    ) -> list[AgentRunStep]:
        run = self.get(run_id)
        if not steps:
            raise ValueError("agent plan requires at least one step")
        sequences = [step.sequence for step in steps]
        if sorted(sequences) != list(range(1, len(steps) + 1)):
            raise ValueError("agent plan step sequence must be contiguous and start at one")
        plan_version = run.plan_version + 1
        self.conn.execute("SAVEPOINT replace_agent_plan")
        try:
            self.conn.execute(
                """
                UPDATE agent_run_steps
                SET status='cancelled', lease_owner='', lease_expires_at=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE run_id=? AND plan_version=? AND status IN ('pending', 'running')
                """,
                (run_id, run.plan_version),
            )
            for step in steps:
                self.conn.execute(
                    """
                    INSERT INTO agent_run_steps
                    (id, run_id, plan_version, sequence, title, description,
                     tool_names_json, completion_criteria_json, status, attempts,
                     max_attempts, evidence_json, error_code)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, '{}', '')
                    """,
                    (
                        new_id("step"),
                        run_id,
                        plan_version,
                        step.sequence,
                        step.title,
                        step.description,
                        dumps(step.tool_names),
                        dumps(step.completion_criteria),
                        step.max_attempts,
                    ),
                )
            self.conn.execute(
                """
                UPDATE agent_runs
                SET plan_version=?, status=?, error_code='', updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (plan_version, RunStatus.queued.value, run_id),
            )
            self.append_event(
                run_id,
                "plan_replaced",
                {"plan_version": plan_version, "step_count": len(steps)},
            )
            self.conn.execute("RELEASE SAVEPOINT replace_agent_plan")
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT replace_agent_plan")
            self.conn.execute("RELEASE SAVEPOINT replace_agent_plan")
            raise
        return self.steps(run_id)

    def steps(
        self,
        run_id: str,
        *,
        current_plan_only: bool = True,
    ) -> list[AgentRunStep]:
        run = self.get(run_id)
        if current_plan_only:
            rows = self.conn.execute(
                """
                SELECT * FROM agent_run_steps
                WHERE run_id=? AND plan_version=?
                ORDER BY plan_version, sequence
                """,
                (run_id, run.plan_version),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM agent_run_steps
                WHERE run_id=? ORDER BY plan_version, sequence
                """,
                (run_id,),
            ).fetchall()
        return [self._step_from_row(row) for row in rows]

    def get_step(self, step_id: str) -> AgentRunStep:
        row = self.conn.execute(
            "SELECT * FROM agent_run_steps WHERE id=?",
            (step_id,),
        ).fetchone()
        if row is None:
            raise KeyError(step_id)
        return self._step_from_row(row)

    def claim_next_step(
        self,
        run_id: str,
        worker_id: str,
        *,
        lease_seconds: int = 300,
    ) -> AgentRunStep | None:
        clean_worker_id = worker_id.strip()
        if not clean_worker_id:
            raise ValueError("worker id is required")
        if lease_seconds < 1 or lease_seconds > 3600:
            raise ValueError("step lease must be between 1 and 3600 seconds")
        run = self.get(run_id)
        if run.status in {
            RunStatus.paused,
            RunStatus.completed,
            RunStatus.failed,
            RunStatus.cancelled,
        }:
            return None
        row = self.conn.execute(
            """
            SELECT * FROM agent_run_steps
            WHERE run_id=? AND plan_version=?
              AND status IN ('pending', 'running')
            ORDER BY sequence LIMIT 1
            """,
            (run_id, run.plan_version),
        ).fetchone()
        if row is None:
            return None
        if row["status"] == "running" and row["lease_expires_at"]:
            available = self.conn.execute(
                "SELECT ? <= CURRENT_TIMESTAMP",
                (row["lease_expires_at"],),
            ).fetchone()[0]
            if not available:
                return None
        resumed_from_expired_lease = row["status"] == "running"
        cursor = self.conn.execute(
            """
            UPDATE agent_run_steps
            SET status='running', attempts=attempts + 1, lease_owner=?,
                lease_expires_at=datetime('now', ?), error_code='',
                updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND attempts < max_attempts
              AND (
                status='pending'
                OR (status='running' AND lease_expires_at<=CURRENT_TIMESTAMP)
              )
            """,
            (
                clean_worker_id,
                f"+{lease_seconds} seconds",
                row["id"],
            ),
        )
        if cursor.rowcount != 1:
            return None
        self.conn.execute(
            """
            UPDATE agent_runs
            SET status=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND status=?
            """,
            (RunStatus.running.value, run_id, RunStatus.queued.value),
        )
        step = self.get_step(str(row["id"])).model_copy(
            update={"resumed_from_expired_lease": resumed_from_expired_lease}
        )
        self.append_event(
            run_id,
            "step_claimed",
            {
                "step_id": step.id,
                "sequence": step.sequence,
                "worker_id": clean_worker_id,
                "attempt": step.attempts,
                "resumed_from_expired_lease": resumed_from_expired_lease,
            },
        )
        return step

    def complete_step(
        self,
        step_id: str,
        *,
        evidence: dict[str, Any],
        worker_id: str = "",
    ) -> AgentRunStep:
        step = self.get_step(step_id)
        self._assert_step_lease(step, worker_id)
        cursor = self.conn.execute(
            """
            UPDATE agent_run_steps
            SET status='completed', evidence_json=?, lease_owner='',
                lease_expires_at=NULL, error_code='', updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='running'
            """,
            (dumps(evidence), step_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("agent run step is not running")
        completed = self.get_step(step_id)
        self.append_event(
            completed.run_id,
            "step_completed",
            {"step_id": completed.id, "evidence": evidence},
        )
        return completed

    def fail_step(
        self,
        step_id: str,
        *,
        error_code: str,
        evidence: dict[str, Any] | None = None,
        worker_id: str = "",
    ) -> AgentRunStep:
        step = self.get_step(step_id)
        self._assert_step_lease(step, worker_id)
        cursor = self.conn.execute(
            """
            UPDATE agent_run_steps
            SET status='failed', evidence_json=?, error_code=?, lease_owner='',
                lease_expires_at=NULL, updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='running'
            """,
            (dumps(evidence or {}), error_code, step_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("agent run step is not running")
        failed = self.get_step(step_id)
        self.append_event(
            failed.run_id,
            "step_failed",
            {"step_id": failed.id, "error_code": error_code},
        )
        return failed

    def retry_step(self, step_id: str) -> AgentRunStep:
        step = self.get_step(step_id)
        if step.status != "failed":
            raise ValueError("only a failed agent run step can be retried")
        if step.attempts >= step.max_attempts:
            raise ValueError("agent run step exhausted its attempts")
        self.conn.execute(
            """
            UPDATE agent_run_steps
            SET status='pending', lease_owner='', lease_expires_at=NULL,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (step_id,),
        )
        retried = self.get_step(step_id)
        self.append_event(
            retried.run_id,
            "step_retry_scheduled",
            {"step_id": step_id, "next_attempt": retried.attempts + 1},
        )
        return retried

    def record_tool_call(
        self,
        *,
        run_id: str,
        step_id: str,
        tool_name: str,
        input_payload: dict[str, Any],
    ) -> ToolCallRecord:
        self.get(run_id)
        step = self.get_step(step_id)
        if step.run_id != run_id:
            raise ValueError("tool call step does not belong to run")
        tool_call_id = new_id("toolcall")
        self.conn.execute(
            """
            INSERT INTO tool_calls
            (id, run_id, step_id, tool_name, status, input_json)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (tool_call_id, run_id, step_id, tool_name, dumps(input_payload)),
        )
        self.append_event(
            run_id,
            "tool_call_recorded",
            {"tool_call_id": tool_call_id, "step_id": step_id, "tool_name": tool_name},
        )
        return self.get_tool_call(tool_call_id)

    def finish_tool_call(
        self,
        tool_call_id: str,
        *,
        status: str,
        output_payload: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        error_code: str = "",
    ) -> ToolCallRecord:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("tool call terminal status is invalid")
        self.get_tool_call(tool_call_id)
        cursor = self.conn.execute(
            """
            UPDATE tool_calls
            SET status=?, output_json=?, evidence_json=?, error_code=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='pending'
            """,
            (
                status,
                dumps(output_payload or {}),
                dumps(evidence or {}),
                error_code,
                tool_call_id,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("tool call is no longer pending")
        finished = self.get_tool_call(tool_call_id)
        self.append_event(
            finished.run_id,
            f"tool_call_{status}",
            {
                "tool_call_id": finished.id,
                "step_id": finished.step_id,
                "tool_name": finished.tool_name,
                "error_code": error_code,
            },
        )
        return finished

    def get_tool_call(self, tool_call_id: str) -> ToolCallRecord:
        row = self.conn.execute(
            "SELECT * FROM tool_calls WHERE id=?",
            (tool_call_id,),
        ).fetchone()
        if row is None:
            raise KeyError(tool_call_id)
        return self._tool_call_from_row(row)

    def tool_calls(self, run_id: str) -> list[ToolCallRecord]:
        self.get(run_id)
        rows = self.conn.execute(
            "SELECT * FROM tool_calls WHERE run_id=? ORDER BY created_at, id",
            (run_id,),
        ).fetchall()
        return [self._tool_call_from_row(row) for row in rows]

    def request_approval(
        self,
        *,
        run_id: str,
        step_id: str,
        capability: str,
        risk_level: str,
        request_payload: dict[str, Any],
        tool_call_id: str | None = None,
    ) -> ApprovalRequest:
        self.get(run_id)
        step = self.get_step(step_id)
        if step.run_id != run_id:
            raise ValueError("approval step does not belong to run")
        if tool_call_id and self.get_tool_call(tool_call_id).run_id != run_id:
            raise ValueError("approval tool call does not belong to run")
        approval_id = new_id("approval")
        self.conn.execute(
            """
            INSERT INTO approval_requests
            (id, run_id, step_id, tool_call_id, capability, risk_level,
             status, request_json)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                approval_id,
                run_id,
                step_id,
                tool_call_id,
                capability,
                risk_level,
                dumps(request_payload),
            ),
        )
        self.append_event(
            run_id,
            "approval_requested",
            {"approval_id": approval_id, "step_id": step_id, "risk_level": risk_level},
        )
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> ApprovalRequest:
        row = self.conn.execute(
            "SELECT * FROM approval_requests WHERE id=?",
            (approval_id,),
        ).fetchone()
        if row is None:
            raise KeyError(approval_id)
        return self._approval_from_row(row)

    def approvals(self, run_id: str) -> list[ApprovalRequest]:
        self.get(run_id)
        rows = self.conn.execute(
            """
            SELECT * FROM approval_requests
            WHERE run_id=? ORDER BY created_at, id
            """,
            (run_id,),
        ).fetchall()
        return [self._approval_from_row(row) for row in rows]

    def pending_approvals(self) -> list[ApprovalRequest]:
        rows = self.conn.execute(
            """
            SELECT * FROM approval_requests
            WHERE status='pending' ORDER BY created_at, id
            """,
        ).fetchall()
        return [self._approval_from_row(row) for row in rows]

    def resolve_approval(
        self,
        approval_id: str,
        *,
        decision: str,
        decision_payload: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        if decision not in {"approved", "denied", "expired"}:
            raise ValueError("approval decision must be approved, denied or expired")
        approval = self.get_approval(approval_id)
        if approval.status != "pending":
            raise ValueError("approval is no longer pending")
        cursor = self.conn.execute(
            """
            UPDATE approval_requests
            SET status=?, decision_json=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='pending'
            """,
            (decision, dumps(decision_payload or {}), approval_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("approval is no longer pending")
        self.append_event(
            approval.run_id,
            f"approval_{decision}",
            {"approval_id": approval_id, "capability": approval.capability},
        )
        return self.get_approval(approval_id)

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
    def _assert_step_lease(step: AgentRunStep, worker_id: str) -> None:
        if step.status != "running":
            raise ValueError("agent run step is not running")
        if worker_id and step.lease_owner != worker_id:
            raise ValueError("agent run step lease is owned by another worker")

    @staticmethod
    def _step_from_row(row: sqlite3.Row) -> AgentRunStep:
        return AgentRunStep(
            id=row["id"],
            run_id=row["run_id"],
            plan_version=int(row["plan_version"]),
            sequence=int(row["sequence"]),
            title=row["title"],
            description=row["description"],
            tool_names=loads(row["tool_names_json"], []),
            completion_criteria=loads(row["completion_criteria_json"], []),
            status=row["status"],
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            evidence=loads(row["evidence_json"], {}),
            error_code=row["error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _tool_call_from_row(row: sqlite3.Row) -> ToolCallRecord:
        return ToolCallRecord(
            id=row["id"],
            run_id=row["run_id"],
            step_id=row["step_id"],
            tool_name=row["tool_name"],
            status=row["status"],
            input_payload=loads(row["input_json"], {}),
            output_payload=loads(row["output_json"], {}),
            evidence=loads(row["evidence_json"], {}),
            error_code=row["error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _approval_from_row(row: sqlite3.Row) -> ApprovalRequest:
        return ApprovalRequest(
            id=row["id"],
            run_id=row["run_id"],
            step_id=row["step_id"],
            tool_call_id=row["tool_call_id"],
            capability=row["capability"],
            risk_level=row["risk_level"],
            status=row["status"],
            request_payload=loads(row["request_json"], {}),
            decision=loads(row["decision_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> RuntimeEvent:
        return RuntimeEvent(
            id=row["id"],
            run_id=row["run_id"],
            event_type=row["event_type"],
            payload=loads(row["payload_json"], {}),
            created_at=row["created_at"],
        )
