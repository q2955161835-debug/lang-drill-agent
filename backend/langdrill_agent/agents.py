from __future__ import annotations

import sqlite3
from datetime import datetime

from .algorithm import MasteryInputs, mastery_score
from .models import EvaluationResult, Question, TaskType
from .prompt_engine import PromptAssembler, PromptRegistry
from .providers import ModelProvider
from .services import ProfileService, QuestionService, SessionService
from .utils import dumps, estimate_tokens, new_id
from .validator import QuestionValidator


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
        plan = {
            "new_content": [content.strip()],
            "review_content": self._select_review_stub(profile.exam_id),
            "target_minutes": profile.daily_minutes,
            "status": "question_ready",
            "algorithm": "mastery_score_v1_fsrs_ready",
        }
        self.conn.execute(
            """
            UPDATE study_sessions
            SET daily_plan_json=?, status='active', title=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (dumps(plan), content.strip()[:18] or "日常学习", session_id),
        )

        pack = self.assembler.assemble(
            task_type="daily_drill",
            exam_id=profile.exam_id,
            persona=profile.persona if profile.persona != "custom" else "professional",
            context_pack={
                "task_type": TaskType.daily_drill.value,
                "profile": profile.model_dump(exclude={"global_user_prompt"}),
                "daily_plan": plan,
            },
            user_content=content,
            allow_global_user_prompt=False,
        )
        result = self.provider.complete(pack)
        self._record_model_call("daily_drill", result, [m["id"] for m in pack.system_modules])
        return plan

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

    def ensure_first_question(self, session_id: str) -> Question:
        # ── Bug #3 修复：只查 status='ready' 的题，按 sequence 排序 ──
        existing = self.conn.execute(
            """
            SELECT * FROM questions
            WHERE session_id=? AND status='ready'
            ORDER BY sequence ASC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if existing:
            return self._question_from_row(existing)

        # 计算下一个 sequence
        max_seq_row = self.conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS max_seq FROM questions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        next_seq = (max_seq_row["max_seq"] if max_seq_row else 0) + 1

        profile = self.profile_service.get()
        plan_row = self.conn.execute(
            "SELECT daily_plan_json FROM study_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        plan = plan_row["daily_plan_json"] if plan_row else "{}"
        pack = self.assembler.assemble(
            task_type="question_authoring",
            exam_id=profile.exam_id,
            persona="none",
            context_pack={
                "session_id": session_id,
                "daily_plan_json": plan,
                "exam_id": profile.exam_id,
                "next_sequence": next_seq,
                "output_contract": "Question JSON Schema",
            },
            user_content=f"请生成第 {next_seq} 题，结构化输出并避免泄露答案。",
            output_schema=Question.model_json_schema(),
            allow_global_user_prompt=False,
        )
        result = self.provider.complete(pack)

        # ── Bug #2 修复：真正解析模型输出，不再无条件 fallback ──
        question = self._try_parse_model_output(result.content, session_id, next_seq)
        if question is None:
            # 解析失败或 mock provider 时使用 fallback
            question = self._fallback_question(session_id, profile.exam_name, next_seq)

        validation_status = "passed"
        try:
            self.validator.validate(question)
        except Exception:
            # 校验失败，用 fallback 替代
            question = self._fallback_question(session_id, profile.exam_name, next_seq)
            validation_status = "fallback_after_validation_failure"

        self._save_question(question)
        self._record_model_call(result, [m["id"] for m in pack.system_modules], validation_status)
        return question

    def _try_parse_model_output(
        self, content: str, session_id: str, sequence: int
    ) -> Question | None:
        """尝试从模型 JSON 输出解析为 Question，失败返回 None。"""
        from .utils import loads as json_loads

        # 尝试从 markdown 代码块中提取 JSON
        import re

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        raw_json = json_match.group(1) if json_match else content

        parsed = json_loads(raw_json.strip(), None)
        if not isinstance(parsed, dict):
            return None

        try:
            # 补充必要的字段默认值
            parsed.setdefault("id", new_id("q"))
            parsed.setdefault("session_id", session_id)
            parsed.setdefault("sequence", sequence)
            parsed.setdefault("type", "multiple_choice")
            parsed.setdefault("difficulty", 0.5)
            parsed.setdefault("knowledge_tags", [])
            parsed.setdefault("source_refs", [{"type": "generated", "boundary": "practice_only"}])

            # 确保 answer 字段格式正确
            if "answer" not in parsed or not isinstance(parsed["answer"], dict):
                return None

            return Question(**parsed)
        except Exception:
            return None

    def _fallback_question(self, session_id: str, exam_name: str, sequence: int = 1) -> Question:
        return Question(
            id=new_id("q"),
            session_id=session_id,
            sequence=sequence,
            type="multiple_choice",
            prompt=f"第 {sequence} 题 / 共 5 题\n根据今日学习内容，选择最符合 {exam_name or '目标考试'} 语境的答案：\nWhich sentence uses the word \"affect\" correctly?",
            options=["The new policy may affect student attendance.", "The new policy may effect student attendance.", "The new policy is affect on attendance.", "The policy affected to attendance."],
            answer={"correct": "The new policy may affect student attendance.", "letter": "A"},
            explanation='"Affect" is usually a verb meaning "to influence". In this sentence, the policy may influence attendance, so "affect" is correct.',
            knowledge_tags=["vocabulary:affect-vs-effect", "grammar:verb_usage"],
            difficulty=0.35,
            source_refs=[{"type": "generated", "boundary": "practice_only"}],
        )

    def _save_question(self, question: Question) -> None:
        QuestionService(self.conn).save_question(question)

    def _question_from_row(self, row: sqlite3.Row) -> Question:
        from .utils import loads

        return Question(
            id=row["id"],
            session_id=row["session_id"],
            sequence=row["sequence"],
            type=row["type"],
            prompt=row["prompt"],
            options=loads(row["options_json"], []),
            answer=loads(row["answer_json"], {}),
            explanation=row["explanation"],
            knowledge_tags=loads(row["knowledge_tags_json"], []),
            difficulty=row["difficulty"],
            source_refs=loads(row["source_refs_json"], []),
        )

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
        feedback = (
            f"判断：{'正确' if is_correct else '不正确'}。\n\n"
            f"正确答案：{letter or ''} {correct}\n\n"
            f"讲解：{question_payload['explanation']}\n\n"
            f"知识点：{', '.join(question_payload.get('knowledge_tags', []))}"
        )
        if extra_prompt.strip():
            feedback = self._feedback_with_extra_prompt(
                session_id=session_id,
                question_payload=question_payload,
                user_answer=user_answer,
                is_correct=is_correct,
                base_feedback=feedback,
                extra_prompt=extra_prompt.strip(),
            )
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
                feedback,
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
        return EvaluationResult(
            is_correct=is_correct,
            feedback=feedback,
            mastery_delta=score - 0.5,
            next_action="continue",
        )

    def _feedback_with_extra_prompt(
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
        pack = self.assembler.assemble(
            task_type="evaluation",
            exam_id=profile.exam_id,
            persona=profile.persona if profile.persona != "custom" else "professional",
            context_pack={
                "task_type": TaskType.answer_question.value,
                "session_id": session_id,
                "question": {
                    "id": question_payload.get("id"),
                    "sequence": question_payload.get("sequence"),
                    "prompt": question_payload.get("prompt"),
                    "options": question_payload.get("options", []),
                    "knowledge_tags": question_payload.get("knowledge_tags", []),
                },
                "programmatic_judgement": "correct" if is_correct else "incorrect",
                "base_feedback": base_feedback,
            },
            user_content=(
                f"用户选择：{user_answer}\n"
                f"用户额外提问：{extra_prompt}\n\n"
                "请基于程序判定补充讲解，回答额外提问。不要更改正确答案。"
            ),
            allow_global_user_prompt=True,
        )
        result = self.provider.complete(pack)
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
                "evaluation_extra_prompt",
                self.provider.provider_id,
                result.model,
                dumps([m["id"] for m in pack.system_modules]),
                result.input_tokens,
                result.output_tokens,
                result.latency_ms,
                "not_required",
            ),
        )
        return result.content.strip() or base_feedback


def token_totals(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute(
        "SELECT COALESCE(SUM(input_tokens),0) AS input, COALESCE(SUM(output_tokens),0) AS output FROM model_calls"
    ).fetchone()
    return {
        "input": int(row["input"]),
        "output": int(row["output"]),
        "total": int(row["input"]) + int(row["output"]),
        "estimated_current_context": estimate_tokens(datetime.now().isoformat()),
    }
