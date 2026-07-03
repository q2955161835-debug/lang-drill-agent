from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import Question, UserProfile
from langdrill_agent.providers import ModelProvider, ModelResult
from langdrill_agent.services import ProfileService, QuestionService, SessionService
from langdrill_agent.utils import dumps, new_id


def test_daily_summary_uses_model_with_full_day_context(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "daily-summary.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)

    with transaction(db_path) as conn:
        ProfileService(conn).update(
            UserProfile(
                learning_goal="四级 600 分",
                learning_background="词汇辨析弱，做题时容易忽略词性。",
                global_user_prompt="总结先指出最需要复盘的错误模式。",
            )
        )
        session_service = SessionService(conn)
        first_session = session_service.ensure_session(None, "method 词义练习", force_new=True)
        second_session = session_service.ensure_session(None, "responsible 复习", force_new=True)
        conn.execute(
            """
            UPDATE study_sessions
            SET daily_plan_json=?
            WHERE id=?
            """,
            (
                dumps(
                    {
                        "new_content": ["method: 方法", "responsible: 负责的"],
                        "review_content": ["project", "collision"],
                        "target_minutes": 35,
                        "status": "formal_question_set_ready",
                    }
                ),
                first_session,
            ),
        )
        question_service = QuestionService(conn)
        questions = [
            Question(
                id="q_summary_1",
                session_id=first_session,
                sequence=1,
                type="multiple_choice",
                prompt="Which word best means a way of doing something?",
                options=["method", "project", "excessive", "responsible"],
                answer={"letter": "A", "correct": "method"},
                explanation="method means a way or procedure.",
                knowledge_tags=["vocabulary:method", "part_of_speech:noun"],
                difficulty=0.35,
            ),
            Question(
                id="q_summary_2",
                session_id=second_session,
                sequence=1,
                type="multiple_choice",
                prompt="Choose the adjective that means being accountable for something.",
                options=["collision", "responsible", "method", "project"],
                answer={"letter": "B", "correct": "responsible"},
                explanation="responsible is an adjective meaning accountable.",
                knowledge_tags=["vocabulary:responsible", "part_of_speech:adjective"],
                difficulty=0.45,
            ),
        ]
        question_service.save_questions(questions)
        for question, user_answer, is_correct, feedback in [
            (questions[0], "B", 0, "误选 project，问题是把名词类别当作语义对应。"),
            (questions[1], "B", 1, "能识别 responsible 的形容词含义。"),
        ]:
            attempt_id = new_id("att")
            conn.execute(
                """
                INSERT INTO attempts
                (id, question_id, session_id, user_answer, is_correct, feedback, mastery_delta)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    question.id,
                    question.session_id,
                    user_answer,
                    is_correct,
                    feedback,
                    0.1 if is_correct else -0.2,
                ),
            )
            question_service.mark_answered(question.id)
        session_service.add_message(first_session, "user", "总结前我觉得 method 和 project 容易混。")

    captured = {}

    def fake_complete(self, pack):
        captured["pack"] = pack
        return ModelResult(
            content="## 今日学习总结\n重点问题是 method 与 project 的词义边界。",
            input_tokens=120,
            output_tokens=42,
            latency_ms=3,
            model=self.model,
        )

    monkeypatch.setattr(ModelProvider, "complete", fake_complete)
    client = TestClient(app)
    response = client.post("/api/chat", json={"content": "总结", "session_id": first_session})

    assert response.status_code == 200
    payload = response.json()
    assert "method 与 project" in payload["message"]["content"]
    assert payload["daily_panel"]["questions_done"] == 2
    assert payload["daily_panel"]["questions_total"] == 2

    pack = captured["pack"]
    module_ids = [module["id"] for module in pack.system_modules]
    assert pack.context_pack["task_type"] == "summary"
    assert "task.summary" in module_ids
    assert "profile.saved_user_prompt" in module_ids
    daily_summary = pack.context_pack["daily_summary"]
    assert daily_summary["panel"]["questions_done"] == 2
    assert len(daily_summary["sessions"]) == 2
    assert len(daily_summary["questions"]) == 2
    wrong_question = next(item for item in daily_summary["questions"] if item["id"] == "q_summary_1")
    assert wrong_question["user_answer"] == "B. project"
    assert wrong_question["correct_answer"] == "A. method"
    assert wrong_question["is_correct"] is False
    assert "vocabulary:method" in wrong_question["knowledge_tags"]
    assert "method" in daily_summary["knowledge"]["needs_review_terms"]

    with transaction(db_path) as conn:
        summary_calls = conn.execute(
            "SELECT COUNT(*) AS total FROM model_calls WHERE task_type='summary'"
        ).fetchone()["total"]
        question_count = conn.execute("SELECT COUNT(*) AS total FROM questions").fetchone()["total"]

    assert summary_calls == 1
    assert question_count == 2
