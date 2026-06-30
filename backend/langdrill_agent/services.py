from __future__ import annotations

import os
import sqlite3
from copy import deepcopy
from datetime import datetime
from typing import Any

from .config import PROJECT_ROOT
from .models import Question, UserProfile
from .utils import dumps, loads, new_id, today_str


class ProfileService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self) -> UserProfile:
        row = self.conn.execute("SELECT * FROM user_profiles WHERE id = 1").fetchone()
        return UserProfile(**dict(row))

    def update(self, profile: UserProfile) -> UserProfile:
        self.conn.execute(
            """
            UPDATE user_profiles
            SET display_name=?, target_language=?, exam_id=?, exam_name=?, deadline=?,
                daily_minutes=?, learning_goal=?, learning_background=?, persona=?,
                global_user_prompt=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=1
            """,
            (
                profile.display_name,
                profile.target_language,
                profile.exam_id,
                profile.exam_name,
                profile.deadline,
                profile.daily_minutes,
                profile.learning_goal,
                profile.learning_background,
                profile.persona,
                profile.global_user_prompt,
            ),
        )
        return profile


class SessionService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def ensure_session(
        self,
        session_id: str | None,
        title_hint: str = "日常学习",
        *,
        force_new: bool = False,
    ) -> str:
        profile = ProfileService(self.conn).get()
        if session_id and not force_new:
            row = self.conn.execute(
                "SELECT id FROM study_sessions WHERE id=? AND exam_id=?",
                (session_id, profile.exam_id),
            ).fetchone()
            if row:
                return session_id
        if not force_new:
            row = self.conn.execute(
                """
                SELECT id FROM study_sessions
                WHERE folder_date=? AND exam_id=? AND status='active'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (today_str(), profile.exam_id),
            ).fetchone()
            if row:
                return str(row["id"])
        new_session_id = new_id("ses")
        title = title_hint.strip()[:18] or "日常学习"
        self.conn.execute(
            """
            INSERT INTO study_sessions (id, title, folder_date, exam_id, daily_plan_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                new_session_id,
                title,
                today_str(),
                profile.exam_id,
                dumps(
                    {
                        "new_content": [],
                        "review_content": [],
                        "target_minutes": 35,
                        "status": "waiting_for_first_prompt",
                    }
                ),
            ),
        )
        return new_session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        payload: dict[str, Any] | None = None,
    ) -> str:
        msg_id = new_id("msg")
        self.conn.execute(
            """
            INSERT INTO messages (id, session_id, role, content, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (msg_id, session_id, role, content, dumps(payload or {})),
        )
        self.conn.execute(
            "UPDATE study_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (session_id,),
        )
        return msg_id

    def daily_panel(self, session_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM study_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return {}
        scope = self._daily_scope(str(row["folder_date"]), str(row["exam_id"]))
        questions = self.conn.execute(
            """
            SELECT
              COUNT(q.id) AS total,
              SUM(CASE WHEN q.status='answered' THEN 1 ELSE 0 END) AS done
            FROM questions q
            JOIN study_sessions s ON s.id = q.session_id
            WHERE s.folder_date=? AND s.exam_id=? AND s.status!='deleted'
            """,
            (scope["date"], scope["exam_id"]),
        ).fetchone()
        attempts = self.conn.execute(
            """
            SELECT COUNT(a.id) AS total, SUM(a.is_correct) AS correct
            FROM attempts a
            JOIN study_sessions s ON s.id = a.session_id
            WHERE s.folder_date=? AND s.exam_id=? AND s.status!='deleted'
            """,
            (scope["date"], scope["exam_id"]),
        ).fetchone()
        plan = self._merged_daily_plan(scope["date"], scope["exam_id"])
        knowledge = self._knowledge_progress(scope["date"], scope["exam_id"])
        total_attempts = attempts["total"] or 0
        return {
            "date": row["folder_date"],
            "title": f"{scope['exam_name']} 当日学习",
            "status": scope["status"],
            "exam_id": scope["exam_id"],
            "exam_name": scope["exam_name"],
            "plan": plan,
            "questions_total": questions["total"] or 0,
            "questions_done": questions["done"] or 0,
            "knowledge_total": knowledge["total"],
            "knowledge_done": knowledge["done"],
            "knowledge_terms": knowledge["terms"],
            "accuracy": round((attempts["correct"] or 0) / total_attempts, 2) if total_attempts else 0,
            "summary": row["summary"],
        }

    def list_sessions_by_date(self) -> list[dict[str, Any]]:
        profile = ProfileService(self.conn).get()
        rows = self.conn.execute(
            """
            SELECT s.id, s.title, s.folder_date, s.exam_id, s.status, s.updated_at
            FROM study_sessions s
            WHERE s.exam_id=?
              AND s.status!='deleted'
              AND EXISTS (SELECT 1 FROM messages m WHERE m.session_id=s.id)
            ORDER BY s.folder_date DESC, s.updated_at DESC
            """,
            (profile.exam_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        row = self.conn.execute("SELECT id FROM study_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return False
        self.conn.execute("DELETE FROM study_sessions WHERE id=?", (session_id,))
        return True

    def load_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE session_id=? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def load_session_detail(self, session_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM study_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return {}
        messages = self.load_session_messages(session_id)
        panel = self.daily_panel(session_id)
        active_q = QuestionService(self.conn).active_question(session_id)
        return {
            "session": dict(row),
            "messages": messages,
            "daily_panel": panel,
            "active_question": active_q,
        }

    def question_progress(self, session_id: str) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
              COUNT(id) AS total,
              SUM(CASE WHEN status='answered' THEN 1 ELSE 0 END) AS done,
              SUM(CASE WHEN status='ready' THEN 1 ELSE 0 END) AS ready
            FROM questions
            WHERE session_id=?
            """,
            (session_id,),
        ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "done": int(row["done"] or 0),
            "ready": int(row["ready"] or 0),
        }

    def mark_completed_if_finished(self, session_id: str) -> bool:
        progress = self.question_progress(session_id)
        if progress["total"] and not progress["ready"]:
            self.conn.execute(
                """
                UPDATE study_sessions
                SET status='completed', updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (session_id,),
            )
            return True
        return False

    def _daily_scope(self, date: str, exam_id: str) -> dict[str, str]:
        profile = ProfileService(self.conn).get()
        row = self.conn.execute(
            """
            SELECT
              SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active_count,
              MAX(updated_at) AS updated_at
            FROM study_sessions
            WHERE folder_date=? AND exam_id=? AND status!='deleted'
            """,
            (date, exam_id),
        ).fetchone()
        return {
            "date": date,
            "exam_id": exam_id,
            "exam_name": profile.exam_name if profile.exam_id == exam_id else exam_id,
            "status": "active" if row and (row["active_count"] or 0) else "idle",
        }

    def _merged_daily_plan(self, date: str, exam_id: str) -> dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT daily_plan_json FROM study_sessions
            WHERE folder_date=? AND exam_id=? AND status!='deleted'
            ORDER BY updated_at ASC
            """,
            (date, exam_id),
        ).fetchall()
        merged: dict[str, Any] = {
            "new_content": [],
            "review_content": [],
            "target_minutes": ProfileService(self.conn).get().daily_minutes,
            "status": "waiting_for_first_prompt",
        }
        for row in rows:
            plan = loads(row["daily_plan_json"], {})
            for key in ("new_content", "review_content"):
                for item in plan.get(key, []) or []:
                    if item and item not in merged[key]:
                        merged[key].append(item)
            if plan.get("target_minutes"):
                merged["target_minutes"] = plan["target_minutes"]
            if plan.get("status") and plan["status"] != "waiting_for_first_prompt":
                merged["status"] = plan["status"]
            if plan.get("algorithm"):
                merged["algorithm"] = plan["algorithm"]
        return merged

    def _knowledge_progress(self, date: str, exam_id: str) -> dict[str, Any]:
        question_rows = self.conn.execute(
            """
            SELECT q.knowledge_tags_json, q.status
            FROM questions q
            JOIN study_sessions s ON s.id = q.session_id
            WHERE s.folder_date=? AND s.exam_id=?
            """,
            (date, exam_id),
        ).fetchall()
        all_tags: list[str] = []
        answered_tags: list[str] = []
        for row in question_rows:
            tags = [str(tag) for tag in loads(row["knowledge_tags_json"], []) if str(tag).strip()]
            all_tags.extend(tags)
            if row["status"] == "answered":
                answered_tags.extend(tags)
        imported_rows = self.conn.execute(
            """
            SELECT term, mastery_score
            FROM knowledge_items
            WHERE exam_id=? AND DATE(created_at, 'localtime')=?
            """,
            (exam_id, date),
        ).fetchall()
        for row in imported_rows:
            term = str(row["term"]).strip()
            if not term:
                continue
            all_tags.append(term)
            if float(row["mastery_score"] or 0) >= 0.75:
                answered_tags.append(term)
        unique_all = sorted(set(all_tags))
        unique_done = sorted(set(answered_tags))
        return {
            "total": len(unique_all),
            "done": len(unique_done),
            "terms": unique_all[:8],
        }


class QuestionService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def active_question(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT * FROM questions
            WHERE session_id=? AND status='ready'
            ORDER BY sequence ASC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return self._row_to_payload(row) if row else None

    def question_progress(self, session_id: str) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
              COUNT(id) AS total,
              SUM(CASE WHEN status='answered' THEN 1 ELSE 0 END) AS done,
              SUM(CASE WHEN status='ready' THEN 1 ELSE 0 END) AS ready
            FROM questions
            WHERE session_id=?
            """,
            (session_id,),
        ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "done": int(row["done"] or 0),
            "ready": int(row["ready"] or 0),
        }

    def next_sequence(self, session_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS max_seq FROM questions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return int(row["max_seq"] or 0) + 1

    def question_by_id(self, question_id: str, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT * FROM questions
            WHERE id=? AND session_id=? AND status='ready'
            LIMIT 1
            """,
            (question_id, session_id),
        ).fetchone()
        return self._row_to_payload(row) if row else None

    def save_question(self, question: Question) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO questions
            (id, session_id, sequence, type, prompt, options_json, answer_json, explanation,
             knowledge_tags_json, difficulty, status, source_refs_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question.id,
                question.session_id,
                question.sequence,
                question.type,
                question.prompt,
                dumps(question.options),
                dumps(question.answer),
                question.explanation,
                dumps(question.knowledge_tags),
                question.difficulty,
                "ready",
                dumps(question.source_refs),
            ),
        )

    def save_questions(self, questions: list[Question]) -> None:
        for question in questions:
            self.save_question(question)

    def mark_answered(self, question_id: str) -> None:
        self.conn.execute("UPDATE questions SET status='answered' WHERE id=?", (question_id,))

    def _row_to_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["options"] = loads(payload.pop("options_json"), [])
        payload["answer"] = loads(payload.pop("answer_json"), {})
        payload["knowledge_tags"] = loads(payload.pop("knowledge_tags_json"), [])
        payload["source_refs"] = loads(payload.pop("source_refs_json"), [])
        return payload


class SourceService:
    COMMON_SYLLABUS_SOURCES = [
        {
            "exam_id": "cjt4",
            "title": "全国大学日语四、六级考试大纲（2024年启用）",
            "year": 2024,
            "url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "trusted_level": "official_or_exam_org",
        },
        {
            "exam_id": "cet4",
            "title": "全国大学英语四、六级考试大纲（2016年修订版）",
            "year": 2016,
            "url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "trusted_level": "official_or_exam_org",
        },
        {
            "exam_id": "cet6",
            "title": "全国大学英语四、六级考试大纲（2016年修订版）",
            "year": 2016,
            "url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "trusted_level": "official_or_exam_org",
        },
        {
            "exam_id": "ielts",
            "title": "IELTS Academic test format（雅思学术类考试结构）",
            "year": 2026,
            "url": "https://ielts.org/take-a-test/test-types/ielts-academic-test",
            "trusted_level": "official",
        },
        {
            "exam_id": "toefl",
            "title": "TOEFL iBT Test Content（托福网考考试内容）",
            "year": 2026,
            "url": "https://www.ets.org/toefl/test-takers/ibt/about/content.html",
            "trusted_level": "official_or_exam_org",
        },
        {
            "exam_id": "gaokao-english",
            "title": "普通高中英语课程标准（2017年版2020年修订）",
            "year": 2020,
            "url": "https://www.moe.gov.cn/srcsite/A26/s8001/202006/t20200603_462199.html",
            "trusted_level": "official",
        },
    ]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def seed_common_sources(self) -> None:
        for source in self.COMMON_SYLLABUS_SOURCES:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO syllabus_sources
                (id, exam_id, title, year, url, trusted_level, copyright_boundary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"src_{source['exam_id']}",
                    source["exam_id"],
                    source["title"],
                    source["year"],
                    source["url"],
                    source["trusted_level"],
                    "index_and_reference",
                ),
            )
            self.conn.execute(
                """
                UPDATE syllabus_sources
                SET year=COALESCE(year, ?),
                    url=CASE WHEN url='' THEN ? ELSE url END,
                    title=CASE WHEN title='' THEN ? ELSE title END
                WHERE id=?
                """,
                (source["year"], source["url"], source["title"], f"src_{source['exam_id']}"),
            )


class SyllabusService:
    EXAM_OPTIONS = [
        {
            "id": "cet4",
            "name": "英语四级",
            "target_language": "英语",
            "official_url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "default_year": 2016,
            "description": "大学英语四级，默认考试。",
        },
        {
            "id": "cjt4",
            "name": "日语四级",
            "target_language": "日语",
            "official_url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "default_year": 2024,
            "description": "大学日语四级，新版考纲 2024 年启用。",
        },
        {
            "id": "ielts",
            "name": "雅思",
            "target_language": "英语",
            "official_url": "https://ielts.org/take-a-test/test-types/ielts-academic-test",
            "default_year": 2026,
            "description": "雅思学术类考试结构，官方页面持续维护。",
        },
        {
            "id": "toefl",
            "name": "托福",
            "target_language": "英语",
            "official_url": "https://www.ets.org/toefl/test-takers/ibt/about/content.html",
            "default_year": 2026,
            "description": "托福网考考试结构，官方页面持续维护。",
        },
        {
            "id": "gaokao-english",
            "name": "高考英语",
            "target_language": "英语",
            "official_url": "https://www.moe.gov.cn/srcsite/A26/s8001/202006/t20200603_462199.html",
            "default_year": 2020,
            "description": "普通高中英语课程标准，按高考英语能力框架使用。",
        },
        {
            "id": "custom",
            "name": "添加自定义",
            "target_language": "",
            "official_url": "",
            "default_year": None,
            "description": "可配置考纲网址自动下载或手动导入。",
        },
    ]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def exam_options(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.EXAM_OPTIONS]

    def status(self, exam_id: str | None = None) -> dict[str, Any]:
        SourceService(self.conn).seed_common_sources()
        profile = ProfileService(self.conn).get()
        target_exam = exam_id or profile.exam_id
        rows = self.conn.execute(
            """
            SELECT id, exam_id, title, year, url, local_path, trusted_level,
                   is_latest_checked, checked_at, created_at
            FROM syllabus_sources
            WHERE exam_id=?
            ORDER BY year DESC, created_at DESC
            """,
            (target_exam,),
        ).fetchall()
        sources = [dict(row) for row in rows]
        current = sources[0] if sources else self._default_source(target_exam)
        selected_id = self._selected_source_id(target_exam) or current.get("id", "")
        return {
            "exam_id": target_exam,
            "current_source_id": selected_id,
            "current_year": current.get("year"),
            "current_title": current.get("title", ""),
            "official_url": current.get("url", self._exam_option(target_exam).get("official_url", "")),
            "sources": sources,
        }

    def manual_check(self, exam_id: str) -> dict[str, Any]:
        SourceService(self.conn).seed_common_sources()
        option = self._exam_option(exam_id)
        default_year = option.get("default_year")
        latest = self.status(exam_id)
        current_year = latest.get("current_year")
        changed = bool(default_year and (not current_year or int(current_year) < int(default_year)))
        if changed:
            source_id = f"src_{exam_id}_{default_year}"
            self.conn.execute(
                """
                INSERT OR IGNORE INTO syllabus_sources
                (id, exam_id, title, year, url, trusted_level, copyright_boundary, is_latest_checked, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, 'index_and_reference', 1, CURRENT_TIMESTAMP)
                """,
                (
                    source_id,
                    exam_id,
                    option["name"] + f"考纲 {default_year}",
                    default_year,
                    option.get("official_url", ""),
                    "official",
                ),
            )
            self._select_source(exam_id, source_id)
            return {
                "changed": True,
                "message": f"已录入 {default_year} 年考纲，旧年份仍保留在可选考纲中。",
                "status": self.status(exam_id),
            }
        if latest["sources"]:
            self.conn.execute(
                """
                UPDATE syllabus_sources
                SET is_latest_checked=1, checked_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (latest["sources"][0]["id"],),
            )
        return {
            "changed": False,
            "message": f"当前 {current_year} 年考纲已是最新考纲。",
            "status": self.status(exam_id),
        }

    def select_source(self, exam_id: str, source_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT id FROM syllabus_sources WHERE exam_id=? AND id=?",
            (exam_id, source_id),
        ).fetchone()
        if not row:
            raise ValueError("考纲不存在，无法切换。")
        self._select_source(exam_id, source_id)
        return self.status(exam_id)

    def _select_source(self, exam_id: str, source_id: str) -> None:
        key = f"syllabus.selected.{exam_id}"
        self.conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (key, dumps({"source_id": source_id})),
        )

    def _selected_source_id(self, exam_id: str) -> str:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (f"syllabus.selected.{exam_id}",),
        ).fetchone()
        data = loads(row["value_json"], {}) if row else {}
        return str(data.get("source_id", ""))

    def _exam_option(self, exam_id: str) -> dict[str, Any]:
        return next((item for item in self.EXAM_OPTIONS if item["id"] == exam_id), self.EXAM_OPTIONS[-1])

    def _default_source(self, exam_id: str) -> dict[str, Any]:
        option = self._exam_option(exam_id)
        return {
            "id": "",
            "exam_id": exam_id,
            "title": option.get("name", exam_id),
            "year": option.get("default_year"),
            "url": option.get("official_url", ""),
            "local_path": "",
            "trusted_level": "unknown",
            "is_latest_checked": 0,
            "checked_at": None,
        }


class ModelConfigService:
    MOCK_PROVIDER = {
        "id": "mock",
        "label": "Mock Provider（本地模拟）",
        "kind": "mock",
        "api_format": "mock",
        "api_key_required": False,
        "enabled": True,
        "base_url": "",
        "model": "mock-tutor-v1",
        "model_options": [
            {
                "id": "mock-tutor-v1",
                "label": "mock-tutor-v1",
                "context_tokens": 0,
                "reasoning": {
                    "default_level": "",
                    "parameter": "",
                    "levels": [],
                },
            }
        ],
    }
    PROVIDERS = [
        {
            "id": "openai",
            "label": "OpenAI GPT（OpenAI GPT）",
            "kind": "openai-compatible",
            "api_format": "openai-chat-completions",
            "api_key_required": True,
            "enabled": True,
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5.5",
            "model_options": [
                {
                    "id": "gpt-5.5",
                    "label": "gpt-5.5",
                    "context_tokens": 1000000,
                    "reasoning": {
                        "default_level": "auto",
                        "parameter": "openai_reasoning_effort",
                        "levels": [
                            {"id": "auto", "label": "自动", "api_value": ""},
                            {"id": "minimal", "label": "极低", "api_value": "minimal"},
                            {"id": "low", "label": "低", "api_value": "low"},
                            {"id": "medium", "label": "中", "api_value": "medium"},
                            {"id": "high", "label": "高", "api_value": "high"},
                            {"id": "xhigh", "label": "极高", "api_value": "xhigh"},
                        ],
                    },
                },
                {
                    "id": "gpt-5.4",
                    "label": "gpt-5.4",
                    "context_tokens": 1000000,
                    "reasoning": {
                        "default_level": "auto",
                        "parameter": "openai_reasoning_effort",
                        "levels": [
                            {"id": "auto", "label": "自动", "api_value": ""},
                            {"id": "minimal", "label": "极低", "api_value": "minimal"},
                            {"id": "low", "label": "低", "api_value": "low"},
                            {"id": "medium", "label": "中", "api_value": "medium"},
                            {"id": "high", "label": "高", "api_value": "high"},
                            {"id": "xhigh", "label": "极高", "api_value": "xhigh"},
                        ],
                    },
                },
            ],
        },
        {
            "id": "claude",
            "label": "Claude（Claude）",
            "kind": "anthropic",
            "api_format": "anthropic-messages",
            "api_key_required": True,
            "enabled": True,
            "base_url": "https://api.anthropic.com",
            "model": "claude-sonnet-4.7",
            "model_options": [
                {
                    "id": "claude-sonnet-4.7",
                    "label": "claude-sonnet-4.7",
                    "context_tokens": 200000,
                    "reasoning": {
                        "default_level": "medium",
                        "parameter": "anthropic_adaptive_thinking",
                        "levels": [
                            {"id": "off", "label": "关闭", "api_value": ""},
                            {"id": "low", "label": "低", "api_value": "low"},
                            {"id": "medium", "label": "中", "api_value": "medium"},
                            {"id": "high", "label": "高", "api_value": "high"},
                        ],
                    },
                },
                {
                    "id": "claude-opus-4.7",
                    "label": "claude-opus-4.7",
                    "context_tokens": 200000,
                    "reasoning": {
                        "default_level": "medium",
                        "parameter": "anthropic_adaptive_thinking",
                        "levels": [
                            {"id": "off", "label": "关闭", "api_value": ""},
                            {"id": "low", "label": "低", "api_value": "low"},
                            {"id": "medium", "label": "中", "api_value": "medium"},
                            {"id": "high", "label": "高", "api_value": "high"},
                        ],
                    },
                },
            ],
        },
        {
            "id": "deepseek",
            "label": "DeepSeek（深度求索）",
            "kind": "openai-compatible",
            "api_format": "openai-chat-completions",
            "api_key_required": True,
            "enabled": True,
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-pro",
            "model_options": [
                {
                    "id": "deepseek-v4-pro",
                    "label": "deepseek-v4-pro",
                    "context_tokens": 1000000,
                    "reasoning": {
                        "default_level": "max",
                        "parameter": "deepseek_thinking",
                        "levels": [
                            {"id": "off", "label": "关闭", "api_value": ""},
                            {"id": "high", "label": "高", "api_value": "high"},
                            {"id": "max", "label": "最高", "api_value": "max"},
                        ],
                    },
                },
                {
                    "id": "deepseek-v4-flash",
                    "label": "deepseek-v4-flash",
                    "context_tokens": 1000000,
                    "reasoning": {
                        "default_level": "high",
                        "parameter": "deepseek_thinking",
                        "levels": [
                            {"id": "off", "label": "关闭", "api_value": ""},
                            {"id": "high", "label": "高", "api_value": "high"},
                            {"id": "max", "label": "最高", "api_value": "max"},
                        ],
                    },
                },
            ],
        },
        {
            "id": "mimo",
            "label": "Xiaomi MiMo（小米 MiMo）",
            "kind": "anthropic",
            "api_format": "anthropic-messages",
            "api_key_required": True,
            "enabled": True,
            "base_url": "https://api.xiaomimimo.com/anthropic",
            "model": "mimo-v2.5-pro",
            "model_options": [
                {
                    "id": "mimo-v2.5",
                    "label": "mimo-v2.5",
                    "context_tokens": 1000000,
                    "reasoning": {
                        "default_level": "enabled",
                        "parameter": "anthropic_thinking_switch",
                        "levels": [
                            {"id": "off", "label": "关闭", "api_value": ""},
                            {"id": "enabled", "label": "开启", "api_value": "enabled"},
                        ],
                    },
                },
                {
                    "id": "mimo-v2.5-pro",
                    "label": "mimo-v2.5-pro",
                    "context_tokens": 1000000,
                    "reasoning": {
                        "default_level": "enabled",
                        "parameter": "anthropic_thinking_switch",
                        "levels": [
                            {"id": "off", "label": "关闭", "api_value": ""},
                            {"id": "enabled", "label": "开启", "api_value": "enabled"},
                        ],
                    },
                },
            ],
        },
    ]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def thinking_level_options(self, provider_id: str, model: str) -> list[dict[str, str]]:
        model_config = self._model_config(provider_id, model)
        reasoning = model_config.get("reasoning", {}) if model_config else {}
        return [dict(item) for item in reasoning.get("levels", []) if item.get("id")]

    def _normalize_thinking_level(
        self,
        value: str,
        options: list[dict[str, str]] | None = None,
        *,
        default: str = "",
    ) -> str:
        if not options:
            return ""
        allowed = {item["id"] for item in options if item.get("id")}
        if value in allowed:
            return value
        if default in allowed:
            return default
        return options[0]["id"]

    def providers(self) -> list[dict[str, Any]]:
        row = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.custom_providers'").fetchone()
        customs = loads(row["value_json"], []) if row else []

        row_ov = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.provider_overrides'").fetchone()
        overrides = loads(row_ov["value_json"], {}) if row_ov else {}

        env_values = {**self._read_env(), **self._read_process_env()}
        current_provider_id = self._current_provider_id(env_values)
        all_providers = [self._apply_provider_overrides(deepcopy(p), overrides) for p in self.PROVIDERS]
        all_providers.extend(self._apply_provider_overrides(self._normalize_custom_provider(p), overrides) for p in customs)
        all_providers.append(deepcopy(self.MOCK_PROVIDER))

        for provider in all_providers:
            has_key = bool(self._provider_api_key(provider["id"], env_values, current_provider_id))
            if provider["id"] == "mock":
                has_key = False
            provider["has_api_key"] = has_key
            provider["visible_in_picker"] = provider["id"] != "mock" and (
                bool(provider.get("enabled", True)) and (not provider.get("api_key_required", True) or has_key)
            )
        return all_providers

    def current(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key='model.default'"
        ).fetchone()
        config = loads(row["value_json"], {}) if row else {}
        env_values = {**self._read_env(), **self._read_process_env()}
        provider_id = config.get("provider_id") or env_values.get("LANGDRILL_DEFAULT_PROVIDER") or "mimo"
        provider = self.provider_by_id(provider_id)
        model = config.get("model") or env_values.get("LANGDRILL_DEFAULT_MODEL") or provider.get("model", "")
        options = self.thinking_level_options(provider_id, model)
        model_config = self._model_config(provider_id, model)
        reasoning = model_config.get("reasoning", {}) if model_config else {}
        default_level = reasoning.get("default_level", "")
        thinking_level = self._normalize_thinking_level(
            config.get("thinking_level") or default_level,
            options,
            default=default_level,
        )
        has_key = bool(self._provider_api_key(provider_id, env_values, provider_id))
        if provider_id == "mock":
            has_key = False
            return {
                "provider_id": "mock",
                "base_url": "",
                "model": model or provider.get("model", "mock-tutor-v1"),
                "thinking_level": "auto",
                "thinking_level_options": [{"id": "auto", "label": "自动", "api_value": ""}],
                "thinking_api_value": "",
                "reasoning_parameter": "",
                "api_format": "mock",
                "has_api_key": False,
                "visible_in_picker": False,
            }
        api_value = self._thinking_api_value(thinking_level, options)
        return {
            "provider_id": provider_id,
            "base_url": config.get("base_url")
            or env_values.get("LANGDRILL_PROVIDER_BASE_URL")
            or provider.get("base_url", ""),
            "model": model,
            "thinking_level": thinking_level,
            "thinking_level_options": self.thinking_level_options(provider_id, model),
            "thinking_api_value": api_value,
            "reasoning_parameter": reasoning.get("parameter", ""),
            "api_format": config.get("api_format") or provider.get("api_format", "openai-chat-completions"),
            "has_api_key": has_key,
            "visible_in_picker": bool(provider.get("enabled", True)) and (not provider.get("api_key_required", True) or has_key),
        }

    def current_for_ui(self) -> dict[str, Any]:
        config = self.current()
        if config.get("provider_id") != "mock":
            return config
        return self.save(
            "mimo",
            "https://api.xiaomimimo.com/anthropic",
            "mimo-v2.5-pro",
            thinking_level="enabled",
            api_format="anthropic-messages",
        )

    def current_with_secret(self) -> dict[str, Any]:
        config = self.current()
        if config.get("provider_id") == "mock":
            config["api_key"] = ""
            return config
        env_values = {**self._read_env(), **self._read_process_env()}
        config["api_key"] = self._provider_api_key(str(config.get("provider_id", "")), env_values, str(config.get("provider_id", "")))
        return config

    def provider_by_id(self, provider_id: str) -> dict[str, Any]:
        all_providers = self.providers()
        return next((item for item in all_providers if item["id"] == provider_id), deepcopy(self.MOCK_PROVIDER))

    def save(
        self,
        provider_id: str,
        base_url: str,
        model: str,
        api_key: str = "",
        *,
        thinking_level: str = "auto",
        thinking_level_options: list[dict[str, str]] | None = None,
        api_format: str = "",
    ) -> dict[str, Any]:
        provider = self.provider_by_id(provider_id)
        clean_base_url = (base_url or provider.get("base_url", "")).strip()
        clean_model = (model or provider.get("model", "")).strip()
        clean_api_format = (api_format or provider.get("api_format", "openai-chat-completions")).strip()
        clean_options = self._normalize_thinking_options(thinking_level_options or self.thinking_level_options(provider_id, clean_model))
        model_config = self._model_config(provider_id, clean_model)
        reasoning = dict(model_config.get("reasoning", {})) if model_config else {}
        if clean_options:
            reasoning["levels"] = clean_options
            reasoning.setdefault("parameter", self._default_reasoning_parameter(provider_id))
            reasoning["default_level"] = thinking_level if thinking_level in {item["id"] for item in clean_options} else (
                reasoning.get("default_level") or clean_options[0]["id"]
            )
        clean_thinking_level = self._normalize_thinking_level(
            thinking_level,
            clean_options,
            default=reasoning.get("default_level", ""),
        )

        self.conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
            VALUES ('model.default', ?, CURRENT_TIMESTAMP)
            """,
            (
                dumps(
                    {
                        "provider_id": provider_id,
                        "base_url": clean_base_url,
                        "model": clean_model,
                        "thinking_level": clean_thinking_level,
                        "api_format": clean_api_format,
                    }
                ),
            ),
        )

        row_ov = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.provider_overrides'").fetchone()
        overrides = loads(row_ov["value_json"], {}) if row_ov else {}
        ov = overrides.setdefault(provider_id, {"added_models": [], "model_reasoning_overrides": {}})
        ov["base_url"] = clean_base_url
        ov["api_format"] = clean_api_format
        known_model_ids = {self._model_id(item) for item in provider.get("model_options", [])}
        if clean_model and clean_model not in known_model_ids:
            added = ov.setdefault("added_models", [])
            if clean_model not in {self._model_id(item) for item in added}:
                added.append(
                    {
                        "id": clean_model,
                        "label": clean_model,
                        "context_tokens": 0,
                        "reasoning": reasoning,
                    }
                )
        if clean_options:
            reasoning["levels"] = clean_options
            reasoning["default_level"] = clean_thinking_level
            ov.setdefault("model_reasoning_overrides", {})[clean_model] = reasoning

        self.conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value_json, updated_at) VALUES ('model.provider_overrides', ?, CURRENT_TIMESTAMP)",
            (dumps(overrides),),
        )
        api_key_updates = {}
        if api_key:
            api_key_updates[self._api_key_env_key(provider_id)] = api_key.strip()
            api_key_updates["LANGDRILL_PROVIDER_API_KEY"] = api_key.strip()
        self._write_env(
            {
                "LANGDRILL_DEFAULT_PROVIDER": provider_id,
                "LANGDRILL_DEFAULT_MODEL": clean_model,
                "LANGDRILL_PROVIDER_BASE_URL": clean_base_url,
                **api_key_updates,
            }
        )
        return self.current()

    def reset_defaults(self) -> dict[str, Any]:
        self.conn.execute(
            "DELETE FROM app_settings WHERE key IN ('model.default', 'model.provider_overrides', 'model.custom_providers')"
        )
        self._write_env(
            {
                "LANGDRILL_DEFAULT_PROVIDER": "mimo",
                "LANGDRILL_DEFAULT_MODEL": "mimo-v2.5-pro",
                "LANGDRILL_PROVIDER_BASE_URL": "https://api.xiaomimimo.com/anthropic",
            }
        )
        return self.current()

    def add_custom_provider(self, name: str, base_url: str, default_model: str) -> None:
        row = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.custom_providers'").fetchone()
        customs = loads(row["value_json"], []) if row else []
        new_id = f"custom_{len(customs) + 1}_{int(datetime.now().timestamp())}"
        clean_model = default_model.strip()
        customs.append({
            "id": new_id,
            "label": f"{name}（自定义）",
            "kind": "openai-compatible",
            "api_format": "openai-chat-completions",
            "api_key_required": True,
            "enabled": True,
            "base_url": base_url.strip(),
            "model": clean_model,
            "model_options": [clean_model] if clean_model else [],
        })
        self.conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value_json, updated_at) VALUES ('model.custom_providers', ?, CURRENT_TIMESTAMP)",
            (dumps(customs),),
        )

    def _normalize_custom_provider(self, provider: dict[str, Any]) -> dict[str, Any]:
        item = deepcopy(provider)
        item.setdefault("kind", "openai-compatible")
        item.setdefault("api_format", "openai-chat-completions")
        item.setdefault("api_key_required", True)
        item.setdefault("enabled", True)
        item.setdefault("base_url", "")
        item.setdefault("model", "")
        item["model_options"] = [self._normalize_model_option(m) for m in item.get("model_options", []) if self._model_id(m)]
        return item

    def _apply_provider_overrides(self, provider: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        ov = overrides.get(provider["id"], {})
        if ov:
            provider["base_url"] = ov.get("base_url", provider.get("base_url", ""))
            provider["api_format"] = ov.get("api_format", provider.get("api_format", "openai-chat-completions"))
            provider["enabled"] = bool(ov.get("enabled", provider.get("enabled", True)))
            model_options = [self._normalize_model_option(item) for item in provider.get("model_options", [])]
            existing = {self._model_id(item) for item in model_options}
            for model in ov.get("added_models", []):
                normalized = self._normalize_model_option(model)
                if normalized["id"] and normalized["id"] not in existing:
                    model_options.append(normalized)
                    existing.add(normalized["id"])
            reasoning_overrides = ov.get("model_reasoning_overrides", {})
            for model_item in model_options:
                model_id = self._model_id(model_item)
                if model_id in reasoning_overrides:
                    model_item["reasoning"] = reasoning_overrides[model_id]
            provider["model_options"] = model_options
        else:
            provider["model_options"] = [self._normalize_model_option(item) for item in provider.get("model_options", [])]
        return provider

    def _normalize_model_option(self, value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            return {
                "id": value,
                "label": value,
                "context_tokens": 0,
                "reasoning": {"default_level": "", "parameter": self._default_reasoning_parameter(""), "levels": []},
            }
        item = dict(value or {})
        item.setdefault("id", item.get("model", ""))
        item.setdefault("label", item.get("id", ""))
        item.setdefault("context_tokens", 0)
        item.setdefault("reasoning", {"default_level": "", "parameter": self._default_reasoning_parameter(""), "levels": []})
        if item["reasoning"]:
            item["reasoning"]["levels"] = self._normalize_thinking_options(item["reasoning"].get("levels", []))
        return item

    def _normalize_thinking_options(self, options: list[dict[str, str]] | None) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for option in options or []:
            option_id = str(option.get("id", "")).strip()
            if not option_id or option_id in seen:
                continue
            seen.add(option_id)
            normalized.append(
                {
                    "id": option_id,
                    "label": str(option.get("label") or option_id).strip(),
                    "api_value": str(option.get("api_value", "")).strip(),
                }
            )
        return normalized

    def _model_id(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        return str((value or {}).get("id") or (value or {}).get("model") or "")

    def _model_config(self, provider_id: str, model: str) -> dict[str, Any]:
        provider = next((item for item in self.providers() if item["id"] == provider_id), None)
        if not provider:
            return {}
        model_id = model or provider.get("model", "")
        return next((item for item in provider.get("model_options", []) if self._model_id(item) == model_id), {})

    def _default_reasoning_parameter(self, provider_id: str) -> str:
        provider = provider_id.lower()
        if provider == "deepseek":
            return "deepseek_thinking"
        if provider == "mimo":
            return "anthropic_thinking_switch"
        if provider == "claude":
            return "anthropic_adaptive_thinking"
        if provider == "openai":
            return "openai_reasoning_effort"
        return "openai_reasoning_effort"

    def _thinking_api_value(self, thinking_level: str, options: list[dict[str, str]]) -> str:
        option = next((item for item in options if item.get("id") == thinking_level), None)
        if not option:
            return ""
        return option.get("api_value") or option.get("id", "")

    def _current_provider_id(self, env_values: dict[str, str]) -> str:
        row = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.default'").fetchone()
        config = loads(row["value_json"], {}) if row else {}
        return str(config.get("provider_id") or env_values.get("LANGDRILL_DEFAULT_PROVIDER") or "mimo")

    def _api_key_env_key(self, provider_id: str) -> str:
        clean = "".join(ch if ch.isalnum() else "_" for ch in provider_id.upper()).strip("_")
        return f"LANGDRILL_PROVIDER_API_KEY_{clean or 'CUSTOM'}"

    def _provider_api_key(self, provider_id: str, env_values: dict[str, str], current_provider_id: str | None = None) -> str:
        specific = env_values.get(self._api_key_env_key(provider_id), "")
        if specific:
            return specific
        if current_provider_id == provider_id:
            return env_values.get("LANGDRILL_PROVIDER_API_KEY", "")
        return ""

    def _read_env(self) -> dict[str, str]:
        env_path = PROJECT_ROOT / ".env"
        if not env_path.exists():
            return {}
        values: dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _read_process_env(self) -> dict[str, str]:
        keys = {
            "LANGDRILL_DEFAULT_PROVIDER",
            "LANGDRILL_DEFAULT_MODEL",
            "LANGDRILL_PROVIDER_BASE_URL",
            "LANGDRILL_PROVIDER_API_KEY",
            "LANGDRILL_PROVIDER_API_KEY_OPENAI",
            "LANGDRILL_PROVIDER_API_KEY_CLAUDE",
            "LANGDRILL_PROVIDER_API_KEY_DEEPSEEK",
            "LANGDRILL_PROVIDER_API_KEY_MIMO",
        }
        values: dict[str, str] = {}
        for key in keys:
            value = os.environ.get(key)
            if value and value.strip():
                values[key] = value
        for key, value in os.environ.items():
            if key.startswith("LANGDRILL_PROVIDER_API_KEY_") and value and value.strip():
                values[key] = value
        return values

    def _write_env(self, updates: dict[str, str], *, clear_empty: bool = False) -> None:
        env_path = PROJECT_ROOT / ".env"
        values = self._read_env()
        if clear_empty:
            values.update(updates)
        else:
            values.update({key: value for key, value in updates.items() if value != ""})
        ordered_keys = [
            "LANGDRILL_USER_DATA_DIR",
            "LANGDRILL_DB_PATH",
            "LANGDRILL_LOG_LEVEL",
            "LANGDRILL_USER_NAME",
            "LANGDRILL_DEFAULT_PROVIDER",
            "LANGDRILL_DEFAULT_MODEL",
            "LANGDRILL_PROVIDER_BASE_URL",
            "LANGDRILL_PROVIDER_API_KEY",
            "LANGDRILL_PROVIDER_API_KEY_OPENAI",
            "LANGDRILL_PROVIDER_API_KEY_CLAUDE",
            "LANGDRILL_PROVIDER_API_KEY_DEEPSEEK",
            "LANGDRILL_PROVIDER_API_KEY_MIMO",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "LOCAL_LLM_BASE_URL",
            "LOCAL_LLM_API_KEY",
            "LOCAL_LLM_MODEL",
            "LANGDRILL_SKILL_SOURCE",
        ]
        lines = []
        for key in ordered_keys:
            if key in values:
                lines.append(f"{key}={values[key]}")
        for key in sorted(set(values) - set(ordered_keys)):
            lines.append(f"{key}={values[key]}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        managed_keys = set(updates)
        if "LANGDRILL_PROVIDER_API_KEY" in values:
            managed_keys.add("LANGDRILL_PROVIDER_API_KEY")
        for key in managed_keys:
            value = values.get(key, "")
            if value:
                os.environ[key] = value
            elif clear_empty:
                os.environ.pop(key, None)
