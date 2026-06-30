from __future__ import annotations

from pathlib import Path

from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import Question, UserProfile
from langdrill_agent.services import ProfileService, QuestionService, SessionService


def _question(session_id: str, question_id: str, sequence: int, tag: str) -> Question:
    return Question(
        id=question_id,
        session_id=session_id,
        sequence=sequence,
        type="multiple_choice",
        prompt=f"第 {sequence} 题：选择正确用法。",
        options=["A option", "B option"],
        answer={"letter": "A", "correct": "A option"},
        explanation="A option is correct.",
        knowledge_tags=[tag],
        difficulty=0.4,
        source_refs=[],
    )


def test_daily_panel_aggregates_same_day_same_exam(tmp_path: Path) -> None:
    db_path = tmp_path / "daily.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        profile_service = ProfileService(conn)
        profile_service.update(UserProfile(exam_id="cet4", exam_name="大学英语四级"))
        sessions = SessionService(conn)
        first = sessions.ensure_session(None, "affect effect")
        second = sessions.ensure_session(None, "grammar drill", force_new=True)

        questions = QuestionService(conn)
        questions.save_question(_question(first, "q_first", 1, "vocabulary:affect"))
        questions.save_question(_question(second, "q_second", 1, "grammar:verb_usage"))
        conn.execute(
            """
            INSERT INTO attempts
            (id, question_id, session_id, user_answer, is_correct, feedback)
            VALUES ('att_first', 'q_first', ?, 'A', 1, 'ok')
            """,
            (first,),
        )
        questions.mark_answered("q_first")

        first_panel = sessions.daily_panel(first)
        second_panel = sessions.daily_panel(second)

    assert first_panel["questions_total"] == 2
    assert first_panel["questions_done"] == 1
    assert first_panel["knowledge_total"] == 2
    assert first_panel["knowledge_done"] == 1
    assert first_panel == second_panel


def test_sessions_are_scoped_to_active_exam(tmp_path: Path) -> None:
    db_path = tmp_path / "exam.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        profiles = ProfileService(conn)
        sessions = SessionService(conn)

        profiles.update(UserProfile(exam_id="cet4", exam_name="大学英语四级"))
        cet4_session = sessions.ensure_session(None, "cet4 words", force_new=True)

        profiles.update(UserProfile(exam_id="ielts", exam_name="雅思"))
        ielts_session = sessions.ensure_session(None, "ielts writing", force_new=True)
        empty_listed = sessions.list_sessions_by_date()
        sessions.add_message(ielts_session, "user", "ielts writing")
        listed = sessions.list_sessions_by_date()

    assert empty_listed == []
    assert [item["id"] for item in listed] == [ielts_session]
    assert cet4_session != ielts_session
