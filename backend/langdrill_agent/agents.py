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
        existing = self.conn.execute(
            "SELECT id FROM questions WHERE session_id=? LIMIT 1",
            (session_id,),
        ).fetchone()
        if existing:
            row = self.conn.execute("SELECT * FROM questions WHERE id=?", (existing["id"],)).fetchone()
            return self._question_from_row(row)

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
                "output_contract": "Question JSON Schema",
            },
            user_content="请生成第一题，结构化输出并避免泄露答案。",
            output_schema=Question.model_json_schema(),
            allow_global_user_prompt=False,
        )
        result = self.provider.complete(pack)
        question = self._fallback_question(session_id, profile.exam_name)
        self.validator.validate(question)
        self._save_question(question)
        self._record_model_call(result, [m["id"] for m in pack.system_modules], "passed")
        return question

    def _fallback_question(self, session_id: str, exam_name: str) -> Question:
        return Question(
            id=new_id("q"),
            session_id=session_id,
            sequence=1,
            type="multiple_choice",
            prompt=f"第 1 题 / 共 5 题\n根据今日学习内容，选择最符合 {exam_name or '目标考试'} 语境的答案：\n「彼は毎朝、駅まで歩いて行きます。」这里的「まで」最接近下面哪一项？",
            options=["到某个终点", "从某个起点", "因为某个原因", "和某人一起"],
            answer={"correct": "到某个终点", "letter": "A"},
            explanation="「まで」表示动作或范围到达的终点，此句中是“走到车站”。",
            knowledge_tags=["particle:まで", "reading:sentence_meaning"],
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

    def evaluate(self, session_id: str, question_payload: dict, user_answer: str) -> EvaluationResult:
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
