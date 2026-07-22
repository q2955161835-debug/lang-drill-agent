from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import AgentRunStep
from .tools import ToolExecutionResult


class VerificationDecision(BaseModel):
    action: Literal["complete", "retry", "replan", "cancel"]
    reason: str
    evidence: dict = Field(default_factory=dict)


class AgentRunVerifier:
    def verify(
        self,
        step: AgentRunStep,
        result: ToolExecutionResult,
    ) -> VerificationDecision:
        if not result.success:
            return self._failure(step, result, result.error_code or "TOOL_EXECUTION_FAILED")
        criteria = result.evidence.get("criteria")
        if not isinstance(criteria, dict):
            return self._failure(step, result, "VERIFICATION_EVIDENCE_MISSING")
        missing = [
            criterion
            for criterion in step.completion_criteria
            if criteria.get(criterion) is not True
        ]
        if missing:
            return self._failure(
                step,
                result,
                "VERIFICATION_CRITERIA_FAILED",
                missing=missing,
            )
        return VerificationDecision(
            action="complete",
            reason="deterministic completion criteria passed",
            evidence=result.evidence,
        )

    @staticmethod
    def _failure(
        step: AgentRunStep,
        result: ToolExecutionResult,
        reason: str,
        *,
        missing: list[str] | None = None,
    ) -> VerificationDecision:
        action: Literal["retry", "replan"] = (
            "retry" if step.attempts < step.max_attempts else "replan"
        )
        evidence = {**result.evidence}
        if missing:
            evidence["missing_criteria"] = missing
        return VerificationDecision(
            action=action,
            reason=reason,
            evidence=evidence,
        )
