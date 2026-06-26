from __future__ import annotations

import os
import sqlite3
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
        if session_id:
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
            WHERE s.folder_date=? AND s.exam_id=?
            """,
            (scope["date"], scope["exam_id"]),
        ).fetchone()
        attempts = self.conn.execute(
            """
            SELECT COUNT(a.id) AS total, SUM(a.is_correct) AS correct
            FROM attempts a
            JOIN study_sessions s ON s.id = a.session_id
            WHERE s.folder_date=? AND s.exam_id=?
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
            SELECT id, title, folder_date, exam_id, status, updated_at
            FROM study_sessions
            WHERE exam_id=?
            ORDER BY folder_date DESC, updated_at DESC
            """,
            (profile.exam_id,),
        ).fetchall()
        return [dict(row) for row in rows]

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

    def _daily_scope(self, date: str, exam_id: str) -> dict[str, str]:
        profile = ProfileService(self.conn).get()
        row = self.conn.execute(
            """
            SELECT
              SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active_count,
              MAX(updated_at) AS updated_at
            FROM study_sessions
            WHERE folder_date=? AND exam_id=?
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
            WHERE folder_date=? AND exam_id=?
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
            WHERE exam_id=? AND DATE(created_at)=?
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
        "base_url": "",
        "model": "mock-tutor-v1",
        "model_options": ["mock-tutor-v1"],
    }
    PROVIDERS = [
        {
            "id": "deepseek",
            "label": "DeepSeek（深度求索）",
            "kind": "openai-compatible",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "model_options": ["deepseek-chat", "deepseek-reasoner"],
        },
        {
            "id": "mimo",
            "label": "Xiaomi MiMo（小米 MiMo）",
            "kind": "openai-compatible",
            "base_url": "https://api.xiaomimimo.com/v1",
            "model": "mimo-v2.5-pro",
            "model_options": ["mimo-v2.5-pro", "mimo-v2-pro"],
        },
        {
            "id": "custom",
            "label": "Custom OpenAI-compatible（自定义 OpenAI 兼容）",
            "kind": "openai-compatible",
            "base_url": "",
            "model": "",
            "model_options": [],
        },
    ]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def providers(self) -> list[dict[str, Any]]:
        row = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.custom_providers'").fetchone()
        customs = loads(row["value_json"], []) if row else []
        
        row_ov = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.provider_overrides'").fetchone()
        overrides = loads(row_ov["value_json"], {}) if row_ov else {}
        
        base_providers = [dict(p) for p in self.PROVIDERS]
        builtin = [provider for provider in base_providers if provider["id"] != "custom"]
        custom_template = next(provider for provider in base_providers if provider["id"] == "custom")
        all_providers = builtin + customs + [custom_template]
        for p in all_providers:
            ov = overrides.get(p["id"])
            if ov:
                p["base_url"] = ov.get("base_url", p["base_url"])
                added_models = ov.get("added_models", [])
                if added_models:
                    opts = p.get("model_options", []).copy()
                    for m in added_models:
                        if m not in opts:
                            opts.append(m)
                    p["model_options"] = opts
        return all_providers

    def current(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key='model.default'"
        ).fetchone()
        config = loads(row["value_json"], {}) if row else {}
        env_values = {**self._read_env(), **self._read_process_env()}
        provider_id = config.get("provider_id") or env_values.get("LANGDRILL_DEFAULT_PROVIDER") or "mock"
        provider = self.provider_by_id(provider_id)
        if provider_id == "mock":
            return {
                "provider_id": "mock",
                "base_url": "",
                "model": config.get("model") or provider.get("model", "mock-tutor-v1"),
                "has_api_key": False,
            }
        return {
            "provider_id": provider_id,
            "base_url": config.get("base_url")
            or env_values.get("LANGDRILL_PROVIDER_BASE_URL")
            or provider.get("base_url", ""),
            "model": config.get("model")
            or env_values.get("LANGDRILL_DEFAULT_MODEL")
            or provider.get("model", ""),
            "has_api_key": bool(env_values.get("LANGDRILL_PROVIDER_API_KEY", "")),
        }

    def current_with_secret(self) -> dict[str, Any]:
        config = self.current()
        if config.get("provider_id") == "mock":
            config["api_key"] = ""
            return config
        env_values = {**self._read_env(), **self._read_process_env()}
        config["api_key"] = env_values.get("LANGDRILL_PROVIDER_API_KEY", "")
        return config

    def provider_by_id(self, provider_id: str) -> dict[str, Any]:
        if provider_id == "mock":
            return dict(self.MOCK_PROVIDER)
        all_providers = self.providers()
        return next((item for item in all_providers if item["id"] == provider_id), all_providers[0])

    def save(self, provider_id: str, base_url: str, model: str, api_key: str = "") -> dict[str, Any]:
        provider = self.provider_by_id(provider_id)
        clean_base_url = (base_url or provider.get("base_url", "")).strip()
        clean_model = (model or provider.get("model", "")).strip()
        
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
                    }
                ),
            ),
        )

        # Save overrides so this provider remembers the base_url and added models
        row_ov = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.provider_overrides'").fetchone()
        overrides = loads(row_ov["value_json"], {}) if row_ov else {}
        ov = overrides.setdefault(provider_id, {"added_models": []})
        ov["base_url"] = clean_base_url
        if clean_model and clean_model not in provider.get("model_options", []) and clean_model not in ov["added_models"]:
            ov["added_models"].append(clean_model)

        self.conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value_json, updated_at) VALUES ('model.provider_overrides', ?, CURRENT_TIMESTAMP)",
            (dumps(overrides),),
        )
        self._write_env(
            {
                "LANGDRILL_DEFAULT_PROVIDER": provider_id,
                "LANGDRILL_DEFAULT_MODEL": clean_model,
                "LANGDRILL_PROVIDER_BASE_URL": clean_base_url,
                **({"LANGDRILL_PROVIDER_API_KEY": api_key.strip()} if api_key else {}),
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
                "LANGDRILL_PROVIDER_BASE_URL": "https://api.xiaomimimo.com/v1",
            }
        )
        return self.current()

    def add_custom_provider(self, name: str, base_url: str, default_model: str) -> None:
        row = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.custom_providers'").fetchone()
        customs = loads(row["value_json"], []) if row else []
        new_id = f"custom_{len(customs) + 1}_{int(datetime.now().timestamp())}"
        customs.append({
            "id": new_id,
            "label": f"{name}（自定义）",
            "kind": "openai-compatible",
            "base_url": base_url.strip(),
            "model": default_model.strip(),
            "model_options": [default_model.strip()],
        })
        self.conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value_json, updated_at) VALUES ('model.custom_providers', ?, CURRENT_TIMESTAMP)",
            (dumps(customs),),
        )

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
        }
        values: dict[str, str] = {}
        for key in keys:
            value = os.environ.get(key)
            if value and value.strip():
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
