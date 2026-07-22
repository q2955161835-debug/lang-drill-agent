from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from ..runtime.models import RunStatus
from ..runtime.repository import AgentRunRepository
from .pi_adapter import PiAdapter, PiRunRequest
from .policy import ToolPolicyGateway, ToolRequest, normalize_tool_request
from .repository import CreativeRepository


class CreativeToolResult(BaseModel):
    output: str = ""
    is_error: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class CreativeToolExecutor(Protocol):
    def execute(self, request: ToolRequest) -> CreativeToolResult: ...


class LocalCreativeToolExecutor:
    def execute(self, request: ToolRequest) -> CreativeToolResult:
        normalized = normalize_tool_request(request)
        if normalized.tool_name == "read":
            path = Path(normalized.paths[0])
            content = path.read_text(encoding="utf-8")
            return CreativeToolResult(
                output=content[:100_000],
                evidence={
                    "path_exists": path.exists(),
                    "content_hash": _content_hash(content),
                },
            )
        if normalized.tool_name == "write":
            path = Path(normalized.paths[0])
            path.parent.mkdir(parents=True, exist_ok=True)
            content = str(normalized.arguments.get("content", ""))
            path.write_text(content, encoding="utf-8")
            persisted = path.read_text(encoding="utf-8")
            return CreativeToolResult(
                output=f"wrote {path}",
                evidence={
                    "path_exists": path.exists(),
                    "content_hash": _content_hash(persisted),
                    "content_matches": persisted == content,
                },
            )
        if normalized.tool_name == "edit":
            path = Path(normalized.paths[0])
            old_text = str(normalized.arguments.get("oldText", ""))
            new_text = str(normalized.arguments.get("newText", ""))
            content = path.read_text(encoding="utf-8")
            if content.count(old_text) != 1:
                return CreativeToolResult(
                    output="edit target must match exactly once",
                    is_error=True,
                )
            updated = content.replace(old_text, new_text)
            path.write_text(updated, encoding="utf-8")
            persisted = path.read_text(encoding="utf-8")
            return CreativeToolResult(
                output=f"edited {path}",
                evidence={
                    "path_exists": path.exists(),
                    "content_hash": _content_hash(persisted),
                    "content_matches": persisted == updated,
                },
            )
        if normalized.tool_name == "bash":
            completed = subprocess.run(
                normalized.command,
                cwd=normalized.cwd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            output = (completed.stdout + completed.stderr)[-100_000:]
            return CreativeToolResult(
                output=output,
                is_error=completed.returncode != 0,
                evidence={"exit_code": completed.returncode},
            )
        return CreativeToolResult(
            output=f"unsupported creative tool: {normalized.tool_name}",
            is_error=True,
        )


class AgentRuntimeGateway:
    def __init__(
        self,
        conn,
        adapter: PiAdapter,
        *,
        workspace_root: Path,
        tool_executor: CreativeToolExecutor | None = None,
    ) -> None:
        self.conn = conn
        self.adapter = adapter
        self.workspace_root = workspace_root.resolve()
        self.tool_executor = tool_executor or LocalCreativeToolExecutor()
        self.run_repo = AgentRunRepository(conn)
        self.creative_repo = CreativeRepository(conn)
        self.policy = ToolPolicyGateway()

    def execute(self, run_id: str, request: PiRunRequest) -> None:
        run = self.run_repo.get(run_id)
        self.run_repo.set_status(run_id, RunStatus.running)
        self.run_repo.append_event(run_id, "pi_runtime_started", {})
        for event in self.adapter.run(request):
            event_type = str(event.get("type", "pi_event"))
            if event_type == "tool.requested":
                self._handle_tool_request(run_id, run.session_id or "", event)
                continue
            if event_type == "message.delta":
                self.run_repo.append_event(
                    run_id,
                    "message_delta",
                    {"delta": str(event.get("delta", ""))},
                )
                continue
            if event_type == "runtime.restarted":
                self.run_repo.append_event(run_id, "pi_runtime_restarted", event)
                continue
            if event_type == "run.completed":
                self._finish_verified_run(run_id)
                return
            if event_type in {"run.failed", "run.cancelled"}:
                status = (
                    RunStatus.cancelled
                    if event_type == "run.cancelled"
                    else RunStatus.failed
                )
                self.run_repo.set_status(
                    run_id,
                    status,
                    error_code=str(event.get("errorCode", "PI_RUN_FAILED")),
                )
                self.run_repo.append_event(run_id, event_type.replace(".", "_"), event)
                return

    def _handle_tool_request(
        self,
        run_id: str,
        session_id: str,
        event: dict[str, Any],
    ) -> None:
        tool_call_id = str(event.get("toolCallId", ""))
        step = self._active_step(run_id)
        tool_request = ToolRequest(
            tool_name=str(event.get("toolName", "")),
            arguments=dict(event.get("arguments") or {}),
            workspace_root=str(self.workspace_root),
            cwd=str(self.workspace_root),
            run_id=run_id,
            session_id=session_id,
        )
        call = self.run_repo.record_tool_call(
            run_id=run_id,
            step_id=step.id,
            tool_name=tool_request.tool_name,
            input_payload=tool_request.arguments,
        )
        decision = self.policy.evaluate(tool_request, self.creative_repo.get_settings())
        self.creative_repo.record_audit_event(
            event_type="tool_policy_decision",
            run_id=run_id,
            session_id=session_id,
            reason_code=decision.reason_code,
            payload={
                "tool_name": tool_request.tool_name,
                "action": decision.action,
                "normalized_targets": decision.normalized_targets,
            },
        )
        if decision.action == "deny":
            self.run_repo.finish_tool_call(
                call.id,
                status="failed",
                error_code=decision.reason_code,
            )
            self.adapter.send_tool_result(
                request_id=run_id,
                tool_call_id=tool_call_id,
                output=f"Tool denied: {decision.reason_code}",
                is_error=True,
            )
            return
        if decision.action == "require_approval":
            self.run_repo.request_approval(
                run_id=run_id,
                step_id=step.id,
                capability=tool_request.tool_name,
                risk_level="medium",
                tool_call_id=call.id,
                request_payload={
                    "tool_call_id": tool_call_id,
                    "arguments": tool_request.arguments,
                    "normalized_targets": decision.normalized_targets,
                },
            )
            self.run_repo.finish_tool_call(
                call.id,
                status="failed",
                error_code="APPROVAL_REQUIRED",
            )
            self.run_repo.fail_step(
                step.id,
                error_code="APPROVAL_REQUIRED",
                evidence={"approval_required": True},
                worker_id="pi-runtime",
            )
            self.run_repo.set_status(run_id, RunStatus.paused)
            self.adapter.send_tool_result(
                request_id=run_id,
                tool_call_id=tool_call_id,
                output="Tool approval is required before this request can continue.",
                is_error=True,
            )
            return
        result = self.tool_executor.execute(tool_request)
        evidence = {
            **result.evidence,
            "policy_decision": decision.reason_code,
            "criteria": {
                criterion: not result.is_error
                for criterion in step.completion_criteria
            },
        }
        self.run_repo.finish_tool_call(
            call.id,
            status="failed" if result.is_error else "completed",
            output_payload={"output": result.output},
            evidence=evidence,
            error_code="TOOL_EXECUTION_FAILED" if result.is_error else "",
        )
        self.creative_repo.record_audit_event(
            event_type="tool_execution_completed",
            run_id=run_id,
            session_id=session_id,
            reason_code="tool_error" if result.is_error else "tool_completed",
            payload={"tool_name": tool_request.tool_name},
        )
        self.adapter.send_tool_result(
            request_id=run_id,
            tool_call_id=tool_call_id,
            output=result.output,
            is_error=result.is_error,
        )

    def _active_step(self, run_id: str):
        steps = self.run_repo.steps(run_id)
        running = next((step for step in steps if step.status == "running"), None)
        if running is not None:
            return running
        claimed = self.run_repo.claim_next_step(
            run_id,
            worker_id="pi-runtime",
            lease_seconds=3600,
        )
        if claimed is None:
            raise RuntimeError("Pi runtime has no executable step")
        return claimed

    def _finish_verified_run(self, run_id: str) -> None:
        current = self.run_repo.get(run_id)
        if current.status in {RunStatus.paused, RunStatus.cancelled}:
            return
        steps = self.run_repo.steps(run_id)
        step = next((item for item in steps if item.status == "running"), None)
        completed_calls = [
            call
            for call in self.run_repo.tool_calls(run_id)
            if call.status == "completed" and call.evidence
        ]
        if step is None or not completed_calls:
            if step is None:
                step = self._active_step(run_id)
            self.run_repo.fail_step(
                step.id,
                error_code="VERIFICATION_EVIDENCE_MISSING",
                evidence={"tool_calls": len(completed_calls)},
                worker_id="pi-runtime",
            )
            self.run_repo.set_status(
                run_id,
                RunStatus.paused,
                error_code="VERIFICATION_EVIDENCE_MISSING",
            )
            self.run_repo.append_event(
                run_id,
                "replan_required",
                {"error_code": "VERIFICATION_EVIDENCE_MISSING"},
            )
            return
        evidence = completed_calls[-1].evidence
        criteria = evidence.get("criteria", {})
        if not all(criteria.get(item) is True for item in step.completion_criteria):
            self.run_repo.fail_step(
                step.id,
                error_code="VERIFICATION_CRITERIA_FAILED",
                evidence=evidence,
                worker_id="pi-runtime",
            )
            self.run_repo.set_status(
                run_id,
                RunStatus.paused,
                error_code="VERIFICATION_CRITERIA_FAILED",
            )
            return
        self.run_repo.complete_step(
            step.id,
            evidence=evidence,
            worker_id="pi-runtime",
        )
        self.run_repo.set_status(run_id, RunStatus.completed)
        self.run_repo.append_event(run_id, "run_completed", {"backend": "pi"})


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
