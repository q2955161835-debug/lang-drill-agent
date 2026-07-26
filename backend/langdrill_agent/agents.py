from __future__ import annotations

import sqlite3
import logging
import re
from typing import Any

from .algorithm import MasteryInputs, mastery_score, next_review_at
from .context import ContextService
from .knowledge.context import build_knowledge_context
from .memory.hooks import MemoryHooks
from .models import AuthoredQuestionSet, EvaluationResult, Question, TaskType
from .past_papers.retrieval import PastPaperQuery, PastPaperRetrievalService
from .past_papers.scheduler import (
    AdaptivePracticeScheduler,
    LearningTargetCandidate,
    SchedulingConfig,
)
from .prompt_engine import PromptAssembler, PromptRegistry
from .providers import ModelProvider
from .services import PastPaperService, ProfileService, QuestionService, SessionService
from .utils import dumps, loads, new_id
from .validator import QuestionValidator


logger = logging.getLogger(__name__)

_CJK_TEXT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff]")
_ENGLISH_TERM_RE = re.compile(r"^[A-Za-z][A-Za-z' -]{1,80}$")
_ENGLISH_EXAM_IDS = {"cet4", "cet6", "ielts", "toefl", "gaokao-english"}
_DRILL_PROGRESS_LINE_RE = re.compile(
    r"^\s*(?:(?:下一题已就绪|当前进度|已准备好|已进入下一题)\s*[:：]?\s*)?"
    r"第\s*\d+\s*题\s*/\s*共\s*\d+\s*题[。.!！]?\s*$"
    r"|^\s*(?:下一题已就绪|当前进度|已准备好|已进入下一题)[。.!！]?\s*$"
)


def _looks_like_english_term(value: object) -> bool:
    return bool(_ENGLISH_TERM_RE.fullmatch(str(value or "").strip()))


class OrchestratorAgent:
    name = "orchestrator"

    def __init__(self, conn: sqlite3.Connection, provider: ModelProvider):
        self.conn = conn
        self.provider = provider
        self.profile_service = ProfileService(conn)
        self.session_service = SessionService(conn)
        self.question_service = QuestionService(conn)
        self.assembler = PromptAssembler(PromptRegistry(conn))

    def handle_daily_drill(self, session_id: str, content: str) -> dict:
        profile = self.profile_service.get()
        imported_terms = self._import_inline_content(profile.exam_id, content)
        new_content = [content.strip()] if content.strip() else []
        for item in imported_terms:
            summary = f"{item['term']}: {item['meaning']}" if item.get("meaning") else item["term"]
            if summary not in new_content:
                new_content.append(summary)
        plan = {
            "new_content": new_content,
            "review_content": self._select_review_stub(profile.exam_id),
            "target_minutes": profile.daily_minutes,
            "status": "formal_question_set_ready",
            "algorithm": "formal_question_set_v1_mastery_score",
        }
        self.conn.execute(
            """
            UPDATE study_sessions
            SET daily_plan_json=?, status='active', title=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (dumps(plan), (content.strip() or "日常学习")[:18], session_id),
        )

        usage = ContextService(self.conn).usage(session_id)
        available = max(
            0,
            int(usage["context_limit"]) - int(usage["estimated_current_context"]),
        )
        memory_context = MemoryHooks(self.conn).recall(
            content or "daily learning plan",
            scope=f"exam:{profile.exam_id}",
            available_context_tokens=available,
        )
        pack = self.assembler.assemble(
            task_type="daily_drill",
            exam_id=profile.exam_id,
            persona=profile.persona if profile.persona != "custom" else "professional",
            context_pack={
                "task_type": TaskType.daily_drill.value,
                "profile": profile.model_dump(exclude={"global_user_prompt"}),
                "daily_plan": plan,
                "memory": memory_context.model_dump(mode="json"),
            },
            user_content=content,
            allow_global_user_prompt=False,
        )
        result = self.provider.complete(pack)
        self._record_model_call("daily_drill", result, [m["id"] for m in pack.system_modules])
        return plan

    def _import_inline_content(self, exam_id: str, content: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or len(line) > 120:
                continue
            term = ""
            reading = ""
            meaning = ""
            notes = ""
            if "|" in line:
                parts = [part.strip() for part in line.split("|")]
                term = parts[0] if parts else ""
                reading = parts[1] if len(parts) > 1 else ""
                meaning = parts[2] if len(parts) > 2 else ""
                notes = parts[4] if len(parts) > 4 else ""
            elif ":" in line or "：" in line:
                pieces = re.split(r"[:：]", line, maxsplit=1)
                term = pieces[0].strip()
                meaning = pieces[1].strip() if len(pieces) > 1 else ""
            if exam_id in _ENGLISH_EXAM_IDS and not _looks_like_english_term(term):
                continue
            if not term or not meaning:
                continue
            existing = self.conn.execute(
                """
                SELECT id FROM knowledge_items
                WHERE term=? AND exam_id=? AND source_scope='chat_input'
                LIMIT 1
                """,
                (term, exam_id),
            ).fetchone()
            if existing:
                self.conn.execute(
                    """
                    UPDATE knowledge_items
                    SET reading=?, meaning=?, notes=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (reading, meaning, notes, existing["id"]),
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO knowledge_items
                    (id, kind, term, reading, meaning, notes, exam_id, source_scope, mastery_score)
                    VALUES (?, 'word', ?, ?, ?, ?, ?, 'chat_input', 0.2)
                    """,
                    (new_id("kn"), term, reading, meaning, notes, exam_id),
                )
            entries.append({"term": term, "meaning": meaning})
        return entries

    def _select_review_stub(self, exam_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT term FROM knowledge_items
            WHERE exam_id IN (?, 'unassigned') AND mastery_score < 0.75
            ORDER BY COALESCE(due_at, created_at) ASC
            LIMIT 5
            """,
            (exam_id,),
        ).fetchall()
        return [row["term"] for row in rows] or ["昨日错题", "低掌握度知识点", "考纲兜底知识点"]

    def _record_model_call(self, task_type: str, result, prompt_modules: list[str]) -> None:
        self.conn.execute(
            """
            INSERT INTO model_calls
            (id, agent_name, task_type, provider_id, model, prompt_modules_json,
             input_tokens, output_tokens, latency_ms, validation_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("call"),
                self.name,
                task_type,
                self.provider.provider_id,
                result.model,
                dumps(prompt_modules),
                result.input_tokens,
                result.output_tokens,
                result.latency_ms,
                "not_required",
            ),
        )


class QuestionAuthorAgent:
    name = "question_author"

    def __init__(self, conn: sqlite3.Connection, provider: ModelProvider):
        self.conn = conn
        self.provider = provider
        self.profile_service = ProfileService(conn)
        self.validator = QuestionValidator()
        self.assembler = PromptAssembler(PromptRegistry(conn))

    def ensure_question_set(
        self,
        session_id: str,
        requested_content: str,
        *,
        target_count: int = 8,
        exact_count: bool = False,
    ) -> dict[str, object]:
        question_service = QuestionService(self.conn)
        progress = question_service.question_progress(session_id)
        if progress["ready"]:
            return {"created": 0, "opening_message": "", "progress": progress}

        profile = self.profile_service.get()
        plan_row = self.conn.execute(
            "SELECT daily_plan_json FROM study_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        plan = loads(plan_row["daily_plan_json"], {}) if plan_row else {}
        start_sequence = question_service.next_sequence(session_id)
        content_pool = self._content_pool(profile.exam_id, requested_content, target_count * 3)
        count = max(1, min(24, target_count)) if exact_count else self._target_count(
            profile.daily_minutes,
            len(content_pool),
            target_count,
        )
        past_paper_context = PastPaperService(self.conn).generation_context(profile.exam_id)
        knowledge_query = requested_content.strip() or " ".join(
            str(item.get("term") or "") for item in content_pool[:12]
        )
        knowledge_context = build_knowledge_context(
            self.conn,
            query=knowledge_query,
            task_type="question_authoring",
            token_budget=1800,
            trace_id=session_id,
        )
        enabled_paper_types = [
            str(item.get("id") or "")
            for item in past_paper_context.get("enabled_question_types", [])
            if str(item.get("id") or "") and str(item.get("id") or "") != "listening"
        ]
        paper_evidence = PastPaperRetrievalService(self.conn).search(
            PastPaperQuery(
                exam_id=profile.exam_id,
                text=knowledge_query or profile.exam_name,
                question_types=enabled_paper_types,
                top_k=8,
            )
        )
        exam_style_evidence = [item.model_dump() for item in paper_evidence.items]
        distilled_exam_patterns = self._distilled_exam_patterns(profile.exam_id)
        usage = ContextService(self.conn).usage(session_id)
        available = max(
            0,
            int(usage["context_limit"]) - int(usage["estimated_current_context"]),
        )
        memory_context = MemoryHooks(self.conn).recall(
            knowledge_query or requested_content or profile.exam_name,
            scope=f"exam:{profile.exam_id}",
            categories=["learning_weakness", "profile", "preference", "temporal"],
            available_context_tokens=available,
        )
        schedule_decision = self._schedule_targets(
            session_id=session_id,
            exam_id=profile.exam_id,
            content_pool=content_pool,
            enabled_question_types=enabled_paper_types,
            distilled_exam_patterns=distilled_exam_patterns,
            count=count,
        )
        scheduled_targets = [item.model_dump() for item in schedule_decision.items]
        scheduled_content_pool = [
            {
                **item.payload,
                "term": str(item.payload.get("term") or item.label),
                "meaning": str(item.payload.get("meaning") or item.label),
                "scheduled_target_id": item.target_id,
                "scheduled_question_type": item.question_type,
                "scheduled_source": item.source,
                "scheduled_reason": item.reason,
            }
            for item in schedule_decision.items
        ]
        pack = self.assembler.assemble(
            task_type="question_authoring",
            exam_id=profile.exam_id,
            persona="none",
            context_pack={
                "session_id": session_id,
                "daily_plan": plan,
                "exam_id": profile.exam_id,
                "exam_name": profile.exam_name,
                "start_sequence": start_sequence,
                "target_count": count,
                "content_pool": content_pool,
                "primary_learning_targets": scheduled_targets,
                "schedule_decision": schedule_decision.model_dump(),
                "past_paper_context": past_paper_context,
                "exam_style_evidence": exam_style_evidence,
                "distilled_exam_patterns": distilled_exam_patterns,
                "knowledge_retrieval": knowledge_context,
                "memory": memory_context.model_dump(mode="json"),
                "question_flow": "先生成完整题组并持久化，再逐题取出展示。",
                "quality_rules": [
                    "优先覆盖用户输入、截图导入、到期复习和低掌握度知识点。",
                    "题型必须贴近真实考试：题干使用英文完整句、短段落、完形空格或阅读语境问题。",
                    "必须真实参考 past_paper_context.selected_papers 中当前选中的历年真题试卷索引、来源和风格摘要。",
                    "只能生成 past_paper_context.enabled_question_types 中已勾选的题型；如果用户关闭某类题型，本轮题组不要生成该题型。",
                    "选择题选项优先使用英文单词、短语、句子或同义改写，禁止只出“选择中文释义 / 最合适理解”的词卡题。",
                    "英语考试题目的选择题选项必须全部是英文内容，不得混入中文释义、日文、调试词、来源说明或用户输入里的中文元信息。",
                    "每题必须考语境理解、搭配、语法或阅读推断，不能只靠中英文同形或裸释义猜答案。",
                    "每题必须有准确答案、讲解和 knowledge_tags。",
                    "每题 source_refs 至少包含一个被参考的真题试卷 id、year、title、source_url 和 boundary。",
                    "选择题选项顺序要分散，不要全是 A。",
                ],
                "output_contract": "AuthoredQuestionSet JSON Schema",
            },
            user_content=(
                f"请一次生成 {count} 道正式刷题题目，题目先入库后再展示。"
                "如果内容池来自截图词表，请自动把这些词改写成考试式语境选择题，"
                "不要要求用户再次确认或再次发送“请出题”。"
                "出题时以当前已选择的历年真题试卷和已勾选题型为硬约束。"
                f"用户本轮输入：{requested_content or '继续今日学习'}"
            ),
            output_schema=AuthoredQuestionSet.model_json_schema(),
            allow_global_user_prompt=False,
        )
        try:
            result = self.provider.complete(pack)
        except Exception:
            logger.warning("model request failed during question authoring, using fallback", exc_info=True)
            questions = self._fallback_question_set(
                session_id=session_id,
                exam_name=profile.exam_name,
                exam_id=profile.exam_id,
                start_sequence=start_sequence,
                target_count=count,
                content_pool=scheduled_content_pool or content_pool,
                exact_count=exact_count,
            )
            self._attach_knowledge_source_refs(questions, knowledge_context)
            self._attach_past_paper_source_refs(questions, exam_style_evidence)
            question_service.save_questions(questions)
            return {
                "created": len(questions),
                "opening_message": "模型暂时不可用，已使用本地规则生成一组考试式练习题。",
                "progress": question_service.question_progress(session_id),
            }
        authored = self._try_parse_question_set(result.content, session_id, start_sequence, count)
        questions = authored["questions"]
        self._attach_knowledge_source_refs(questions, knowledge_context)
        self._attach_past_paper_source_refs(questions, exam_style_evidence)
        validation_status = "passed"
        try:
            self._validate_questions(
                questions,
                allowed_past_paper_question_ids={item["id"] for item in exam_style_evidence},
            )
        except Exception:
            questions = self._fallback_question_set(
                session_id=session_id,
                exam_name=profile.exam_name,
                exam_id=profile.exam_id,
                start_sequence=start_sequence,
                target_count=count,
                content_pool=scheduled_content_pool or content_pool,
                exact_count=exact_count,
            )
            validation_status = "fallback_after_validation_failure"
        if len(questions) < max(2, min(count, 4)):
            questions = self._fallback_question_set(
                session_id=session_id,
                exam_name=profile.exam_name,
                exam_id=profile.exam_id,
                start_sequence=start_sequence,
                target_count=count,
                content_pool=scheduled_content_pool or content_pool,
                exact_count=exact_count,
            )
            validation_status = "fallback_after_short_set"
        self._attach_knowledge_source_refs(questions, knowledge_context)
        self._attach_past_paper_source_refs(questions, exam_style_evidence)
        question_service.save_questions(questions)
        self._record_model_call(result, [m["id"] for m in pack.system_modules], validation_status)
        return {
            "created": len(questions),
            "opening_message": authored["opening_message"],
            "progress": question_service.question_progress(session_id),
        }

    def _schedule_targets(
        self,
        *,
        session_id: str,
        exam_id: str,
        content_pool: list[dict[str, object]],
        enabled_question_types: list[str],
        distilled_exam_patterns: list[dict[str, Any]],
        count: int,
    ):
        enabled_types = [
            question_type
            for question_type in enabled_question_types
            if question_type and question_type != "listening"
        ] or ["reading", "translation", "writing", "vocabulary"]
        candidates: list[LearningTargetCandidate] = []
        for index, item in enumerate(content_pool):
            source_scope = str(item.get("source_scope") or "")
            source = (
                "current_import"
                if source_scope in {"screenshot_import", "chat_input"}
                else "personal_review"
            )
            term = str(item.get("term") or item.get("id") or f"target-{index}")
            mastery = float(item.get("mastery_score") or 0)
            candidates.append(
                LearningTargetCandidate(
                    target_id=str(item.get("id") or f"content-{index}-{term}"),
                    source=source,
                    question_type=enabled_types[index % len(enabled_types)],
                    label=term,
                    mastery_gap=max(0, min(1, 1 - mastery)),
                    due=bool(item.get("due_at")),
                    uncertainty=0.5,
                    payload=item,
                )
            )
        for finding in distilled_exam_patterns:
            question_type = str(finding.get("label") or "")
            if question_type not in enabled_types:
                continue
            candidates.append(
                LearningTargetCandidate(
                    target_id=f"distillation:{finding.get('id')}",
                    source="distillation",
                    question_type=question_type,
                    label=question_type,
                    exam_frequency=float(
                        (finding.get("finding") or {}).get("share_of_verified") or 0
                    ),
                    uncertainty=max(0, 1 - float(finding.get("confidence") or 0)),
                    payload={
                        "term": question_type,
                        "meaning": "已验证真题证据支持的考试模式",
                        "distillation_id": finding.get("id"),
                    },
                )
            )
        for question_type in enabled_types:
            candidates.append(
                LearningTargetCandidate(
                    target_id=f"long-tail:{question_type}",
                    source="long_tail",
                    question_type=question_type,
                    label=question_type,
                    uncertainty=0.7,
                    payload={
                        "term": question_type,
                        "meaning": "已启用题型的滚动覆盖目标",
                    },
                )
            )
        settings_row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (f"past_papers.library_settings.{exam_id}",),
        ).fetchone()
        scheduler_settings = loads(settings_row["value_json"], {}) if settings_row else {}
        return AdaptivePracticeScheduler(self.conn).schedule(
            candidates=candidates,
            exam_id=exam_id,
            count=count,
            config=SchedulingConfig(
                long_tail_min_ratio=float(
                    scheduler_settings.get("long_tail_min_ratio", 0.10)
                ),
                max_question_type_ratio=float(
                    scheduler_settings.get("max_question_type_ratio", 0.35)
                ),
                rolling_question_window=int(
                    scheduler_settings.get("coverage_window", 20)
                ),
                enabled_question_types=frozenset(enabled_types),
            ),
            session_id=session_id,
        )

    def _distilled_exam_patterns(self, exam_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, finding_type, label, finding_json, evidence_count,
                   paper_count, years_json, confidence
            FROM past_paper_distillations
            WHERE exam_id=? AND status='ready'
              AND version=(
                SELECT MAX(version) FROM past_paper_distillations
                WHERE exam_id=? AND status='ready'
              )
            ORDER BY confidence DESC, evidence_count DESC, id
            LIMIT 20
            """,
            (exam_id, exam_id),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "finding_type": row["finding_type"],
                "label": row["label"],
                "finding": loads(row["finding_json"], {}),
                "evidence_count": row["evidence_count"],
                "paper_count": row["paper_count"],
                "years": loads(row["years_json"], []),
                "confidence": row["confidence"],
            }
            for row in rows
        ]

    @staticmethod
    def _attach_past_paper_source_refs(
        questions: list[Question],
        exam_style_evidence: list[dict[str, Any]],
    ) -> None:
        refs = [
            {
                "type": "past_paper_evidence",
                "question_id": item.get("id", ""),
                "document_id": item.get("document_id", ""),
                "title": item.get("document_title", ""),
                "year": item.get("year"),
                "source_url": item.get("source_url", ""),
                "source_page": item.get("source_page"),
                "verification_status": item.get("verification_status", "unverified"),
                "correctness_evidence": bool(item.get("correctness_evidence")),
                "boundary": item.get("boundary", "short_style_reference"),
                "claim": "generated_practice_inspired_by_evidence",
            }
            for item in exam_style_evidence[:4]
            if item.get("id")
        ]
        for question in questions:
            known = {
                str(ref.get("question_id") or "")
                for ref in question.source_refs
                if ref.get("type") == "past_paper_evidence"
            }
            question.source_refs.extend(
                ref for ref in refs if str(ref.get("question_id") or "") not in known
            )

    @staticmethod
    def _attach_knowledge_source_refs(
        questions: list[Question],
        knowledge_context: dict[str, Any],
    ) -> None:
        refs = []
        for item in knowledge_context.get("items", [])[:4]:
            citation = item.get("citation", {})
            refs.append(
                {
                    "type": "knowledge_document",
                    "document_id": citation.get("document_id", ""),
                    "title": citation.get("document_title", ""),
                    "heading": citation.get("heading", ""),
                    "page_start": citation.get("page_start"),
                    "page_end": citation.get("page_end"),
                    "content_hash": citation.get("content_hash", ""),
                    "boundary": "short_untrusted_reference",
                }
            )
        for question in questions:
            existing = {
                (ref.get("type"), ref.get("document_id"), ref.get("content_hash"))
                for ref in question.source_refs
            }
            question.source_refs.extend(
                ref
                for ref in refs
                if (ref.get("type"), ref.get("document_id"), ref.get("content_hash"))
                not in existing
            )

    def _target_count(self, daily_minutes: int, pool_size: int, default_count: int) -> int:
        minute_based = max(6, min(16, daily_minutes // 4 or default_count))
        pressure_based = max(default_count, min(18, pool_size // 2 if pool_size else default_count))
        return max(4, min(24, max(minute_based, pressure_based)))

    def _content_pool(self, exam_id: str, requested_content: str, limit: int) -> list[dict[str, object]]:
        explicit_pool = self._explicit_content_pool(requested_content)
        if explicit_pool and "截图导入词表" in requested_content:
            return explicit_pool[:limit]
        rows = self.conn.execute(
            """
            SELECT id, kind, term, reading, meaning, notes, source_scope, mastery_score, due_at
            FROM knowledge_items
            WHERE exam_id IN (?, 'unassigned')
            ORDER BY
              CASE WHEN due_at IS NOT NULL AND due_at<>'' AND due_at<=CURRENT_TIMESTAMP THEN 0 ELSE 1 END,
              mastery_score ASC,
              updated_at ASC
            LIMIT ?
            """,
            (exam_id, limit),
        ).fetchall()
        seen_terms = {str(item.get("term") or "").lower() for item in explicit_pool}
        pool = [item for item in explicit_pool if self._allow_pool_item(exam_id, item)]
        pool.extend(
            dict(row)
            for row in rows
            if str(row["term"] or "").lower() not in seen_terms and self._allow_pool_item(exam_id, dict(row))
        )
        pool = pool[:limit]
        text = requested_content.strip()
        if text and not pool:
            pool.append(
                {
                    "id": "user_content",
                    "kind": "text",
                    "term": text[:80],
                    "reading": "",
                    "meaning": text[:160],
                    "notes": "来自用户本轮输入",
                    "source_scope": "chat_input",
                    "mastery_score": 0.2,
                    "due_at": "",
                }
            )
        return pool

    @staticmethod
    def _allow_pool_item(exam_id: str, item: dict[str, object]) -> bool:
        return exam_id not in _ENGLISH_EXAM_IDS or _looks_like_english_term(item.get("term"))

    def _explicit_content_pool(self, requested_content: str) -> list[dict[str, object]]:
        pool: list[dict[str, object]] = []
        seen: set[str] = set()
        for line in requested_content.splitlines():
            if ":" not in line:
                continue
            term, meaning = line.split(":", 1)
            clean_term = term.strip().lower()
            clean_meaning = meaning.strip()
            if not re.fullmatch(r"[a-z][a-z'-]{1,40}", clean_term):
                continue
            if clean_term in seen or not clean_meaning:
                continue
            seen.add(clean_term)
            pool.append(
                {
                    "id": f"explicit:{clean_term}",
                    "kind": "word",
                    "term": clean_term,
                    "reading": "",
                    "meaning": clean_meaning,
                    "notes": "来自本轮显式词表",
                    "source_scope": "screenshot_import" if "截图导入词表" in requested_content else "chat_input",
                    "mastery_score": 0.2,
                    "due_at": "",
                }
            )
        return pool

    def _try_parse_question_set(
        self,
        content: str,
        session_id: str,
        start_sequence: int,
        target_count: int,
    ) -> dict[str, object]:
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        raw_json = json_match.group(1) if json_match else content
        parsed = loads(raw_json.strip(), {})
        if isinstance(parsed, list):
            parsed = {"questions": parsed}
        if not isinstance(parsed, dict):
            return {"opening_message": "", "questions": []}
        questions: list[Question] = []
        for offset, item in enumerate(parsed.get("questions", [])[:target_count]):
            if not isinstance(item, dict):
                continue
            question = self._question_from_authored(item, session_id, start_sequence + offset)
            if question:
                questions.append(question)
        return {
            "opening_message": str(parsed.get("opening_message", "") or ""),
            "questions": questions,
        }

    def _question_from_authored(
        self,
        item: dict[str, object],
        session_id: str,
        sequence: int,
    ) -> Question | None:
        options = [str(option).strip() for option in item.get("options", []) or [] if str(option).strip()]
        answer = item.get("answer") if isinstance(item.get("answer"), dict) else {}
        normalized_answer = self._normalize_answer(answer, options)
        if not normalized_answer:
            return None
        try:
            return Question(
                id=new_id("q"),
                session_id=session_id,
                sequence=sequence,
                type=str(item.get("type") or "multiple_choice"),
                prompt=str(item.get("prompt") or "").strip(),
                options=options,
                answer=normalized_answer,
                explanation=str(item.get("explanation") or "").strip(),
                knowledge_tags=[str(tag) for tag in item.get("knowledge_tags", []) or [] if str(tag).strip()],
                difficulty=float(item.get("difficulty") or 0.5),
                source_refs=[ref for ref in item.get("source_refs", []) or [] if isinstance(ref, dict)],
            )
        except Exception:
            return None

    def _normalize_answer(self, answer: dict[str, object], options: list[str]) -> dict[str, str] | None:
        letter = str(answer.get("letter") or "").strip().upper()
        correct = str(answer.get("correct") or "").strip()
        if letter in {"A", "B", "C", "D"} and options:
            index = ord(letter) - ord("A")
            if index < len(options):
                return {"letter": letter, "correct": options[index]}
        if correct in {"A", "B", "C", "D"} and options:
            index = ord(correct) - ord("A")
            if index < len(options):
                return {"letter": correct, "correct": options[index]}
        if correct and options and correct in options:
            return {"letter": chr(ord("A") + options.index(correct)), "correct": correct}
        if correct and not options:
            return {"correct": correct}
        return None

    def _validate_questions(
        self,
        questions: list[Question],
        *,
        allowed_past_paper_question_ids: set[str] | None = None,
    ) -> None:
        if not questions:
            raise ValueError("题组为空")
        profile = self.profile_service.get()
        letters: list[str] = []
        for question in questions:
            self.validator.validate(question)
            self.validator.validate_source_refs(
                question,
                allowed_past_paper_question_ids or set(),
            )
            self._validate_exam_style(question, profile.exam_id, profile.target_language)
            letter = str(question.answer.get("letter", "")).upper()
            if letter:
                letters.append(letter)
        if len(letters) >= 4 and len(set(letters)) == 1:
            raise ValueError("整套题答案选项过度集中")

    def _validate_exam_style(self, question: Question, exam_id: str, target_language: str) -> None:
        if question.type not in {"multiple_choice", "cloze"}:
            return
        prompt = question.prompt.strip()
        prompt_lower = prompt.lower()
        card_patterns = [
            "最合适的理解",
            "最贴近的中文释义",
            "选择中文释义",
            "根据导入的单词列表",
        ]
        if any(pattern in prompt for pattern in card_patterns):
            raise ValueError("题目像词卡释义题，不符合考试式语境题")
        has_exam_context = (
            "____" in prompt
            or "blank" in prompt_lower
            or "sentence" in prompt_lower
            or "passage" in prompt_lower
            or "which" in prompt_lower
        )
        if not has_exam_context:
            raise ValueError("题干缺少明确语境或空缺")
        if self._requires_english_options(exam_id, target_language):
            for option in question.options:
                if _CJK_TEXT_RE.search(option):
                    raise ValueError("英语考试选择题选项不得包含中文、日文或其他 CJK 字符")

    @staticmethod
    def _requires_english_options(exam_id: str, target_language: str) -> bool:
        return exam_id in _ENGLISH_EXAM_IDS or target_language.strip().lower() in {"英语", "english"}

    def _fallback_question_set(
        self,
        *,
        session_id: str,
        exam_name: str,
        exam_id: str,
        start_sequence: int,
        target_count: int,
        content_pool: list[dict[str, object]],
        exact_count: bool = False,
    ) -> list[Question]:
        terms = [item for item in content_pool if str(item.get("term") or "").strip()]
        if not terms:
            terms = [
                {"term": "affect", "meaning": "影响", "source_scope": "generated"},
                {"term": "effect", "meaning": "结果；效果", "source_scope": "generated"},
                {"term": "context", "meaning": "语境", "source_scope": "generated"},
                {"term": "evidence", "meaning": "证据", "source_scope": "generated"},
                {"term": "infer", "meaning": "推断", "source_scope": "generated"},
                {"term": "contrast", "meaning": "对比", "source_scope": "generated"},
                {"term": "summarize", "meaning": "概括", "source_scope": "generated"},
                {"term": "accurate", "meaning": "准确的", "source_scope": "generated"},
            ]
        questions: list[Question] = []
        total_count = target_count if exact_count else max(4, min(target_count, len(terms) or target_count))
        for offset in range(total_count):
            item = terms[offset % len(terms)]
            sequence = start_sequence + offset
            term = str(item.get("term") or f"item-{sequence}").strip()
            meaning = str(item.get("meaning") or "该知识点的核心含义").strip()
            questions.append(
                self._fallback_question_for_term(
                    session_id,
                    exam_id,
                    sequence,
                    term,
                    meaning,
                    terms,
                    source_scope=str(item.get("source_scope") or ""),
                    scheduled_question_type=str(
                        item.get("scheduled_question_type") or "context_vocabulary"
                    ),
                    scheduled_target_id=str(item.get("scheduled_target_id") or ""),
                    scheduled_reason=str(item.get("scheduled_reason") or ""),
                )
            )
        return questions

    def _fallback_question_for_term(
        self,
        session_id: str,
        exam_id: str,
        sequence: int,
        term: str,
        meaning: str,
        terms: list[dict[str, object]],
        *,
        source_scope: str = "",
        scheduled_question_type: str = "context_vocabulary",
        scheduled_target_id: str = "",
        scheduled_reason: str = "",
    ) -> Question:
        distractors = [
            str(item.get("term") or "").strip().lower()
            for item in terms
            if str(item.get("term") or "").strip() != term and str(item.get("meaning") or "").strip()
        ]
        generic = ["context", "evidence", "method", "result"]
        options = [term.lower(), *distractors, *generic]
        deduped = []
        for option in options:
            if option and option not in deduped:
                deduped.append(option)
        option_count = 4 if len(deduped) >= 4 else max(2, len(deduped))
        correct_index = (sequence - 1) % option_count
        selected = deduped[:option_count]
        correct = selected.pop(0)
        selected.insert(correct_index, correct)
        letter = chr(ord("A") + correct_index)
        sentence = self._fallback_context_sentence(term.lower(), meaning)
        source_type = "user_import" if source_scope == "screenshot_import" else "generated"
        paper_refs = PastPaperService(self.conn).generation_context(exam_id).get("selected_papers", [])
        source_refs = [
            {"type": source_type, "boundary": "practice_only", "term": term},
            {
                "type": "scheduled_target",
                "target_id": scheduled_target_id,
                "question_type": scheduled_question_type,
                "reason": scheduled_reason,
                "boundary": "scheduler_decision",
            },
        ]
        if paper_refs:
            ref = paper_refs[0]
            source_refs.append(
                {
                    "type": "past_paper_style",
                    "id": ref.get("id", ""),
                    "year": ref.get("year"),
                    "title": ref.get("title", ""),
                    "source_url": ref.get("source_url", ""),
                    "boundary": "style_reference_only",
                }
            )
        if scheduled_question_type == "translation":
            return Question(
                id=new_id("q"),
                session_id=session_id,
                sequence=sequence,
                type="translation",
                prompt=f"第 {sequence} 题\nTranslate the target expression in context: {meaning}",
                answer={"correct": term},
                explanation=f"A reference translation for this scheduled target is `{term}`.",
                knowledge_tags=[f"translation:{term}"],
                difficulty=0.5,
                source_refs=source_refs,
            )
        if scheduled_question_type in {"writing", "writing_task1", "writing_task2", "speaking"}:
            return Question(
                id=new_id("q"),
                session_id=session_id,
                sequence=sequence,
                type="short_answer",
                prompt=(
                    f"第 {sequence} 题\nWrite one complete sentence that correctly uses `{term}` "
                    f"to express this idea: {meaning}"
                ),
                answer={"correct": f"A complete context-appropriate sentence using {term}."},
                explanation=(
                    f"The response should use `{term}` accurately and preserve the target idea: {meaning}."
                ),
                knowledge_tags=[f"writing:{term}"],
                difficulty=0.55,
                source_refs=source_refs,
            )
        return Question(
            id=new_id("q"),
            session_id=session_id,
            sequence=sequence,
            type="cloze",
            prompt=(
                f"第 {sequence} 题\n"
                f"Choose the best word to complete the sentence.\n\n{sentence}"
            ),
            options=selected,
            answer={"correct": correct, "letter": letter},
            explanation=(
                f"`{term}` matches the sentence context. Its imported meaning is: {meaning}. "
                "The other options do not fit the semantic clue in the sentence."
            ),
            knowledge_tags=[f"vocabulary:{term}"],
            difficulty=0.35 + min((sequence % 5) * 0.08, 0.32),
            source_refs=source_refs,
        )

    def _fallback_context_sentence(self, term: str, meaning: str) -> str:
        templates = {
            "collision": "The police report said the ______ on the icy road blocked traffic for two hours.",
            "snowstorm": "Because of the heavy ______, several flights were canceled last night.",
            "collection": "The museum's new ______ includes paintings from the nineteenth century.",
            "dry": "The clothes were still wet, so she left them outside to ______ in the sun.",
            "apply": "Students must ______ for the scholarship before the end of this month.",
            "bull": "The farmer kept the ______ in a separate field for safety.",
            "germ": "Washing your hands often can reduce the spread of ______s.",
            "fork": "He picked up a ______ and began to eat the salad.",
            "mysterious": "The scientist could not explain the ______ signal from the old machine.",
            "pot": "She put the soup into a large ______ and warmed it slowly.",
            "book": "Tourists are advised to ______ hotel rooms before the holiday begins.",
            "chair": "Please take a ______ near the window before the lecture starts.",
            "meal": "Breakfast is the first ______ of the day for many people.",
            "steal": "It is illegal to ______ another person's bicycle.",
            "save": "Using less electricity can help families ______ money.",
            "emerge": "New evidence began to ______ during the investigation.",
            "dish": "This restaurant is famous for a spicy chicken ______.",
            "aunt": "My ______ sent me a birthday card from another city.",
            "dull": "The lecture was so ______ that several students lost attention.",
            "state": "The witness was asked to ______ exactly what he had seen.",
            "champion": "After winning the final match, she became the national ______.",
            "aware": "Drivers should be ______ of children crossing the street.",
            "root": "The strong wind pulled the tree up by the ______.",
            "extreme": "The desert is known for its ______ heat during the day.",
            "skin": "Too much sunlight may damage your ______.",
            "hence": "The road was closed; ______, we had to take another route.",
            "vigorous": "The coach asked the team to do ______ exercise every morning.",
            "waterfall": "The path led us to a beautiful ______ deep in the forest.",
            "fierce": "The two companies are in ______ competition for the same market.",
            "contrary": "His actions were ______ to the advice he had received.",
            "discard": "Please ______ any broken glass into the special bin.",
            "evident": "It was ______ from her smile that she was pleased with the result.",
            "fall": "Temperatures usually ______ quickly after sunset in the mountains.",
            "class": "The teacher asked the whole ______ to hand in their papers.",
            "altogether": "There were thirty students ______ in the language club.",
            "forever": "Some memories seem to stay with us ______.",
            "cultivate": "Good teachers try to ______ students' interest in reading.",
            "material": "The factory needs more raw ______ to continue production.",
            "research": "The team carried out ______ into the causes of air pollution.",
            "course": "She signed up for an English writing ______ this semester.",
            "blood": "Doctors tested his ______ before the operation.",
            "executive": "The company hired a new ______ to manage daily operations.",
            "adequate": "The small room did not provide ______ space for all the students.",
            "process": "Learning a language is a long ______ that requires practice.",
            "bow": "The performer gave a polite ______ after the audience applauded.",
            "laser": "Doctors used a ______ to perform the delicate eye operation.",
            "robe": "The judge entered the room wearing a long black ______.",
            "loyalty": "The old worker was respected for his ______ to the company.",
        }
        if term in templates:
            return templates[term]
        hint = meaning.split("；", 1)[0].split(";", 1)[0].strip() or "the meaning in context"
        return f"In this short passage, the word that best matches the idea of \"{hint}\" is ______."

    def _record_model_call(self, result, prompt_modules: list[str], validation_status: str) -> None:
        self.conn.execute(
            """
            INSERT INTO model_calls
            (id, agent_name, task_type, provider_id, model, prompt_modules_json,
             input_tokens, output_tokens, latency_ms, validation_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("call"),
                self.name,
                "question_authoring",
                self.provider.provider_id,
                result.model,
                dumps(prompt_modules),
                result.input_tokens,
                result.output_tokens,
                result.latency_ms,
                validation_status,
            ),
        )


class EvaluatorTutorAgent:
    name = "evaluator_tutor"

    def __init__(self, conn: sqlite3.Connection, provider: ModelProvider):
        self.conn = conn
        self.provider = provider
        self.assembler = PromptAssembler(PromptRegistry(conn))

    def evaluate(
        self,
        session_id: str,
        question_payload: dict,
        user_answer: str,
        extra_prompt: str = "",
    ) -> EvaluationResult:
        correct = question_payload["answer"].get("correct")
        letter = question_payload["answer"].get("letter")
        normalized = user_answer.strip().upper()
        is_correct = normalized == str(letter).upper() or user_answer.strip() == str(correct).strip()
        score = mastery_score(
            MasteryInputs(
                correct_rate=1.0 if is_correct else 0.0,
                days_since_last_attempt=0,
                difficulty=float(question_payload.get("difficulty", 0.5)),
                answered_after_hint=False,
                answered_in_integrated_item=False,
                wrong_repeat_count=0 if is_correct else 1,
            )
        )
        base_feedback = (
            f"判断：{'正确' if is_correct else '不正确'}。\n\n"
            f"正确答案：{letter or ''} {correct}\n\n"
            f"讲解：{question_payload['explanation']}\n\n"
            f"知识点：{', '.join(question_payload.get('knowledge_tags', []))}"
        )
        # 作答记录必须先落库，再调用模型。程序判定此刻已经完成，而模型讲解可能超时、
        # 连接失败或返回不可用结果；若把写入放在模型调用之后，一次超时就会同时丢掉
        # attempts、mark_answered、mastery_events 和掌握度更新，违反 AGENTS.md:37
        # “不得丢失作答记录”。先写入程序判定，模型成功后再回写讲解正文。
        attempt_id = new_id("att")
        self.conn.execute(
            """
            INSERT INTO attempts
            (id, question_id, session_id, user_answer, is_correct, feedback, mastery_delta)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                question_payload["id"],
                session_id,
                user_answer,
                1 if is_correct else 0,
                base_feedback,
                score - 0.5,
            ),
        )
        QuestionService(self.conn).mark_answered(question_payload["id"])
        self.conn.execute(
            """
            INSERT INTO mastery_events (id, question_id, attempt_id, event_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                new_id("mev"),
                question_payload["id"],
                attempt_id,
                dumps({"score_after": score, "created_from": "evaluator_tutor"}),
            ),
        )
        self._update_knowledge_mastery(question_payload, score)
        try:
            feedback = self._feedback_with_model(
                session_id=session_id,
                question_payload=question_payload,
                user_answer=user_answer,
                is_correct=is_correct,
                base_feedback=base_feedback,
                extra_prompt=extra_prompt.strip(),
            )
            feedback_source = "model"
            model_error = ""
        except RuntimeError as exc:
            # 只捕获 RuntimeError：供应商层已把超时、连接错误和响应解析错误统一归一化成
            # ModelProviderError(RuntimeError)，因此这里覆盖了真实的“模型不可用”场景。
            # 提示词组装或数据库层的内部缺陷不属于该类型，应当继续向上抛出而不是被伪装成
            # 模型故障——此时作答记录已经安全落库。
            logger.warning("model request failed during answer feedback, using base feedback", exc_info=True)
            feedback_source = "program_fallback"
            model_error = self._safe_model_error(exc)
            feedback = self._model_failure_feedback(base_feedback, model_error)
        # 回写最终讲解，使成功路径的落库结果与调整顺序前完全一致。
        self.conn.execute(
            "UPDATE attempts SET feedback=? WHERE id=?",
            (feedback, attempt_id),
        )
        MemoryHooks(self.conn).on_attempt(
            session_id=session_id,
            is_correct=is_correct,
            knowledge_tags=[str(tag) for tag in question_payload.get("knowledge_tags", [])],
            question_id=str(question_payload.get("id") or attempt_id),
            scope=f"exam:{ProfileService(self.conn).get().exam_id}",
        )
        return EvaluationResult(
            is_correct=is_correct,
            feedback=feedback,
            mastery_delta=score - 0.5,
            next_action="continue",
            feedback_source=feedback_source,
            model_error=model_error,
        )

    def _update_knowledge_mastery(self, question_payload: dict, score: float) -> None:
        due_at = next_review_at(score).isoformat(timespec="seconds")
        for tag in question_payload.get("knowledge_tags", []):
            term = str(tag).split(":", 1)[-1].strip()
            if not term:
                continue
            rows = self.conn.execute(
                """
                SELECT id FROM knowledge_items
                WHERE term=? OR term=?
                """,
                (term, tag),
            ).fetchall()
            for row in rows:
                self.conn.execute(
                    """
                    UPDATE knowledge_items
                    SET mastery_score=?, due_at=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (score, due_at, row["id"]),
                )

    def _feedback_with_model(
        self,
        *,
        session_id: str,
        question_payload: dict,
        user_answer: str,
        is_correct: bool,
        base_feedback: str,
        extra_prompt: str,
    ) -> str:
        profile = ProfileService(self.conn).get()
        context = ContextService(self.conn).prompt_context(session_id)
        memory_context = context.pop("memory")
        knowledge_query = " ".join(
            [
                str(tag) for tag in question_payload.get("knowledge_tags", [])
            ]
            + [str(question_payload.get("prompt") or ""), user_answer, extra_prompt]
        ).strip()
        knowledge_context = build_knowledge_context(
            self.conn,
            query=knowledge_query,
            task_type="evaluation",
            token_budget=1200,
            trace_id=session_id,
        )
        pack = self.assembler.assemble(
            task_type="evaluation",
            exam_id=profile.exam_id,
            persona=profile.persona if profile.persona != "custom" else "professional",
            context_pack={
                "task_type": TaskType.answer_question.value,
                "session_id": session_id,
                "profile": profile.model_dump(),
                "conversation_context": context,
                "knowledge_retrieval": knowledge_context,
                "memory": memory_context,
                "question": {
                    "id": question_payload.get("id"),
                    "sequence": question_payload.get("sequence"),
                    "prompt": question_payload.get("prompt"),
                    "options": question_payload.get("options", []),
                    "answer": question_payload.get("answer", {}),
                    "explanation": question_payload.get("explanation", ""),
                    "knowledge_tags": question_payload.get("knowledge_tags", []),
                },
                "programmatic_judgement": "correct" if is_correct else "incorrect",
                "base_feedback": base_feedback,
                "user_extra_prompt": extra_prompt,
                "answer_feedback_contract": {
                    "extra_prompt_priority": (
                        "如果 user_extra_prompt 非空，必须先直接回应用户这个补充提问，"
                        "再做常规判题讲解；不要只给泛化学习建议。"
                    ),
                    "progress_footer": (
                        "不要输出“下一题已就绪”、题号进度或本轮完成提示；这些进度提示由程序在模型讲解后统一追加。"
                    ),
                    "profile_usage": (
                        "profile 只用于辅助判断讲解深度、例子难度和复习建议。"
                        "除非用户问到学习设置、制定计划，或画像信息与当前错误直接相关，"
                        "不要显式复述目标分数、考试时间、学习背景或弱项。"
                    ),
                },
            },
            user_content=(
                f"用户选择：{user_answer}\n"
                f"用户额外提问：{extra_prompt or '无'}\n\n"
                "请基于程序判定、完整会话上下文和用户画像生成判题讲解。"
                "如果用户额外提问不是“无”，必须在正文前半部分直接回答这个提问。"
                "必须保留对错结论和正确答案，不要更改正确答案；如果用户没有额外提问，也要主动解释为什么对/错，"
                "指出最该复习的知识点，并给出下一题前的一句具体提醒。"
                "不要写“下一题已就绪”、题号进度或本轮完成提示。"
                "用户画像只作为辅助上下文，不要每次显式重复学习目标、目标分数、考试时间、学习背景或弱项。"
            ),
            allow_global_user_prompt=True,
        )
        saved_prompt = (profile.global_user_prompt or "").strip()
        if saved_prompt:
            pack = pack.model_copy(
                update={
                    "system_modules": [
                        *pack.system_modules,
                        {
                            "id": "profile.saved_user_prompt",
                            "content": (
                                "以下是用户在设置页保存的长期自定义指令，主要用于回复风格、讲题方式和复习建议偏好；"
                                "不得覆盖安全规则、权限边界、题目正确答案或系统功能事实：\n"
                                f"{saved_prompt}"
                            ),
                        },
                    ],
                }
            )
        try:
            result = self.provider.complete(pack)
        except RuntimeError:
            self._record_answer_evaluation_call(
                pack=pack,
                model=self.provider.model,
                input_tokens=0,
                output_tokens=0,
                latency_ms=0,
                validation_status="provider_error_fallback",
            )
            raise
        self._record_answer_evaluation_call(
            pack=pack,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=result.latency_ms,
            validation_status="not_required",
        )
        return self._strip_drill_progress_footer(self._coerce_model_feedback(result.content, base_feedback)) or base_feedback

    def _record_answer_evaluation_call(
        self,
        *,
        pack: Any,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        validation_status: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO model_calls
            (id, agent_name, task_type, provider_id, model, prompt_modules_json,
             input_tokens, output_tokens, latency_ms, validation_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("call"),
                self.name,
                "answer_evaluation",
                self.provider.provider_id,
                model,
                dumps([m["id"] for m in pack.system_modules]),
                input_tokens,
                output_tokens,
                latency_ms,
                validation_status,
            ),
        )

    @staticmethod
    def _safe_model_error(exc: RuntimeError) -> str:
        text = re.sub(r"\s+", " ", str(exc)).strip()
        if not text:
            return "模型请求失败，未返回具体错误。"
        lowered = text.lower()
        if "<html" in lowered or "<!doctype" in lowered or "openresty" in lowered:
            return "模型服务返回非结构化错误页面，请检查 Base URL、API 格式和网络。"
        return text[:240]

    @staticmethod
    def _model_failure_feedback(base_feedback: str, error: str) -> str:
        return (
            "⚠️ Evaluator Tutor（判题讲解智能体）模型讲解未成功，本题已先按程序客观判定保存作答，"
            "避免丢失记录。\n\n"
            f"失败原因：{error}\n\n"
            "以下是程序基础判题：\n\n"
            f"{base_feedback}"
        )

    @staticmethod
    def _coerce_model_feedback(content: str, base_feedback: str) -> str:
        model_feedback = content.strip()
        if not model_feedback:
            return base_feedback
        if model_feedback.startswith("{"):
            parsed = loads(model_feedback, None)
            if isinstance(parsed, dict):
                message = str(
                    parsed.get("message")
                    or parsed.get("feedback")
                    or parsed.get("explanation")
                    or ""
                ).strip()
                if message:
                    return f"{base_feedback}\n\n模型补充：{message}"
                return base_feedback
        return model_feedback

    @staticmethod
    def _strip_drill_progress_footer(feedback: str) -> str:
        lines = feedback.rstrip().splitlines()
        while lines and _DRILL_PROGRESS_LINE_RE.match(lines[-1]):
            lines.pop()
            while lines and not lines[-1].strip():
                lines.pop()
        return "\n".join(lines).strip()


def token_totals(conn: sqlite3.Connection, session_id: str | None = None) -> dict[str, Any]:
    context = ContextService(conn)
    return {
        **context.global_usage_stats(),
        **context.usage(session_id),
    }
