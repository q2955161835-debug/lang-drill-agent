from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .models import RunStatus
from .repository import AgentRunRepository
from .tools import (
    ToolExecutionContext,
    ToolExecutionResult,
    ToolRegistry,
)
from .verifier import AgentRunVerifier


class ExecutionOutcome(BaseModel):
    run_id: str
    step_id: str = ""
    status: str
    action: Literal["continue", "retry", "replan", "wait", "cancel", "complete"]
    detail: str = ""


class AgentRunExecutor:
    def __init__(
        self,
        repository: AgentRunRepository,
        tools: ToolRegistry,
        *,
        worker_id: str,
        verifier: AgentRunVerifier | None = None,
    ) -> None:
        self.repository = repository
        self.tools = tools
        self.worker_id = worker_id
        self.verifier = verifier or AgentRunVerifier()

    def tick(self, run_id: str) -> ExecutionOutcome:
        run = self.repository.get(run_id)
        if run.status is RunStatus.cancelled:
            return ExecutionOutcome(
                run_id=run_id,
                status="cancelled",
                action="cancel",
            )
        if run.status is RunStatus.paused:
            return ExecutionOutcome(run_id=run_id, status="paused", action="wait")
        if run.status in {RunStatus.completed, RunStatus.failed}:
            return ExecutionOutcome(
                run_id=run_id,
                status=run.status.value,
                action="complete" if run.status is RunStatus.completed else "replan",
            )

        step = self.repository.claim_next_step(run_id, self.worker_id)
        if step is None:
            steps = self.repository.steps(run_id)
            if steps and all(item.status == "completed" for item in steps):
                self.repository.set_status(run_id, RunStatus.completed)
                self.repository.append_event(run_id, "run_completed", {})
                return ExecutionOutcome(
                    run_id=run_id,
                    status="completed",
                    action="complete",
                )
            return ExecutionOutcome(run_id=run_id, status="waiting", action="wait")

        aggregate = ToolExecutionResult(
            success=True,
            output={"tool_results": []},
            evidence={"criteria": {}},
        )
        for tool_name in step.tool_names:
            if self._cancelled(run_id):
                self.repository.fail_step(
                    step.id,
                    error_code="AGENT_RUN_CANCELLED",
                    worker_id=self.worker_id,
                )
                return ExecutionOutcome(
                    run_id=run_id,
                    step_id=step.id,
                    status="cancelled",
                    action="cancel",
                )
            try:
                tool = self.tools.get(tool_name)
                input_payload = tool.input_for(step)
                validated_input = tool.validate_input(input_payload)
            except Exception as exc:
                return self._handle_failure(
                    run_id,
                    step.id,
                    "TOOL_INPUT_INVALID",
                    {"detail": str(exc)[:300]},
                )

            call = self.repository.record_tool_call(
                run_id=run_id,
                step_id=step.id,
                tool_name=tool_name,
                input_payload=validated_input.model_dump(mode="json"),
            )
            context = ToolExecutionContext(
                run_id=run_id,
                step_id=step.id,
                cancellation_requested=lambda: self._cancelled(run_id),
                trace=lambda event_type, payload: self.repository.append_event(
                    run_id,
                    event_type,
                    {"step_id": step.id, "tool_call_id": call.id, **payload},
                ),
            )
            try:
                raw_result = tool.execute(validated_input, context)
                result = ToolExecutionResult.model_validate(raw_result)
            except Exception as exc:
                result = ToolExecutionResult(
                    success=False,
                    error_code="TOOL_EXECUTION_FAILED",
                    evidence={"detail": str(exc)[:300]},
                )
            self.repository.finish_tool_call(
                call.id,
                status="completed" if result.success else "failed",
                output_payload=result.output,
                evidence=result.evidence,
                error_code=result.error_code,
            )
            aggregate.output["tool_results"].append(
                {"tool_name": tool_name, "output": result.output}
            )
            criteria = result.evidence.get("criteria")
            if isinstance(criteria, dict):
                aggregate.evidence["criteria"].update(criteria)
            aggregate.evidence.setdefault("tool_evidence", []).append(
                {"tool_name": tool_name, "evidence": result.evidence}
            )
            if not result.success:
                aggregate = aggregate.model_copy(
                    update={
                        "success": False,
                        "error_code": result.error_code or "TOOL_EXECUTION_FAILED",
                    }
                )
                break
            if self._cancelled(run_id):
                return self._handle_failure(
                    run_id,
                    step.id,
                    "AGENT_RUN_CANCELLED",
                    aggregate.evidence,
                    cancelled=True,
                )

        decision = self.verifier.verify(step, aggregate)
        if decision.action == "complete":
            self.repository.complete_step(
                step.id,
                evidence=decision.evidence,
                worker_id=self.worker_id,
            )
            if all(
                item.status == "completed"
                for item in self.repository.steps(run_id)
            ):
                self.repository.set_status(run_id, RunStatus.completed)
                self.repository.append_event(run_id, "run_completed", {})
            return ExecutionOutcome(
                run_id=run_id,
                step_id=step.id,
                status="step_completed",
                action="continue",
                detail=decision.reason,
            )
        return self._handle_failure(
            run_id,
            step.id,
            decision.reason,
            decision.evidence,
        )

    def _handle_failure(
        self,
        run_id: str,
        step_id: str,
        error_code: str,
        evidence: dict,
        *,
        cancelled: bool = False,
    ) -> ExecutionOutcome:
        failed = self.repository.fail_step(
            step_id,
            error_code=error_code,
            evidence=evidence,
            worker_id=self.worker_id,
        )
        if cancelled or self._cancelled(run_id):
            return ExecutionOutcome(
                run_id=run_id,
                step_id=step_id,
                status="cancelled",
                action="cancel",
                detail=error_code,
            )
        if failed.attempts < failed.max_attempts:
            self.repository.retry_step(step_id)
            return ExecutionOutcome(
                run_id=run_id,
                step_id=step_id,
                status="step_retry_scheduled",
                action="retry",
                detail=error_code,
            )
        self.repository.set_status(run_id, RunStatus.paused, error_code=error_code)
        self.repository.append_event(
            run_id,
            "replan_required",
            {"step_id": step_id, "error_code": error_code},
        )
        return ExecutionOutcome(
            run_id=run_id,
            step_id=step_id,
            status="replan_required",
            action="replan",
            detail=error_code,
        )

    def _cancelled(self, run_id: str) -> bool:
        return self.repository.get(run_id).status is RunStatus.cancelled
