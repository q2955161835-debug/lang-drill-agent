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

    def ensure_session(self, session_id: str | None, title_hint: str = "日常学习") -> str:
        if session_id:
            row = self.conn.execute("SELECT id FROM study_sessions WHERE id=?", (session_id,)).fetchone()
            if row:
                return session_id
        new_session_id = new_id("ses")
        title = title_hint.strip()[:18] or "日常学习"
        self.conn.execute(
            """
            INSERT INTO study_sessions (id, title, folder_date, daily_plan_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                new_session_id,
                title,
                today_str(),
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
        questions = self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status='answered' THEN 1 ELSE 0 END) AS done FROM questions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        attempts = self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(is_correct) AS correct FROM attempts WHERE session_id=?",
            (session_id,),
        ).fetchone()
        plan = loads(row["daily_plan_json"], {})
        total_attempts = attempts["total"] or 0
        return {
            "date": row["folder_date"],
            "title": row["title"],
            "status": row["status"],
            "plan": plan,
            "questions_total": questions["total"] or 0,
            "questions_done": questions["done"] or 0,
            "accuracy": round((attempts["correct"] or 0) / total_attempts, 2) if total_attempts else 0,
            "summary": row["summary"],
        }

    def list_sessions_by_date(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, title, folder_date, status, updated_at FROM study_sessions ORDER BY folder_date DESC, updated_at DESC"
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
            "title": "大学日语四级考试大纲 2023",
            "url": "https://www.china-cet.edu.cn/",
            "trusted_level": "official_or_exam_org",
        },
        {
            "exam_id": "cet4",
            "title": "全国大学英语四级考试大纲 2016",
            "url": "https://cet.neea.edu.cn/",
            "trusted_level": "official_or_exam_org",
        },
        {
            "exam_id": "cet6",
            "title": "全国大学英语六级考试大纲 2016",
            "url": "https://cet.neea.edu.cn/",
            "trusted_level": "official_or_exam_org",
        },
        {
            "exam_id": "gaokao-english",
            "title": "普通高中英语课程标准 2020",
            "url": "http://www.moe.gov.cn/",
            "trusted_level": "official",
        },
        {
            "exam_id": "gaokao-japanese",
            "title": "普通高中日语课程标准 2020",
            "url": "http://www.moe.gov.cn/",
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
                (id, exam_id, title, url, trusted_level, copyright_boundary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"src_{source['exam_id']}",
                    source["exam_id"],
                    source["title"],
                    source["url"],
                    source["trusted_level"],
                    "index_and_reference",
                ),
            )


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
            "LANGDRILL_DB_PATH",
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
