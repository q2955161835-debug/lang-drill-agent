from __future__ import annotations

from pathlib import Path

from langdrill_agent.agents import QuestionAuthorAgent
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import UserProfile
from langdrill_agent.providers import ModelResult
from langdrill_agent.services import ProfileService, QuestionService, SessionService
from langdrill_agent.utils import dumps


class StructuredQuestionProvider:
    provider_id = "structured"
    model = "structured-model"

    def __init__(self) -> None:
        self.last_pack = None

    def complete(self, pack):
        self.last_pack = pack
        payload = {
            "opening_message": "已生成结构化题组。",
            "questions": [
                {
                    "type": "cloze",
                    "prompt": "Choose the best word to complete the sentence.\n\nThe speaker gave enough ______ to support the claim.",
                    "options": ["evidence", "robe", "weather", "ticket"],
                    "answer": {"letter": "A", "correct": "evidence"},
                    "explanation": "Evidence supports a claim.",
                    "knowledge_tags": ["vocabulary:evidence"],
                    "difficulty": 0.36,
                    "source_refs": [{"type": "generated", "boundary": "practice_only"}],
                },
                {
                    "type": "multiple_choice",
                    "prompt": "Which option best explains the word in the sentence?",
                    "options": ["It names a color.", "It describes proof.", "It lists a time.", "It marks a place."],
                    "answer": {"letter": "B", "correct": "It describes proof."},
                    "explanation": "The prompt asks for evidence in context.",
                    "knowledge_tags": ["reading:evidence"],
                    "difficulty": 0.42,
                    "source_refs": [{"type": "generated", "boundary": "practice_only"}],
                },
                {
                    "type": "cloze",
                    "prompt": "Choose the best word to complete the sentence.\n\nThe paragraph gives useful ______ for understanding the word.",
                    "options": ["laser", "habit", "context", "window"],
                    "answer": {"letter": "C", "correct": "context"},
                    "explanation": "Context helps readers understand meaning.",
                    "knowledge_tags": ["vocabulary:context"],
                    "difficulty": 0.38,
                    "source_refs": [{"type": "generated", "boundary": "practice_only"}],
                },
                {
                    "type": "multiple_choice",
                    "prompt": "Which sentence best uses method in an academic context?",
                    "options": [
                        "The method was carefully described.",
                        "The weather was carefully described.",
                        "The ticket was carefully described.",
                        "The window was carefully described.",
                    ],
                    "answer": {"letter": "A", "correct": "The method was carefully described."},
                    "explanation": "Method refers to a way of doing research.",
                    "knowledge_tags": ["vocabulary:method"],
                    "difficulty": 0.44,
                    "source_refs": [{"type": "generated", "boundary": "practice_only"}],
                },
            ],
        }
        content = dumps(payload)
        return ModelResult(content=content, input_tokens=20, output_tokens=20, latency_ms=1, model=self.model)


class TimeoutQuestionProvider:
    provider_id = "timeout"
    model = "timeout-model"

    def complete(self, pack):
        raise TimeoutError("simulated provider timeout")


def test_question_author_persists_valid_structured_model_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(tmp_path / "papers"))
    db_path = tmp_path / "structured-output.db"
    init_db(db_path)
    provider = StructuredQuestionProvider()

    with transaction(db_path) as conn:
        ProfileService(conn).update(UserProfile(exam_id="cet4", exam_name="大学英语四级", target_language="英语"))
        session_id = SessionService(conn).ensure_session(None, "structured output", force_new=True)

        result = QuestionAuthorAgent(conn, provider).ensure_question_set(
            session_id,
            "evidence: 证据\ncontext: 语境\nmethod: 方法\nclaim: 主张",
            target_count=4,
        )
        active = QuestionService(conn).active_question(session_id)
        question_rows = conn.execute(
            "SELECT prompt, status FROM questions WHERE session_id=? ORDER BY sequence ASC",
            (session_id,),
        ).fetchall()
        call_rows = conn.execute(
            "SELECT validation_status FROM model_calls WHERE agent_name='question_author'"
        ).fetchall()

    assert provider.last_pack is not None
    assert result["created"] == 4
    assert active is not None
    assert active["prompt"].startswith("Choose the best word")
    assert [row["status"] for row in question_rows] == ["ready", "ready", "ready", "ready"]
    assert [row["validation_status"] for row in call_rows] == ["passed"]


def test_question_author_falls_back_when_provider_times_out(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(tmp_path / "papers"))
    db_path = tmp_path / "timeout-fallback.db"
    init_db(db_path)
    provider = TimeoutQuestionProvider()

    with transaction(db_path) as conn:
        ProfileService(conn).update(UserProfile(exam_id="cet4", exam_name="大学英语四级", target_language="英语"))
        session_id = SessionService(conn).ensure_session(None, "timeout fallback", force_new=True)

        result = QuestionAuthorAgent(conn, provider).ensure_question_set(
            session_id,
            "collection: 收藏\ncollision: 碰撞\ncontext: 语境\nmethod: 方法",
            target_count=4,
        )
        active = QuestionService(conn).active_question(session_id)
        question_rows = conn.execute(
            "SELECT type, status FROM questions WHERE session_id=? ORDER BY sequence ASC",
            (session_id,),
        ).fetchall()
        call_count = conn.execute(
            "SELECT COUNT(*) AS count FROM model_calls WHERE agent_name='question_author'"
        ).fetchone()["count"]

    assert result["created"] >= 4
    assert "本地规则" in str(result["opening_message"])
    assert active is not None
    assert len(question_rows) >= 4
    assert all(row["status"] == "ready" for row in question_rows)
    assert call_count == 0

