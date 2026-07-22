from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from .models import MemoryCandidate, MemoryItem
from .secrets import scan_memory_secrets

MemoryOperation = Literal["ADD", "UPDATE", "SUPERSEDE", "DELETE", "NOOP", "STAGE"]


class MemoryPolicyConfig(BaseModel):
    learning_evidence_min: int = Field(default=3, ge=2, le=20)
    confidence_min: float = Field(default=0.70, ge=0, le=1)
    write_mode: Literal["explicit", "approval", "balanced", "proactive"] = "balanced"


class MemoryPolicyEvidence(BaseModel):
    id: str
    kind: str
    session_id: str = ""
    knowledge_key: str = ""
    payload: dict[str, object] = Field(default_factory=dict)


class MemoryDecision(BaseModel):
    operation: MemoryOperation
    reason: str
    candidate: MemoryCandidate | None = None
    target_memory_id: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    sanitized_content: str = ""


class MemoryPolicy:
    def __init__(self, config: MemoryPolicyConfig | None = None) -> None:
        self.config = config or MemoryPolicyConfig()

    def evaluate(
        self,
        candidate: MemoryCandidate,
        existing: list[MemoryItem],
        evidence: list[MemoryPolicyEvidence],
    ) -> MemoryDecision:
        secret_scan = scan_memory_secrets(candidate.content)
        if secret_scan.detected:
            return MemoryDecision(
                operation="NOOP",
                reason="secret_detected",
                sanitized_content=secret_scan.sanitized,
            )
        clean_candidate = candidate.model_copy(
            update={"content": _normalize_text(candidate.content)}
        )
        if clean_candidate.confidence < self.config.confidence_min:
            return self._decision("STAGE", "confidence_below_threshold", clean_candidate)
        if not _has_future_utility(clean_candidate):
            return self._decision("NOOP", "low_future_utility", clean_candidate)

        same_key = [
            item
            for item in existing
            if item.status == "active"
            and item.normalized_key
            and item.normalized_key == clean_candidate.normalized_key
        ]
        for item in same_key:
            if _normalized_compare(item.content) == _normalized_compare(clean_candidate.content):
                return self._decision(
                    "NOOP",
                    "duplicate_memory",
                    clean_candidate,
                    target_memory_id=item.id,
                )
        if same_key:
            return self._decision(
                "SUPERSEDE",
                "material_conflict",
                clean_candidate,
                target_memory_id=same_key[0].id,
                evidence=evidence,
            )

        if clean_candidate.category == "learning_weakness":
            independent = {
                item.session_id
                for item in evidence
                if item.kind == "wrong_attempt"
                and item.session_id
                and (
                    not item.knowledge_key
                    or item.knowledge_key in clean_candidate.normalized_key
                )
            }
            if len(independent) < self.config.learning_evidence_min:
                return self._decision(
                    "STAGE",
                    "insufficient_learning_evidence",
                    clean_candidate,
                    evidence=evidence,
                )

        explicit = bool(clean_candidate.metadata.get("explicit"))
        if self.config.write_mode == "explicit" and not explicit:
            return self._decision("NOOP", "explicit_write_required", clean_candidate)
        if self.config.write_mode == "approval":
            return self._decision(
                "STAGE",
                "approval_required",
                clean_candidate,
                evidence=evidence,
            )
        return self._decision("ADD", "policy_passed", clean_candidate, evidence=evidence)

    @staticmethod
    def _decision(
        operation: MemoryOperation,
        reason: str,
        candidate: MemoryCandidate,
        *,
        target_memory_id: str = "",
        evidence: list[MemoryPolicyEvidence] | None = None,
    ) -> MemoryDecision:
        evidence_ids = [item.id for item in evidence or []]
        return MemoryDecision(
            operation=operation,
            reason=reason,
            candidate=candidate.model_copy(update={"evidence_ids": evidence_ids}),
            target_memory_id=target_memory_id,
            evidence_ids=evidence_ids,
            sanitized_content=candidate.content,
        )


_LOW_UTILITY = {
    "thanks",
    "thank you",
    "ok",
    "okay",
    "hello",
    "hi",
    "你好",
    "谢谢",
    "好的",
}


def _has_future_utility(candidate: MemoryCandidate) -> bool:
    if bool(candidate.metadata.get("explicit")):
        return True
    if candidate.category in {
        "profile",
        "preference",
        "learning_weakness",
        "procedural",
        "temporal",
        "core",
    } and _normalized_compare(candidate.content) not in _LOW_UTILITY:
        return len(candidate.content.strip()) >= 8
    return len(candidate.content.strip()) >= 24


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalized_compare(text: str) -> str:
    return _normalize_text(text).casefold().strip(" .!?。！？")
