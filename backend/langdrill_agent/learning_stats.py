from __future__ import annotations

import sqlite3
from typing import Any

from .services import ProfileService


class LearningStatsService:
    MASTERY_THRESHOLD = 0.75

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def overview(self) -> dict[str, Any]:
        profile = ProfileService(self.conn).get()
        exam_id = profile.exam_id
        questions = self._question_counts(exam_id)
        words = self._word_counts(exam_id)
        attempts = self._attempt_counts(exam_id)
        total_attempts = attempts["total"]
        return {
            "exam_id": exam_id,
            "exam_name": profile.exam_name,
            "questions_done": questions["done"],
            "questions_total": questions["total"],
            "words_mastered": words["mastered"],
            "words_total": words["total"],
            "accuracy": round(attempts["correct"] / total_attempts, 2) if total_attempts else 0,
            "attempts_total": total_attempts,
            "attempts_correct": attempts["correct"],
        }

    def _question_counts(self, exam_id: str) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
              COUNT(q.id) AS total,
              SUM(CASE WHEN q.status='answered' THEN 1 ELSE 0 END) AS done
            FROM questions q
            JOIN study_sessions s ON s.id = q.session_id
            WHERE s.exam_id=? AND s.status!='deleted'
            """,
            (exam_id,),
        ).fetchone()
        return {"total": int(row["total"] or 0), "done": int(row["done"] or 0)}

    def _word_counts(self, exam_id: str) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
              COUNT(term_key) AS total,
              SUM(CASE WHEN mastery_score>=? THEN 1 ELSE 0 END) AS mastered
            FROM (
              SELECT LOWER(TRIM(term)) AS term_key, MAX(mastery_score) AS mastery_score
              FROM knowledge_items
              WHERE exam_id=? AND TRIM(term)!=''
              GROUP BY LOWER(TRIM(term))
            )
            """,
            (self.MASTERY_THRESHOLD, exam_id),
        ).fetchone()
        return {"total": int(row["total"] or 0), "mastered": int(row["mastered"] or 0)}

    def _attempt_counts(self, exam_id: str) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
              COUNT(a.id) AS total,
              SUM(a.is_correct) AS correct
            FROM attempts a
            JOIN study_sessions s ON s.id = a.session_id
            WHERE s.exam_id=? AND s.status!='deleted'
            """,
            (exam_id,),
        ).fetchone()
        return {"total": int(row["total"] or 0), "correct": int(row["correct"] or 0)}
