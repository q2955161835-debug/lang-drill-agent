from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from ..utils import dumps, loads, new_id
from .context import MemoryContext, MemoryContextAssembler
from .models import MemoryCandidate, MemoryItem
from .policy import (
    MemoryDecision,
    MemoryPolicy,
    MemoryPolicyConfig,
    MemoryPolicyEvidence,
)
from .presets import (
    MemoryGroup,
    MemoryMode,
    categories_for_groups,
    intersect_categories,
    read_context_limit,
    resolve_memory_budget,
)
from .repository import MemoryRepository
from .retrieval import MemoryRetrievalQuery
from .secrets import scan_memory_secrets
from .service import MemoryService


def default_internal_categories() -> dict[str, bool]:
    """Return the eight internal memory categories all enabled by default."""
    return {
        "core": True,
        "semantic": True,
        "episodic": True,
        "procedural": True,
        "temporal": True,
        "preference": True,
        "profile": True,
        "learning_weakness": True,
    }


class MemorySettings(BaseModel):
    enabled: bool = True
    capture_enabled: bool = True
    recall_enabled: bool = True
    mode: MemoryMode = "standard"
    group_enabled: dict[MemoryGroup, bool] = Field(
        default_factory=lambda: {
            "about_me": True,
            "learning_history": True,
            "usage_habits": True,
        }
    )
    category_enabled: dict[str, bool] = Field(
        default_factory=default_internal_categories
    )
    write_mode: str = "balanced"
    learning_evidence_min: int = 3
    confidence_min: float = 0.70
    default_ttl_days: int = 365
    recall_top_k: int = 50
    embeddings_enabled: bool = True
    compaction_flush_enabled: bool = True


class MemorySettingsService:
    SETTINGS_KEY = "memory.settings"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self) -> MemorySettings:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (self.SETTINGS_KEY,),
        ).fetchone()
        payload = loads(row["value_json"], {}) if row else {}
        return MemorySettings(**payload)

    def save(self, settings: MemorySettings) -> MemorySettings:
        normalized = MemorySettings(**settings.model_dump())
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (self.SETTINGS_KEY, dumps(normalized.model_dump(mode="json"))),
        )
        return normalized


class MemoryHooks:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repository = MemoryRepository(conn)
        self.settings_service = MemorySettingsService(conn)
        self.memory_service = MemoryService(conn)

    def on_turn_end(
        self,
        *,
        user: str,
        assistant: str,
        scope: str = "global",
        evidence_ref: str = "",
    ) -> MemoryItem | MemoryCandidate | None:
        try:
            settings = self.settings_service.get()
            if not settings.enabled or not settings.capture_enabled:
                return None
            candidate = _explicit_candidate(user, scope=scope, evidence_ref=evidence_ref)
            if candidate is None:
                return None
            return self._evaluate_and_apply(candidate, [])
        except Exception as exc:
            self._record_failure("on_turn_end", exc)
            return None

    def on_attempt(
        self,
        *,
        session_id: str,
        is_correct: bool,
        knowledge_tags: list[str],
        question_id: str,
        scope: str = "global",
    ) -> list[MemoryItem | MemoryCandidate]:
        results: list[MemoryItem | MemoryCandidate] = []
        try:
            settings = self.settings_service.get()
            if (
                not settings.enabled
                or not settings.capture_enabled
                or is_correct
                or not settings.category_enabled.get("learning_weakness", True)
            ):
                return []
            for tag in {str(item).strip() for item in knowledge_tags if str(item).strip()}:
                normalized_key = f"weakness:{tag}"
                evidence = self._attempt_evidence(normalized_key)
                current_ref = f"attempt:{session_id}:{question_id}:{tag}"
                if current_ref not in {item.id for item in evidence}:
                    evidence.append(
                        MemoryPolicyEvidence(
                            id=current_ref,
                            kind="wrong_attempt",
                            session_id=session_id,
                            knowledge_key=tag,
                        )
                    )
                candidate = MemoryCandidate(
                    category="learning_weakness",
                    scope=scope,
                    content=f"User repeatedly struggles with {tag}",
                    normalized_key=normalized_key,
                    confidence=min(1.0, 0.55 + 0.15 * len({item.session_id for item in evidence})),
                    importance=0.8,
                    evidence_ids=[item.id for item in evidence],
                    metadata={"knowledge_tag": tag, "source": "attempts"},
                )
                result = self._evaluate_and_apply(candidate, evidence)
                if result is not None:
                    results.append(result)
            return results
        except Exception as exc:
            self._record_failure("on_attempt", exc)
            return results

    def on_agent_run_complete(
        self,
        *,
        run_id: str,
        goal: str,
        outcome: str,
        scope: str = "global",
    ) -> MemoryItem | MemoryCandidate | None:
        try:
            settings = self.settings_service.get()
            if not settings.enabled or not settings.capture_enabled:
                return None
            candidate = MemoryCandidate(
                category="episodic",
                scope=scope,
                content=f"Completed task: {goal}. Outcome: {outcome}",
                normalized_key=f"agent_run:{run_id}",
                confidence=0.9,
                importance=0.5,
                evidence_ids=[f"agent_run:{run_id}"],
                metadata={"run_id": run_id},
            )
            return self._evaluate_and_apply(candidate, [])
        except Exception as exc:
            self._record_failure("on_agent_run_complete", exc)
            return None

    def before_context_compaction(
        self,
        *,
        messages: list[dict[str, Any]],
        scope: str = "global",
    ) -> list[MemoryItem | MemoryCandidate]:
        results: list[MemoryItem | MemoryCandidate] = []
        try:
            settings = self.settings_service.get()
            if (
                not settings.enabled
                or not settings.capture_enabled
                or not settings.compaction_flush_enabled
            ):
                return []
            for index, message in enumerate(messages):
                if str(message.get("role") or "") != "user":
                    continue
                result = self.on_turn_end(
                    user=str(message.get("content") or ""),
                    assistant="",
                    scope=scope,
                    evidence_ref=f"compaction_message:{index}",
                )
                if result is not None:
                    results.append(result)
            return results
        except Exception as exc:
            self._record_failure("before_context_compaction", exc)
            return results

    def recall(
        self,
        text: str,
        *,
        scope: str,
        categories: list[str] | None = None,
        available_context_tokens: int | None = None,
    ) -> MemoryContext:
        try:
            settings = self.settings_service.get()
            if not settings.enabled or not settings.recall_enabled:
                return MemoryContext(items=[], token_count=0)
            available = (
                available_context_tokens
                if available_context_tokens is not None
                else read_context_limit(self.conn)
            )
            budget = resolve_memory_budget(settings.mode, available)
            enabled_categories = intersect_categories(
                categories,
                categories_for_groups(settings.group_enabled),
                settings.category_enabled,
            )
            if not enabled_categories:
                return MemoryContext(items=[], token_count=0, budget=budget)
            query = MemoryRetrievalQuery(
                text=text.strip(),
                categories=enabled_categories,
                scope=scope,
                top_k=settings.recall_top_k,
                token_budget=max(1, budget.effective_tokens),
            )
            if self.memory_service.current_primary_id == "builtin":
                return MemoryContextAssembler(self.conn).build(
                    query,
                    budget=budget,
                    embeddings_enabled=settings.embeddings_enabled,
                )
            result = self.memory_service.retrieve(query)
            return MemoryContext(
                mode=result.mode,
                items=result.items,
                token_count=result.token_count,
                budget=budget,
            )
        except Exception as exc:
            self._record_failure("recall", exc)
            return MemoryContext(items=[], token_count=0)

    def _evaluate_and_apply(
        self,
        candidate: MemoryCandidate,
        evidence: list[MemoryPolicyEvidence],
    ) -> MemoryItem | MemoryCandidate | None:
        settings = self.settings_service.get()
        if not settings.category_enabled.get(candidate.category, True):
            return None
        if (
            not candidate.expires_at
            and not candidate.pinned
            and candidate.category not in {"core", "profile", "preference"}
        ):
            candidate = candidate.model_copy(
                update={
                    "expires_at": (
                        datetime.now() + timedelta(days=settings.default_ttl_days)
                    ).isoformat(timespec="seconds")
                }
            )
        existing = self.memory_service.active_items(scope=candidate.scope)
        policy = MemoryPolicy(
            MemoryPolicyConfig(
                learning_evidence_min=settings.learning_evidence_min,
                confidence_min=settings.confidence_min,
                write_mode=settings.write_mode,
            )
        )
        decision = policy.evaluate(candidate, existing, evidence)
        return self._apply_decision(decision)

    def _apply_decision(
        self,
        decision: MemoryDecision,
    ) -> MemoryItem | MemoryCandidate | None:
        candidate = decision.candidate
        if decision.operation == "NOOP" or candidate is None:
            self.repository._event(
                "memory_candidate_noop",
                payload={"reason": decision.reason},
            )
            return None
        if decision.operation == "STAGE":
            return self.repository.stage(candidate.model_copy(update={"reason": decision.reason}))
        if decision.operation == "ADD":
            staged = self.repository.stage(candidate)
            item = self.memory_service.commit_staged_candidate(staged)
            if self.memory_service.current_primary_id != "builtin":
                self.repository.mark_candidate_committed_external(
                    staged.id,
                    provider_id=self.memory_service.current_primary_id,
                    external_memory_id=item.id,
                )
            self._discard_prior_staged(candidate.normalized_key, keep_candidate_id=staged.id)
            return item
        if decision.operation == "SUPERSEDE":
            if self.memory_service.current_primary_id == "builtin":
                return self.repository.supersede(decision.target_memory_id, candidate)
            staged = self.repository.stage(candidate)
            item = self.memory_service.update(decision.target_memory_id, candidate.content)
            self.repository.mark_candidate_committed_external(
                staged.id,
                provider_id=self.memory_service.current_primary_id,
                external_memory_id=item.id,
            )
            return item
        if decision.operation == "UPDATE":
            return self.memory_service.update(decision.target_memory_id, candidate.content)
        if decision.operation == "DELETE":
            return self.memory_service.delete(decision.target_memory_id)
        return None

    def _attempt_evidence(self, normalized_key: str) -> list[MemoryPolicyEvidence]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT e.evidence_ref
            FROM memory_evidence e
            JOIN memory_candidates c ON c.id=e.candidate_id
            WHERE c.normalized_key=? AND c.status IN ('staged', 'committed')
            ORDER BY e.evidence_ref
            """,
            (normalized_key,),
        ).fetchall()
        evidence = []
        for row in rows:
            reference = str(row["evidence_ref"])
            parts = reference.split(":", 3)
            if len(parts) < 4 or parts[0] != "attempt":
                continue
            evidence.append(
                MemoryPolicyEvidence(
                    id=reference,
                    kind="wrong_attempt",
                    session_id=parts[1],
                    knowledge_key=parts[3],
                )
            )
        return evidence

    def _discard_prior_staged(self, normalized_key: str, *, keep_candidate_id: str) -> None:
        self.conn.execute(
            """
            UPDATE memory_candidates
            SET status='discarded', updated_at=CURRENT_TIMESTAMP
            WHERE normalized_key=? AND status='staged' AND id<>?
            """,
            (normalized_key, keep_candidate_id),
        )

    def _record_failure(self, hook: str, exc: Exception) -> None:
        try:
            detail = scan_memory_secrets(str(exc)).sanitized[:300]
            self.conn.execute(
                """
                INSERT INTO memory_events (id, event_type, payload_json)
                VALUES (?, 'memory_hook_failed', ?)
                """,
                (new_id("memevent"), dumps({"hook": hook, "detail": detail})),
            )
        except Exception:
            return


def _explicit_candidate(
    text: str,
    *,
    scope: str,
    evidence_ref: str,
) -> MemoryCandidate | None:
    clean = re.sub(r"\s+", " ", text).strip()
    match = re.search(
        r"(?i)(?:remember(?:\s+that)?|please remember|记住|请记住)[:：]?\s*(.+)$",
        clean,
    )
    if not match:
        return None
    content = match.group(1).strip(" .。")
    if not content:
        return None
    lower = content.casefold()
    if any(token in lower for token in ("prefer", "preference", "喜欢", "偏好")):
        category = "preference"
        key_prefix = "preference"
    elif any(token in lower for token in ("deadline", "exam date", "考试时间", "截止")):
        category = "temporal"
        key_prefix = "temporal"
    else:
        category = "profile"
        key_prefix = "profile"
    normalized_tail = re.sub(r"[^a-z0-9\u3400-\u9fff]+", "-", lower).strip("-")[:80]
    return MemoryCandidate(
        category=category,
        scope=scope,
        content=content,
        normalized_key=f"{key_prefix}:{normalized_tail}",
        confidence=0.95,
        importance=0.8,
        evidence_ids=[evidence_ref] if evidence_ref else [],
        metadata={"explicit": True, "source": "user_turn"},
    )
