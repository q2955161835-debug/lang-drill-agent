from __future__ import annotations

import html
import logging
import os
import re
import shutil
import sqlite3
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from .config import PROJECT_ROOT
from .models import Question, UserProfile
from .paper_assets import (
    ensure_exam_paper_dirs,
    extract_text_from_file,
    paper_slug,
    parse_paper_text,
    relative_display_path,
    source_manifest_text,
    write_parsed_json,
)
from .utils import dumps, loads, new_id, normalize_api_key, today_str, validate_http_header_value


logger = logging.getLogger(__name__)


class AgentSettingsPermissionService:
    SETTINGS_KEY = "agent.settings.permissions"
    FEATURES = [
        {
            "id": "screenshot_import",
            "label": "截图导入与词表入库",
            "description": "允许会话 Agent 触发截图/文件词表解析，把确认后的单词写入学习库并创建练习会话。",
            "sensitive": False,
            "default_enabled": True,
        },
        {
            "id": "learning_database",
            "label": "单词、题目与作答数据库",
            "description": "允许会话 Agent 通过正式学习流程创建知识项、题目、作答记录和掌握度统计。",
            "sensitive": False,
            "default_enabled": True,
        },
        {
            "id": "past_paper_import",
            "label": "历年真题导入与题型",
            "description": "允许会话 Agent 解析试卷信息，并在用户确认后填入真题导入表单。",
            "sensitive": False,
            "default_enabled": True,
        },
        {
            "id": "web_search_import",
            "label": "联网搜索导入",
            "description": "允许会话 Agent 使用无需个人 API Key 的本地 Skills 生成真题来源搜索索引和可核验来源。",
            "sensitive": False,
            "default_enabled": True,
        },
        {
            "id": "profile_exam",
            "label": "考试与学习目标",
            "description": "允许会话 Agent 按用户确认的目标调整考试、截止时间和学习背景草稿。",
            "sensitive": False,
            "default_enabled": True,
        },
        {
            "id": "context_settings",
            "label": "上下文容量",
            "description": "允许会话 Agent 帮助调整上下文容量上限和压缩相关设置。",
            "sensitive": False,
            "default_enabled": True,
        },
        {
            "id": "skills",
            "label": "Skills 功能",
            "description": "允许会话 Agent 读取已安装的本地 Skills 能力，并优先使用无需密钥的技能辅助搜索和导入。",
            "sensitive": False,
            "default_enabled": True,
        },
        {
            "id": "model_config",
            "label": "模型供应商与默认模型",
            "description": "允许会话 Agent 帮助填写模型供应商、模型名、Base URL（基础网址）和能力开关。",
            "sensitive": True,
            "default_enabled": False,
        },
        {
            "id": "data_paths",
            "label": "题目数据库目录",
            "description": "允许会话 Agent 帮助填写题目数据库目录迁移设置；迁移前仍需用户确认。",
            "sensitive": True,
            "default_enabled": False,
        },
        {
            "id": "mineru_config",
            "label": "MinerU token",
            "description": "允许会话 Agent 帮助打开 MinerU 配置项；token 明文仍只能由用户输入。",
            "sensitive": True,
            "default_enabled": False,
        },
    ]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def status(self) -> dict[str, Any]:
        enabled_ids = set(self._enabled_feature_ids())
        features = [
            {
                **feature,
                "enabled": feature["id"] in enabled_ids,
            }
            for feature in self.FEATURES
        ]
        return {
            "features": features,
            "enabled_feature_ids": [feature["id"] for feature in self.FEATURES if feature["id"] in enabled_ids],
            "groups": [
                {
                    "id": "default_enabled",
                    "label": "默认开启的能力权限",
                    "feature_ids": [
                        feature["id"]
                        for feature in self.FEATURES
                        if not bool(feature.get("sensitive"))
                    ],
                },
                {
                    "id": "sensitive",
                    "label": "敏感设置权限",
                    "feature_ids": [
                        feature["id"]
                        for feature in self.FEATURES
                        if bool(feature.get("sensitive"))
                    ],
                },
            ],
        }

    def save(self, enabled_feature_ids: list[str]) -> dict[str, Any]:
        allowed = {feature["id"] for feature in self.FEATURES}
        clean_ids = []
        for feature_id in enabled_feature_ids:
            clean_id = str(feature_id).strip()
            if clean_id in allowed and clean_id not in clean_ids:
                clean_ids.append(clean_id)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (self.SETTINGS_KEY, dumps({"enabled_feature_ids": clean_ids})),
        )
        return self.status()

    def is_enabled(self, feature_id: str) -> bool:
        return feature_id in set(self._enabled_feature_ids())

    def _enabled_feature_ids(self) -> list[str]:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (self.SETTINGS_KEY,),
        ).fetchone()
        if not row:
            return [
                str(feature["id"])
                for feature in self.FEATURES
                if bool(feature.get("default_enabled"))
            ]
        data = loads(row["value_json"], {})
        return [str(item) for item in data.get("enabled_feature_ids", []) if str(item).strip()]


class SkillRegistryService:
    DEFAULT_SEARCH_ROOT = Path("D:/2Folder/skills")
    RECOMMENDED_WEB_SEARCH_SKILL = {
        "id": "multi-search-engine",
        "name": "multi-search-engine",
        "label": "Multi Search Engine",
        "description": "生成可审计的多搜索引擎查询 URL，支持中英文搜索、站点限定、文件类型和时间范围；不需要个人 API Key 或 token。",
        "homepage": "https://clawhub.com/skills/multi-search-engine",
        "requires_api_key": False,
        "requires_token": False,
        "permission_feature_id": "web_search_import",
        "reason": "适合为真题、考纲和来源网站生成可核验搜索入口，避免绑定需要个人申请的搜索 API。",
    }

    def __init__(self, skills_roots: list[Path] | None = None):
        env_roots = [
            Path(item.strip())
            for item in os.getenv("LANGDRILL_SKILLS_ROOTS", "").split(os.pathsep)
            if item.strip()
        ]
        roots = skills_roots or [
            *env_roots,
            self.DEFAULT_SEARCH_ROOT,
            Path.home() / ".agents" / "skills",
            Path.home() / ".codex" / "skills",
        ]
        self.skills_roots = self._dedupe_roots(roots)

    def status(self) -> dict[str, Any]:
        installed = self.installed_skills()
        web_search_skill = next(
            (skill for skill in installed if skill["id"] == self.RECOMMENDED_WEB_SEARCH_SKILL["id"]),
            None,
        )
        if web_search_skill:
            web_search_skill = {
                **web_search_skill,
                **self.RECOMMENDED_WEB_SEARCH_SKILL,
                "path": web_search_skill.get("path", ""),
                "skill_file": web_search_skill.get("skill_file", ""),
                "requires_api_key": False,
                "requires_token": False,
                "installed": True,
            }
        else:
            web_search_skill = {
                **self.RECOMMENDED_WEB_SEARCH_SKILL,
                "installed": False,
                "path": str(self.DEFAULT_SEARCH_ROOT / self.RECOMMENDED_WEB_SEARCH_SKILL["id"]),
            }
        no_key_skill_ids = [
            str(skill["id"])
            for skill in installed
            if not bool(skill.get("requires_api_key")) and not bool(skill.get("requires_token"))
        ]
        return {
            "skills_roots": [str(path) for path in self.skills_roots],
            "installed": installed,
            "installed_count": len(installed),
            "no_key_skill_ids": no_key_skill_ids,
            "web_search_skill": web_search_skill,
            "permission_feature_id": "skills",
            "web_search_permission_feature_id": "web_search_import",
            "message": "已优先选择无需个人 API Key 或 token 的 multi-search-engine 作为联网搜索导入技能。",
        }

    def installed_skills(self) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        seen: set[str] = set()
        for root in self.skills_roots:
            if not root.exists() or not root.is_dir():
                continue
            for skill_dir in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                if not skill_dir.is_dir():
                    continue
                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue
                skill = self._skill_from_file(skill_file)
                if skill["id"] in seen:
                    continue
                seen.add(skill["id"])
                skills.append(skill)
        return skills

    def _skill_from_file(self, skill_file: Path) -> dict[str, Any]:
        text = skill_file.read_text(encoding="utf-8", errors="ignore")
        metadata = self._frontmatter(text)
        skill_id = str(metadata.get("name") or skill_file.parent.name).strip() or skill_file.parent.name
        description = str(metadata.get("description") or "").strip()
        lower = text.lower()
        no_key = (
            "does not require api keys" in lower
            or "no api keys" in lower
            or "无需" in text and ("api key" in lower or "token" in lower)
            or "不需要" in text and ("api key" in lower or "token" in lower)
        )
        requires_secret = not no_key and (
            "requires api key" in lower
            or "api key required" in lower
            or "requires token" in lower
            or "token required" in lower
        )
        return {
            "id": skill_id,
            "name": skill_id,
            "label": skill_id.replace("-", " ").title(),
            "description": description,
            "path": str(skill_file.parent),
            "skill_file": str(skill_file),
            "homepage": str(metadata.get("homepage") or ""),
            "requires_api_key": bool(requires_secret),
            "requires_token": bool(requires_secret),
            "installed": True,
        }

    def _frontmatter(self, text: str) -> dict[str, str]:
        if not text.startswith("---"):
            return {}
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}
        metadata: dict[str, str] = {}
        for line in parts[1].splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            clean_key = key.strip()
            clean_value = value.strip().strip('"').strip("'")
            if clean_key in {"name", "description", "homepage"}:
                metadata[clean_key] = clean_value
        return metadata

    def _dedupe_roots(self, roots: list[Path]) -> list[Path]:
        deduped: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root.expanduser()).lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(root.expanduser())
        return deduped


class PastPaperDraftService:
    QUESTION_TYPE_HINTS = [
        ("listening", "听力理解", ("听力", "listening", "short conversation", "long conversation", "lecture")),
        ("reading", "阅读理解", ("阅读", "reading", "passage", "comprehension", "段落匹配", "仔细阅读")),
        ("translation", "翻译", ("翻译", "translation", "translate")),
        ("writing", "写作", ("写作", "writing", "essay", "composition")),
        ("cloze", "完形填空", ("完形", "cloze", "fill in the blank", "blank")),
        ("vocabulary", "词汇", ("词汇", "vocabulary", "word choice")),
        ("grammar", "语法", ("语法", "grammar")),
        ("speaking", "口语", ("口语", "speaking", "oral")),
    ]

    TITLE_KEYWORDS = ("真题", "试卷", "样卷", "模拟", "CET", "IELTS", "TOEFL", "高考", "四级", "六级", "Sample", "Test")

    def draft(
        self,
        *,
        exam_id: str,
        title: str = "",
        year: int | None = None,
        source_url: str = "",
        local_path: str = "",
        summary: str = "",
        question_types: list[str] | None = None,
        raw_text: str = "",
        filename: str = "",
        model_hint: dict[str, Any] | None = None,
        include_raw_text: bool = True,
    ) -> dict[str, Any]:
        hint = model_hint or {}
        clean_raw = raw_text.strip()
        clean_title = self._first_text(title, hint.get("title")) or self._infer_title(clean_raw, filename)
        clean_year = self._coerce_year(year if year is not None else hint.get("year")) or self._infer_year(
            " ".join(str(item or "") for item in [clean_title, filename, source_url, local_path, clean_raw[:2000]])
        )
        clean_source = self._first_text(source_url, hint.get("source_url"))
        clean_local_path = self._first_text(local_path, hint.get("local_path"), filename)
        clean_types = self._normalize_question_types([*(question_types or []), *self._hint_types(hint)])
        if not clean_types:
            clean_types = self._detect_question_types(clean_raw)
        clean_summary = self._first_text(summary, hint.get("summary")) or self._infer_summary(
            clean_raw,
            title=clean_title,
            year=clean_year,
            question_types=clean_types,
        )
        return {
            "exam_id": exam_id,
            "title": clean_title,
            "year": clean_year,
            "source_url": clean_source,
            "local_path": clean_local_path,
            "question_types": clean_types,
            "summary": clean_summary,
            "raw_text": clean_raw if include_raw_text else "",
        }

    def _first_text(self, *values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _hint_types(self, hint: dict[str, Any]) -> list[str]:
        value = hint.get("question_types") or hint.get("types") or []
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[，,\n/;；]", value) if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _normalize_question_types(self, values: list[str]) -> list[str]:
        clean: list[str] = []
        for value in values:
            text = re.sub(r"\s+", " ", str(value or "")).strip(" -:：，,;；")
            if not text:
                continue
            mapped = self._map_question_type(text) or text
            if mapped not in clean:
                clean.append(mapped)
        return clean[:12]

    def _map_question_type(self, text: str) -> str:
        lower = text.lower()
        for type_id, label, hints in self.QUESTION_TYPE_HINTS:
            if lower == type_id or text == label:
                return type_id
            if any(hint.lower() in lower for hint in hints):
                return type_id
        return ""

    def _detect_question_types(self, raw_text: str) -> list[str]:
        text = raw_text.lower()
        detected = []
        for type_id, _label, hints in self.QUESTION_TYPE_HINTS:
            if any(hint.lower() in text for hint in hints) and type_id not in detected:
                detected.append(type_id)
        return detected[:12]

    def _infer_title(self, raw_text: str, filename: str) -> str:
        for line in raw_text.splitlines()[:80]:
            clean = re.sub(r"^[#>\-\s]+", "", line).strip()
            clean = re.sub(r"\s+", " ", clean)
            if 4 <= len(clean) <= 90 and any(keyword.lower() in clean.lower() for keyword in self.TITLE_KEYWORDS):
                return clean
        if filename:
            return Path(filename).stem.strip() or filename.strip()
        return ""

    def _infer_year(self, text: str) -> int | None:
        match = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", text)
        return int(match.group(1)) if match else None

    def _coerce_year(self, value: Any) -> int | None:
        try:
            year = int(value)
        except (TypeError, ValueError):
            return None
        if 1900 <= year <= 2100:
            return year
        return None

    def _infer_summary(self, raw_text: str, *, title: str, year: int | None, question_types: list[str]) -> str:
        parts = []
        if title:
            parts.append(f"试卷：{title}")
        if year:
            parts.append(f"年份：{year}")
        if question_types:
            parts.append(f"检测到题型：{'、'.join(question_types)}")
        excerpt_lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in raw_text.splitlines()
            if re.sub(r"\s+", " ", line).strip()
        ][:8]
        excerpt = "；".join(excerpt_lines)
        if excerpt:
            parts.append(f"文本摘要：{excerpt[:260]}")
        return "；".join(parts)[:420]


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
            "SELECT id, role, content, payload_json, created_at FROM messages WHERE session_id=? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        messages: list[dict[str, Any]] = []
        for row in rows:
            message = dict(row)
            message["payload"] = loads(message.pop("payload_json"), {})
            messages.append(message)
        return messages

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
        progress = self.question_progress(str(payload["session_id"]))
        payload["set_total"] = progress["total"]
        payload["set_done"] = progress["done"]
        return payload


class SourceService:
    COMMON_SYLLABUS_SOURCES = [
        {
            "exam_id": "cft4",
            "title": "全国大学法语四级考试大纲（2023版）",
            "year": 2023,
            "url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "trusted_level": "official_or_exam_org",
        },
        {
            "exam_id": "cjt4",
            "title": "全国大学日语四、六级考试大纲（2024年启用）",
            "year": 2024,
            "url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "trusted_level": "official_or_exam_org",
        },
        {
            "exam_id": "cjt6",
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
    CET_SYLLABUS_PAGE = "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm"
    CET_SYLLABUS_MATCHERS = {
        "cet4": {"required": ["英语"], "level_any": ["四、六级", "四级"]},
        "cet6": {"required": ["英语"], "level_any": ["四、六级", "六级"]},
        "cft4": {"required": ["法语"], "level_any": ["四级"]},
        "cjt4": {"required": ["日语"], "level_any": ["四、六级", "四级"]},
        "cjt6": {"required": ["日语"], "level_any": ["四、六级", "六级"]},
    }
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
            "id": "cet6",
            "name": "英语六级",
            "target_language": "英语",
            "official_url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "default_year": 2016,
            "description": "大学英语六级，按六级题型和难度组织。",
        },
        {
            "id": "cft4",
            "name": "法语四级",
            "target_language": "法语",
            "official_url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "default_year": 2023,
            "description": "大学法语四级，官方 2023 版考纲。",
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
            "id": "cjt6",
            "name": "日语六级",
            "target_language": "日语",
            "official_url": "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
            "default_year": 2024,
            "description": "大学日语六级，按更高难度日语题型和表达能力组织。",
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
        latest = sources[0] if sources else self._default_source(target_exam)
        selected_id = self._selected_source_id(target_exam)
        selected = next((item for item in sources if item.get("id") == selected_id), None)
        current = selected or latest
        selected_id = str(current.get("id", ""))
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
        official_candidate = self._latest_matching_official_syllabus(exam_id, option)
        default_year = official_candidate["year"] if official_candidate else option.get("default_year")
        default_title = (
            official_candidate["title"]
            if official_candidate
            else option["name"] + f"考纲 {default_year}"
        )
        default_url = (
            official_candidate["url"]
            if official_candidate
            else option.get("official_url", "")
        )
        latest = self.status(exam_id)
        current_year = latest.get("current_year")
        current_year_int = self._int_year(current_year)
        default_year_int = self._int_year(default_year)
        changed = bool(
            default_year_int and (not current_year_int or current_year_int < default_year_int)
        )
        if changed:
            source_id = self._source_id_for_year(latest["sources"], default_year)
            source_id = source_id or f"src_{exam_id}_{default_year}"
            self.conn.execute(
                """
                INSERT OR IGNORE INTO syllabus_sources
                (id, exam_id, title, year, url, trusted_level, copyright_boundary, is_latest_checked, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, 'index_and_reference', 1, CURRENT_TIMESTAMP)
                """,
                (
                    source_id,
                    exam_id,
                    default_title,
                    default_year,
                    default_url,
                    "official_or_exam_org" if official_candidate else "official",
                ),
            )
            self.conn.execute(
                """
                UPDATE syllabus_sources
                SET title=?, year=?, url=?, trusted_level=?,
                    is_latest_checked=1, checked_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    default_title,
                    default_year,
                    default_url,
                    "official_or_exam_org" if official_candidate else "official",
                    source_id,
                ),
            )
            self._select_source(exam_id, source_id)
            return {
                "changed": True,
                "message": f"已录入 {default_year} 年考纲，旧年份仍保留在可选考纲中。",
                "status": self.status(exam_id),
            }
        if latest["sources"]:
            source_id = (
                self._source_id_for_year(latest["sources"], default_year)
                or latest["sources"][0]["id"]
            )
            if official_candidate and default_year:
                self.conn.execute(
                    """
                    UPDATE syllabus_sources
                    SET title=?, url=CASE WHEN ?='' THEN url ELSE ? END
                    WHERE id=?
                    """,
                    (default_title, default_url, default_url, source_id),
                )
            self.conn.execute(
                """
                UPDATE syllabus_sources
                SET is_latest_checked=1, checked_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (source_id,),
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

    @staticmethod
    def parse_official_syllabus_candidates(
        page_html: str, source_url: str = ""
    ) -> list[dict[str, Any]]:
        text = html.unescape(page_html or "")
        text = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", "\n", text)
        text = re.sub(r"(?is)<br\s*/?>|</p>|</li>|</a>|</div>|</tr>|</td>", "\n", text)
        text = re.sub(r"(?is)<[^>]+>", "", text)
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for line in text.splitlines():
            title = re.sub(r"\s+", " ", line).strip(" \u3000")
            if "全国大学" not in title or "考试大纲" not in title:
                continue
            title = SyllabusService._clean_official_syllabus_title(title)
            year_match = re.search(r"(19\d{2}|20\d{2})", title)
            if not year_match:
                continue
            year = int(year_match.group(1))
            key = (title, year)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({"title": title, "year": year, "url": source_url})
        return candidates

    @staticmethod
    def _clean_official_syllabus_title(title: str) -> str:
        starts = [index for token in ("《全国大学", "全国大学") if (index := title.find(token)) >= 0]
        if starts:
            title = title[min(starts) :]
        for token in (" 《全国大学", " 全国大学"):
            next_index = title.find(token, 1)
            if next_index > 0:
                title = title[:next_index]
        return title.strip(" \u3000")

    def _latest_matching_official_syllabus(
        self, exam_id: str, option: dict[str, Any]
    ) -> dict[str, Any] | None:
        official_url = str(option.get("official_url", ""))
        if official_url != self.CET_SYLLABUS_PAGE or exam_id not in self.CET_SYLLABUS_MATCHERS:
            return None
        candidates = self._fetch_official_syllabus_candidates(official_url)
        matched = [
            item for item in candidates if self._matches_official_syllabus(exam_id, item["title"])
        ]
        return max(matched, key=lambda item: int(item["year"]), default=None)

    def _fetch_official_syllabus_candidates(self, official_url: str) -> list[dict[str, Any]]:
        try:
            response = httpx.get(official_url, timeout=8, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("failed to fetch official syllabus page", exc_info=True)
            return []
        return self.parse_official_syllabus_candidates(response.text, official_url)

    def _matches_official_syllabus(self, exam_id: str, title: str) -> bool:
        matcher = self.CET_SYLLABUS_MATCHERS.get(exam_id)
        if not matcher:
            return False
        required = matcher.get("required", [])
        level_any = matcher.get("level_any", [])
        return all(token in title for token in required) and any(token in title for token in level_any)

    @staticmethod
    def _source_id_for_year(sources: list[dict[str, Any]], year: Any) -> str:
        year_int = SyllabusService._int_year(year)
        if not year_int:
            return ""
        for source in sources:
            if SyllabusService._int_year(source.get("year")) == year_int:
                return str(source.get("id", ""))
        return ""

    @staticmethod
    def _int_year(year: Any) -> int | None:
        try:
            return int(year)
        except (TypeError, ValueError):
            return None

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


class PastPaperService:
    DEFAULT_RECENT_YEARS = [2025, 2024, 2023]
    EXAM_PAPER_SOURCES = {
        "cet4": {
            "source_website": "https://cet.neea.edu.cn/",
            "title_prefix": "大学英语四级",
            "description": "CET-4（大学英语四级）真题按听力、阅读、翻译和写作组织。",
            "question_types": [
                {"id": "listening", "label": "听力理解", "description": "短篇新闻、长对话和听力篇章。"},
                {"id": "reading", "label": "阅读理解", "description": "选词填空、长篇匹配和仔细阅读。"},
                {"id": "translation", "label": "汉译英翻译", "description": "段落翻译，偏中国文化与社会话题。"},
                {"id": "writing", "label": "短文写作", "description": "议论文、应用文或图表类写作。"},
                {"id": "context_vocabulary", "label": "语境词汇", "description": "从真题语境抽取搭配、词义和近义辨析。"},
            ],
        },
        "cet6": {
            "source_website": "https://cet.neea.edu.cn/",
            "title_prefix": "大学英语六级",
            "description": "CET-6（大学英语六级）真题强调更高难度阅读、听力和写译表达。",
            "question_types": [
                {"id": "listening", "label": "听力理解", "description": "讲座、长对话和篇章理解。"},
                {"id": "reading", "label": "阅读理解", "description": "选词填空、信息匹配和仔细阅读。"},
                {"id": "translation", "label": "汉译英翻译", "description": "段落翻译，重视准确表达。"},
                {"id": "writing", "label": "短文写作", "description": "观点论证、问题解决或图表表达。"},
                {"id": "context_vocabulary", "label": "语境词汇", "description": "近义辨析、搭配和篇章词义。"},
            ],
        },
        "cft4": {
            "source_website": "https://cet.neea.edu.cn/",
            "title_prefix": "大学法语四级",
            "description": "CFT-4（大学法语四级）按听力、阅读、语法词汇、翻译和写作组织。",
            "question_types": [
                {"id": "listening", "label": "听力理解", "description": "对话、短文和信息判断。"},
                {"id": "reading", "label": "阅读理解", "description": "篇章理解、细节定位和推断。"},
                {"id": "grammar_vocabulary", "label": "语法词汇", "description": "词形、搭配、句法和语义辨析。"},
                {"id": "translation", "label": "翻译表达", "description": "法汉互译和句意转换。"},
                {"id": "writing", "label": "写作表达", "description": "短文、应用文或开放表达。"},
            ],
        },
        "cjt4": {
            "source_website": "https://cet.neea.edu.cn/",
            "title_prefix": "大学日语四级",
            "description": "CJT-4（大学日语四级）按文字词汇、语法、阅读、翻译和听力组织。",
            "question_types": [
                {"id": "vocabulary", "label": "文字词汇", "description": "假名、汉字、词义和用法。"},
                {"id": "grammar", "label": "语法结构", "description": "助词、句型、活用和固定表达。"},
                {"id": "reading", "label": "阅读理解", "description": "短文理解和信息推断。"},
                {"id": "translation", "label": "翻译表达", "description": "中日互译和句意转换。"},
                {"id": "listening", "label": "听力理解", "description": "对话和短篇听力。"},
            ],
        },
        "cjt6": {
            "source_website": "https://cet.neea.edu.cn/",
            "title_prefix": "大学日语六级",
            "description": "CJT-6（大学日语六级）按高阶文字词汇、语法、阅读、翻译和听力组织。",
            "question_types": [
                {"id": "vocabulary", "label": "文字词汇", "description": "高阶汉字、词义辨析和惯用表达。"},
                {"id": "grammar", "label": "语法结构", "description": "复合句、敬语、助词和高级句型。"},
                {"id": "reading", "label": "阅读理解", "description": "长文理解、主旨推断和信息整合。"},
                {"id": "translation", "label": "翻译表达", "description": "中日互译、语体转换和自然表达。"},
                {"id": "listening", "label": "听力理解", "description": "较长对话、讲述和信息判断。"},
            ],
        },
        "ielts": {
            "source_website": "https://ielts.org/take-a-test/preparation",
            "title_prefix": "雅思学术类",
            "description": "IELTS（雅思）公开样题按听、说、读、写四科参考，不默认保存完整真题原文。",
            "question_types": [
                {"id": "listening", "label": "Listening", "description": "听力信息定位、拼写和匹配。"},
                {"id": "reading", "label": "Reading", "description": "判断、匹配、填空和主旨题。"},
                {"id": "writing_task1", "label": "Writing Task 1", "description": "图表、流程或地图描述。"},
                {"id": "writing_task2", "label": "Writing Task 2", "description": "议论文任务。"},
                {"id": "speaking", "label": "Speaking", "description": "Part 1-3 口语问答。"},
            ],
        },
        "toefl": {
            "source_website": "https://www.ets.org/toefl/test-takers/ibt/prepare.html",
            "title_prefix": "TOEFL iBT",
            "description": "TOEFL iBT（托福网考）按阅读、听力、口语和写作综合任务组织。",
            "question_types": [
                {"id": "reading", "label": "Reading", "description": "学术文章理解、词汇和推断。"},
                {"id": "listening", "label": "Listening", "description": "讲座和校园对话。"},
                {"id": "speaking", "label": "Speaking", "description": "独立与综合口语。"},
                {"id": "writing", "label": "Writing", "description": "综合写作和学术讨论写作。"},
            ],
        },
        "gaokao-english": {
            "source_website": "https://www.moe.gov.cn/",
            "title_prefix": "高考英语",
            "description": "高考英语按地区卷型差异参考，默认只保留题型结构和来源索引。",
            "question_types": [
                {"id": "listening", "label": "听力", "description": "短对话、长对话和独白。"},
                {"id": "reading", "label": "阅读理解", "description": "细节、推断、主旨和词义猜测。"},
                {"id": "cloze", "label": "完形填空", "description": "篇章语义、搭配和逻辑衔接。"},
                {"id": "grammar_fill", "label": "语法填空", "description": "词形、时态、非谓语和从句。"},
                {"id": "writing", "label": "写作", "description": "应用文、读后续写或概要写作。"},
            ],
        },
        "custom": {
            "source_website": "",
            "title_prefix": "自定义考试",
            "description": "自定义考试需要用户补充来源、样卷和题型。",
            "question_types": [
                {"id": "vocabulary", "label": "词汇", "description": "词义、搭配和语境用法。"},
                {"id": "grammar", "label": "语法", "description": "句法结构和表达规则。"},
                {"id": "reading", "label": "阅读", "description": "短文理解、信息定位和推断。"},
                {"id": "writing", "label": "写作", "description": "短文、应用文或开放表达。"},
                {"id": "translation", "label": "翻译", "description": "双语转换或句意改写。"},
            ],
        },
    }

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def status(self, exam_id: str | None = None) -> dict[str, Any]:
        profile = ProfileService(self.conn).get()
        target_exam = exam_id or profile.exam_id
        self.seed_default_papers(target_exam)
        papers = self._papers(target_exam)
        selected_ids = self._selected_paper_ids(target_exam)
        if not selected_ids:
            selected_ids = [paper["id"] for paper in papers[:3]]
        selected_set = set(selected_ids)
        current_papers = [paper for paper in papers if paper["id"] in selected_set]
        source_info = self._source_info(target_exam)
        question_types = self._question_type_options(target_exam)
        enabled_ids = self._enabled_question_type_ids(target_exam)
        if not enabled_ids:
            enabled_ids = [item["id"] for item in question_types]
        return {
            "exam_id": target_exam,
            "description": source_info["description"],
            "source_website": source_info["source_website"],
            "papers": papers,
            "selected_paper_ids": selected_ids,
            "current_papers": current_papers,
            "question_types": question_types,
            "enabled_question_type_ids": enabled_ids,
        }

    def generation_context(self, exam_id: str) -> dict[str, Any]:
        status = self.status(exam_id)
        enabled = set(status["enabled_question_type_ids"])
        question_types = [item for item in status["question_types"] if item["id"] in enabled]
        papers = []
        for paper in status["current_papers"]:
            metadata = paper.get("metadata") or loads(paper.get("metadata_json", "{}"), {})
            parsed = metadata.get("parsed", {})
            papers.append(
                {
                    "id": paper["id"],
                    "title": paper["title"],
                    "year": paper["year"],
                    "source_url": paper["source_url"],
                    "local_path": paper["local_path"],
                    "trusted_level": paper["trusted_level"],
                    "copyright_boundary": paper["copyright_boundary"],
                    "summary": metadata.get("summary", ""),
                    "question_types": metadata.get("question_types", []),
                    "raw_path": metadata.get("raw_path", paper.get("local_path", "")),
                    "parsed_path": metadata.get("parsed_path", ""),
                    "parse_status": metadata.get("parse_status", ""),
                    "sections": parsed.get("sections", [])[:8] if isinstance(parsed, dict) else [],
                    "usable_excerpts": parsed.get("usable_excerpts", [])[:12] if isinstance(parsed, dict) else [],
                }
            )
        return {
            "source_website": status["source_website"],
            "selected_papers": papers,
            "enabled_question_types": question_types,
            "rules": [
                "生成题目时必须参考 selected_papers 的年份、来源、题型和风格摘要。",
                "source_refs 至少写入一个当前选中真题试卷 id/year/title/source_url。",
                "禁止复刻或长段引用完整真题原文；只做题型、难度、主题和风格参考。",
                "只生成 enabled_question_types 中已勾选的题型；未勾选题型不得进入本轮题组。",
            ],
        }

    def seed_default_papers(self, exam_id: str) -> None:
        source_info = self._source_info(exam_id)
        question_type_ids = [item["id"] for item in self._question_type_options(exam_id)]
        dirs = ensure_exam_paper_dirs(exam_id)
        for year in self.DEFAULT_RECENT_YEARS:
            paper_id = f"paper_{exam_id}_{year}"
            title = f"{source_info['title_prefix']} {year} 年真题参考索引"
            summary = f"默认近三年真题索引，用于参考 {source_info['title_prefix']} 的题型结构、难度和常见主题。"
            slug = paper_slug(exam_id, title, year, paper_id)
            raw_path = dirs["raw"] / f"{slug}.md"
            parsed_path = dirs["parsed"] / f"{slug}.json"
            manifest = source_manifest_text(
                exam_id=exam_id,
                title=title,
                year=year,
                source_url=source_info["source_website"],
                summary=summary,
                question_types=question_type_ids,
            )
            if not raw_path.exists():
                raw_path.write_text(manifest, encoding="utf-8")
            if not parsed_path.exists():
                parsed_payload = parse_paper_text(
                    manifest,
                    exam_id=exam_id,
                    title=title,
                    year=year,
                    source_url=source_info["source_website"],
                    raw_path=relative_display_path(raw_path),
                    parser="source_manifest",
                    fallback_summary=summary,
                    fallback_question_types=question_type_ids,
                    parse_status="source_manifest_only",
                )
                write_parsed_json(parsed_path, parsed_payload)
            metadata = {
                "summary": summary,
                "question_types": question_type_ids,
                "import_mode": "default_recent_source_manifest",
                "raw_path": relative_display_path(raw_path),
                "parsed_path": relative_display_path(parsed_path),
                "parse_status": "source_manifest_only",
                "parsed": loads(parsed_path.read_text(encoding="utf-8"), {}),
            }
            self.conn.execute(
                """
                INSERT OR IGNORE INTO exam_assets
                (id, exam_id, asset_type, title, year, source_url, local_path,
                 trusted_level, copyright_boundary, metadata_json)
                VALUES (?, ?, 'past_paper', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    paper_id,
                    exam_id,
                    title,
                    year,
                    source_info["source_website"],
                    relative_display_path(raw_path),
                    "needs_verification",
                    "style_reference_only",
                    dumps(metadata),
                ),
            )
            self.conn.execute(
                """
                UPDATE exam_assets
                SET local_path=CASE WHEN local_path='' THEN ? ELSE local_path END,
                    metadata_json=CASE
                        WHEN metadata_json='' OR metadata_json='{}' THEN ?
                        ELSE metadata_json
                    END
                WHERE id=?
                """,
                (relative_display_path(raw_path), dumps(metadata), paper_id),
            )

    def select_papers(self, exam_id: str, paper_ids: list[str]) -> dict[str, Any]:
        self.seed_default_papers(exam_id)
        existing = {paper["id"] for paper in self._papers(exam_id)}
        clean_ids = [paper_id for paper_id in paper_ids if paper_id in existing]
        if not clean_ids and paper_ids:
            raise ValueError("选择的真题试卷不存在。")
        self.conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (f"past_papers.selected.{exam_id}", dumps({"paper_ids": clean_ids})),
        )
        return self.status(exam_id)

    def save_question_types(self, exam_id: str, enabled_type_ids: list[str]) -> dict[str, Any]:
        known = {item["id"] for item in self._question_type_options(exam_id)}
        clean_ids = [type_id for type_id in enabled_type_ids if type_id in known]
        self.conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (f"past_papers.question_types.{exam_id}", dumps({"enabled_type_ids": clean_ids})),
        )
        return self.status(exam_id)

    def manual_import(
        self,
        *,
        exam_id: str,
        title: str,
        year: int | None,
        source_url: str,
        local_path: str,
        summary: str,
        question_types: list[str],
        raw_text: str = "",
        parse_now: bool = True,
    ) -> dict[str, Any]:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("试卷标题不能为空。")
        clean_types = [item.strip() for item in question_types if item.strip()]
        paper_id = new_id("paper")
        asset = self._store_and_parse_paper_asset(
            paper_id=paper_id,
            exam_id=exam_id,
            title=clean_title,
            year=year,
            source_url=source_url.strip(),
            local_path=local_path.strip(),
            summary=summary.strip(),
            question_types=clean_types,
            raw_text=raw_text,
            parse_now=parse_now,
        )
        self.conn.execute(
            """
            INSERT INTO exam_assets
            (id, exam_id, asset_type, title, year, source_url, local_path,
             trusted_level, copyright_boundary, metadata_json)
            VALUES (?, ?, 'past_paper', ?, ?, ?, ?, 'user_imported', 'reference_only', ?)
            """,
            (
                paper_id,
                exam_id,
                clean_title,
                year,
                source_url.strip(),
                asset["raw_path"],
                dumps(asset),
            ),
        )
        status = self.status(exam_id)
        next_selected = [paper_id, *[item for item in status["selected_paper_ids"] if item != paper_id]][:6]
        return self.select_papers(exam_id, next_selected)

    def parse_existing(self, exam_id: str, paper_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT id, exam_id, title, year, source_url, local_path, metadata_json
            FROM exam_assets
            WHERE exam_id=? AND id=? AND asset_type='past_paper'
            """,
            (exam_id, paper_id),
        ).fetchone()
        if not row:
            raise ValueError("真题试卷不存在，无法解析。")
        metadata = loads(row["metadata_json"], {})
        asset = self._store_and_parse_paper_asset(
            paper_id=str(row["id"]),
            exam_id=str(row["exam_id"]),
            title=str(row["title"]),
            year=row["year"],
            source_url=str(row["source_url"] or ""),
            local_path=str(row["local_path"] or metadata.get("raw_path", "")),
            summary=str(metadata.get("summary", "")),
            question_types=[str(item) for item in metadata.get("question_types", [])],
            raw_text="",
            parse_now=True,
        )
        self.conn.execute(
            """
            UPDATE exam_assets
            SET local_path=?, metadata_json=?
            WHERE id=?
            """,
            (asset["raw_path"], dumps(asset), paper_id),
        )
        return self.status(exam_id)

    def search_import(self, exam_id: str, source_website: str = "") -> dict[str, Any]:
        source_info = self._source_info(exam_id)
        clean_source = source_website.strip() or source_info["source_website"]
        self.seed_default_papers(exam_id)
        for year in self.DEFAULT_RECENT_YEARS:
            paper_id = f"paper_{exam_id}_{year}"
            self.conn.execute(
                """
                UPDATE exam_assets
                SET source_url=CASE WHEN source_url='' THEN ? ELSE source_url END,
                    trusted_level='needs_verification'
                WHERE id=? AND exam_id=?
                """,
                (clean_source, paper_id, exam_id),
            )
        status = self.status(exam_id)
        return {
            **status,
            "message": (
                "已按当前考试生成近三年真题搜索导入索引；"
                "本地版本记录来源网站和题型摘要，完整原文需用户按版权边界手动核验。"
            ),
        }

    def _store_and_parse_paper_asset(
        self,
        *,
        paper_id: str,
        exam_id: str,
        title: str,
        year: int | None,
        source_url: str,
        local_path: str,
        summary: str,
        question_types: list[str],
        raw_text: str,
        parse_now: bool,
    ) -> dict[str, Any]:
        dirs = ensure_exam_paper_dirs(exam_id)
        slug = paper_slug(exam_id, title, year, paper_id)
        source_path = self._resolve_paper_source_path(local_path) if local_path else None
        parse_status = "parsed"
        parse_error = ""
        parser = "text"

        if raw_text.strip():
            raw_path = dirs["raw"] / f"{slug}.md"
            raw_path.write_text(raw_text.strip() + "\n", encoding="utf-8")
            extracted_text = raw_text
            parser = "pasted_text"
        elif source_path and source_path.exists():
            raw_path = dirs["raw"] / f"{slug}{source_path.suffix.lower() or '.txt'}"
            if source_path.resolve() != raw_path.resolve():
                shutil.copy2(source_path, raw_path)
            if parse_now:
                try:
                    extracted_text, parser = extract_text_from_file(
                        raw_path,
                        language=self._language_for_exam(exam_id),
                        mineru_token=MinerUConfigService(self.conn).token_for_runtime(),
                    )
                except RuntimeError as exc:
                    extracted_text = source_manifest_text(
                        exam_id=exam_id,
                        title=title,
                        year=year,
                        source_url=source_url,
                        summary=summary,
                        question_types=question_types,
                    )
                    parser = "source_manifest_after_parse_error"
                    parse_status = "parse_failed"
                    parse_error = str(exc)
            else:
                extracted_text = source_manifest_text(
                    exam_id=exam_id,
                    title=title,
                    year=year,
                    source_url=source_url,
                    summary=summary,
                    question_types=question_types,
                )
                parser = "source_manifest_without_parse"
                parse_status = "not_parsed"
        else:
            raw_path = dirs["raw"] / f"{slug}.md"
            extracted_text = source_manifest_text(
                exam_id=exam_id,
                title=title,
                year=year,
                source_url=source_url,
                summary=summary,
                question_types=question_types,
            )
            raw_path.write_text(extracted_text, encoding="utf-8")
            parser = "source_manifest"
            parse_status = "source_manifest_only"

        parsed_path = dirs["parsed"] / f"{slug}.json"
        parsed_payload = parse_paper_text(
            extracted_text,
            exam_id=exam_id,
            title=title,
            year=year,
            source_url=source_url,
            raw_path=relative_display_path(raw_path),
            parser=parser,
            fallback_summary=summary,
            fallback_question_types=question_types,
            parse_status=parse_status,
            parse_error=parse_error,
        )
        write_parsed_json(parsed_path, parsed_payload)
        parsed_types = [str(item) for item in parsed_payload.get("question_types", []) if str(item).strip()]
        merged_types = []
        for item in [*question_types, *parsed_types]:
            if item and item not in merged_types:
                merged_types.append(item)
        return {
            "summary": parsed_payload.get("summary", summary),
            "question_types": merged_types,
            "import_mode": "manual",
            "raw_path": relative_display_path(raw_path),
            "parsed_path": relative_display_path(parsed_path),
            "parse_status": parse_status,
            "parse_error": parse_error,
            "parser": parser,
            "parsed": parsed_payload,
        }

    def _papers(self, exam_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, exam_id, asset_type, title, year, source_url, local_path,
                   trusted_level, copyright_boundary, metadata_json, created_at
            FROM exam_assets
            WHERE exam_id=? AND asset_type='past_paper'
            ORDER BY COALESCE(year, 0) DESC, created_at DESC
            """,
            (exam_id,),
        ).fetchall()
        papers = []
        for row in rows:
            paper = dict(row)
            paper["metadata"] = loads(paper.get("metadata_json", "{}"), {})
            papers.append(paper)
        return papers

    def _selected_paper_ids(self, exam_id: str) -> list[str]:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (f"past_papers.selected.{exam_id}",),
        ).fetchone()
        data = loads(row["value_json"], {}) if row else {}
        return [str(item) for item in data.get("paper_ids", []) if str(item).strip()]

    def _enabled_question_type_ids(self, exam_id: str) -> list[str]:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (f"past_papers.question_types.{exam_id}",),
        ).fetchone()
        data = loads(row["value_json"], {}) if row else {}
        return [str(item) for item in data.get("enabled_type_ids", []) if str(item).strip()]

    def _source_info(self, exam_id: str) -> dict[str, Any]:
        info = dict(self.EXAM_PAPER_SOURCES.get(exam_id) or self.EXAM_PAPER_SOURCES["custom"])
        if exam_id not in self.EXAM_PAPER_SOURCES:
            option = SyllabusService(self.conn)._exam_option(exam_id)
            info["title_prefix"] = option.get("name") or exam_id
            info["source_website"] = option.get("official_url") or ""
        return info

    def _language_for_exam(self, exam_id: str) -> str:
        if exam_id.startswith("cjt"):
            return "japan"
        if exam_id in {"ielts", "toefl"}:
            return "en"
        return "ch"

    def _resolve_paper_source_path(self, local_path: str) -> Path:
        source_path = Path(local_path).expanduser()
        if source_path.is_absolute():
            return source_path
        return PROJECT_ROOT / source_path

    def _question_type_options(self, exam_id: str) -> list[dict[str, str]]:
        info = self._source_info(exam_id)
        options = [dict(item) for item in info.get("question_types", [])]
        seen = {item["id"] for item in options}
        rows = self.conn.execute(
            """
            SELECT metadata_json FROM exam_assets
            WHERE exam_id=? AND asset_type='past_paper'
            """,
            (exam_id,),
        ).fetchall()
        for row in rows:
            metadata = loads(row["metadata_json"], {})
            for label in metadata.get("question_types", []) or []:
                clean_label = str(label).strip()
                if not clean_label:
                    continue
                type_id = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "_", clean_label.lower()).strip("_")
                if not type_id or type_id in seen:
                    continue
                seen.add(type_id)
                options.append({"id": type_id, "label": clean_label, "description": "来自已导入试卷的题型。"})
        return options


class ModelConfigService:
    MOCK_PROVIDER = {
        "id": "mock",
        "label": "Mock Provider",
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
                "vision": False,
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
            "label": "OpenAI GPT",
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
                    "vision": True,
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
                    "vision": True,
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
            "label": "Claude",
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
                    "vision": True,
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
                    "vision": True,
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
            "label": "DeepSeek",
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
                    "vision": False,
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
                    "vision": False,
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
            "label": "Xiaomi MiMo",
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
                    "vision": False,
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
                    "vision": False,
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

    def thinking_level_options(self, provider_id: str, model: str) -> list[dict[str, Any]]:
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
        provider_id = env_values.get("LANGDRILL_DEFAULT_PROVIDER") or config.get("provider_id") or "mimo"
        provider = self.provider_by_id(provider_id)
        model = env_values.get("LANGDRILL_DEFAULT_MODEL") or config.get("model") or provider.get("model", "")
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
                "vision": False,
                "has_api_key": False,
                "visible_in_picker": False,
            }
        api_value = self._thinking_api_value(thinking_level, options)
        return {
            "provider_id": provider_id,
            "base_url": env_values.get("LANGDRILL_PROVIDER_BASE_URL")
            or config.get("base_url")
            or provider.get("base_url", ""),
            "model": model,
            "thinking_level": thinking_level,
            "thinking_level_options": self.thinking_level_options(provider_id, model),
            "thinking_api_value": api_value,
            "reasoning_parameter": reasoning.get("parameter", ""),
            "api_format": config.get("api_format") or provider.get("api_format", "openai-chat-completions"),
            "vision": bool(config.get("vision", model_config.get("vision", False) if model_config else False)),
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
        thinking_level_options: list[dict[str, Any]] | None = None,
        api_format: str = "",
        vision: bool | None = None,
    ) -> dict[str, Any]:
        provider = self.provider_by_id(provider_id)
        clean_base_url = (base_url or provider.get("base_url", "")).strip()
        clean_model = (model or provider.get("model", "")).strip()
        clean_api_format = (api_format or provider.get("api_format", "openai-chat-completions")).strip()
        clean_options = self._normalize_thinking_options(thinking_level_options or self.thinking_level_options(provider_id, clean_model))
        model_config = self._model_config(provider_id, clean_model)
        reasoning = dict(model_config.get("reasoning", {})) if model_config else {}
        clean_vision = bool(vision) if vision is not None else bool(model_config.get("vision", False) if model_config else False)
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
                        "vision": clean_vision,
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
                        "vision": clean_vision,
                        "reasoning": reasoning,
                    }
                )
        if clean_options:
            reasoning["levels"] = clean_options
            reasoning["default_level"] = clean_thinking_level
            ov.setdefault("model_reasoning_overrides", {})[clean_model] = reasoning
        ov.setdefault("model_capability_overrides", {})[clean_model] = {"vision": clean_vision}

        self.conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value_json, updated_at) VALUES ('model.provider_overrides', ?, CURRENT_TIMESTAMP)",
            (dumps(overrides),),
        )
        api_key_updates = {}
        clean_api_key = normalize_api_key(api_key)
        if clean_api_key:
            api_key_updates[self._api_key_env_key(provider_id)] = clean_api_key
            api_key_updates["LANGDRILL_PROVIDER_API_KEY"] = clean_api_key
        self._write_env(
            {
                "LANGDRILL_DEFAULT_PROVIDER": provider_id,
                "LANGDRILL_DEFAULT_MODEL": clean_model,
                "LANGDRILL_PROVIDER_BASE_URL": clean_base_url,
                **api_key_updates,
            }
        )
        return self.current()

    def refresh_provider_models(
        self,
        provider_id: str,
        base_url: str = "",
        api_key: str = "",
        *,
        api_format: str = "",
    ) -> dict[str, Any]:
        provider = self.provider_by_id(provider_id)
        if provider.get("id") == "mock":
            raise ValueError("Mock Provider 不支持从 API 获取模型列表。")
        clean_base_url = (base_url or provider.get("base_url", "")).strip()
        clean_api_format = (api_format or provider.get("api_format", "openai-chat-completions")).strip()
        env_values = {**self._read_env(), **self._read_process_env()}
        clean_api_key = normalize_api_key(api_key) or self._provider_api_key(provider_id, env_values, self._current_provider_id(env_values))
        if provider.get("api_key_required", True) and not clean_api_key:
            raise ValueError("获取模型列表需要先填写或保存 API Key（接口密钥）。")

        fetched_models = self._fetch_provider_models(clean_base_url, clean_api_key, clean_api_format)
        if not fetched_models:
            raise ValueError("供应商 API 没有返回可用模型。")

        row_ov = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.provider_overrides'").fetchone()
        overrides = loads(row_ov["value_json"], {}) if row_ov else {}
        ov = overrides.setdefault(provider_id, {"added_models": [], "model_reasoning_overrides": {}})
        visibility_overrides = dict(ov.get("model_visibility_overrides", {}))
        normalized_models: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in fetched_models:
            model_id = self._model_id(item)
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            normalized = self._merge_model_metadata(provider_id, item)
            normalized["visible"] = bool(visibility_overrides.get(model_id, normalized.get("visible", True)))
            normalized_models.append(normalized)

        ov["base_url"] = clean_base_url
        ov["api_format"] = clean_api_format
        ov["fetched_models"] = normalized_models
        self._save_provider_overrides(overrides)
        return {
            "provider": self.provider_by_id(provider_id),
            "providers": self.providers(),
            "models": normalized_models,
            "message": f"已从供应商 API 获取 {len(normalized_models)} 个可调用模型。",
        }

    def set_model_visibility(self, provider_id: str, model: str, visible: bool) -> dict[str, Any]:
        clean_model = model.strip()
        if not clean_model:
            raise ValueError("模型名称不能为空。")
        row_ov = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.provider_overrides'").fetchone()
        overrides = loads(row_ov["value_json"], {}) if row_ov else {}
        ov = overrides.setdefault(provider_id, {"added_models": [], "model_reasoning_overrides": {}})
        ov.setdefault("model_visibility_overrides", {})[clean_model] = bool(visible)
        self._save_provider_overrides(overrides)
        return {
            "provider": self.provider_by_id(provider_id),
            "providers": self.providers(),
            "model_config": self.current(),
            "message": f"模型 {clean_model} 已{'显示' if visible else '隐藏'}。",
        }

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

    def add_custom_provider(self, name: str, base_url: str, default_model: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT value_json FROM app_settings WHERE key='model.custom_providers'").fetchone()
        customs = loads(row["value_json"], []) if row else []
        new_id = f"custom_{len(customs) + 1}_{int(datetime.now().timestamp())}"
        clean_name = name.strip() or "Custom Provider"
        clean_model = default_model.strip()
        provider = {
            "id": new_id,
            "label": clean_name,
            "kind": "openai-compatible",
            "api_format": "openai-chat-completions",
            "api_key_required": True,
            "enabled": True,
            "base_url": base_url.strip(),
            "model": clean_model,
            "model_options": [
                {"id": clean_model, "label": clean_model, "context_tokens": 0, "vision": False}
            ] if clean_model else [],
        }
        customs.append(provider)
        self.conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value_json, updated_at) VALUES ('model.custom_providers', ?, CURRENT_TIMESTAMP)",
            (dumps(customs),),
        )
        return self._normalize_custom_provider(provider)

    def _save_provider_overrides(self, overrides: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value_json, updated_at) VALUES ('model.provider_overrides', ?, CURRENT_TIMESTAMP)",
            (dumps(overrides),),
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
            provider["base_url"] = self._normalize_provider_base_url(
                provider["id"],
                str(ov.get("base_url", provider.get("base_url", ""))),
                str(ov.get("api_format", provider.get("api_format", "openai-chat-completions"))),
                str(provider.get("base_url", "")),
            )
            provider["api_format"] = ov.get("api_format", provider.get("api_format", "openai-chat-completions"))
            provider["enabled"] = bool(ov.get("enabled", provider.get("enabled", True)))
            model_options = [self._normalize_model_option(item) for item in provider.get("model_options", [])]
            default_reasoning = {
                self._model_id(item): dict(item.get("reasoning", {}))
                for item in model_options
            }
            existing = {self._model_id(item) for item in model_options}
            for model in [*ov.get("fetched_models", []), *ov.get("added_models", [])]:
                normalized = self._normalize_model_option(model)
                if normalized["id"] and normalized["id"] not in existing:
                    model_options.append(normalized)
                    existing.add(normalized["id"])
            reasoning_overrides = ov.get("model_reasoning_overrides", {})
            capability_overrides = ov.get("model_capability_overrides", {})
            visibility_overrides = ov.get("model_visibility_overrides", {})
            for model_item in model_options:
                model_id = self._model_id(model_item)
                if model_id in reasoning_overrides:
                    model_item["reasoning"] = self._normalize_reasoning_override(
                        reasoning_overrides[model_id],
                        default_reasoning.get(model_id, {}),
                    )
                if model_id in capability_overrides:
                    override_item = capability_overrides[model_id]
                    if isinstance(override_item, dict):
                        model_item["vision"] = bool(override_item.get("vision", model_item.get("vision", False)))
                    else:
                        model_item["vision"] = bool(override_item)
                if model_id in visibility_overrides:
                    model_item["visible"] = bool(visibility_overrides[model_id])
            provider["model_options"] = model_options
        else:
            provider["model_options"] = [self._normalize_model_option(item) for item in provider.get("model_options", [])]
        return provider

    def _normalize_provider_base_url(self, provider_id: str, base_url: str, api_format: str, default_base_url: str) -> str:
        clean_base = (base_url or "").strip().rstrip("/")
        if provider_id == "mimo" and api_format == "anthropic-messages" and clean_base == "https://api.xiaomimimo.com/v1":
            return default_base_url
        return clean_base

    def _normalize_reasoning_override(self, override: dict[str, Any], default_reasoning: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(override or {})
        normalized["levels"] = self._normalize_thinking_options(normalized.get("levels", []))
        default_levels = self._normalize_thinking_options(default_reasoning.get("levels", []))
        if default_levels and [
            (item.get("id"), item.get("api_value", ""))
            for item in normalized.get("levels", [])
        ] == [
            (item.get("id"), item.get("api_value", ""))
            for item in default_levels
        ]:
            return dict(default_reasoning)
        native_pairs = {
            (item.get("id"), item.get("api_value", ""))
            for item in default_levels
        }
        for item in normalized["levels"]:
            option_pair = (item.get("id"), item.get("api_value", ""))
            if not default_levels or option_pair not in native_pairs:
                item["custom"] = True
        return normalized

    def _normalize_model_option(self, value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            return {
                "id": value,
                "label": value,
                "context_tokens": 0,
                "vision": False,
                "visible": True,
                "reasoning": {"default_level": "", "parameter": self._default_reasoning_parameter(""), "levels": []},
            }
        item = dict(value or {})
        item.setdefault("id", item.get("model", ""))
        item.setdefault("label", item.get("id", ""))
        item.setdefault("context_tokens", 0)
        item["vision"] = bool(item.get("vision", False))
        item["visible"] = bool(item.get("visible", True))
        item.setdefault("reasoning", {"default_level": "", "parameter": self._default_reasoning_parameter(""), "levels": []})
        if item["reasoning"]:
            item["reasoning"]["levels"] = self._normalize_thinking_options(item["reasoning"].get("levels", []))
        return item

    def _merge_model_metadata(self, provider_id: str, model: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_model_option(model)
        native = self._model_config(provider_id, normalized["id"])
        if native:
            merged = {
                **normalized,
                "context_tokens": native.get("context_tokens", normalized.get("context_tokens", 0)),
                "vision": bool(native.get("vision", normalized.get("vision", False))),
                "reasoning": deepcopy(native.get("reasoning", normalized.get("reasoning", {}))),
            }
            if normalized.get("label") and normalized["label"] != normalized["id"]:
                merged["label"] = normalized["label"]
            return self._normalize_model_option(merged)
        return normalized

    def _fetch_provider_models(self, base_url: str, api_key: str, api_format: str) -> list[dict[str, Any]]:
        clean_key = validate_http_header_value(normalize_api_key(api_key), "API Key") if api_key else ""
        attempts: list[str] = []
        last_error = ""
        for endpoint, headers in self._model_list_candidates(base_url, clean_key, api_format):
            attempts.append(endpoint)
            try:
                response = httpx.get(endpoint, headers=headers, timeout=30)
                response.raise_for_status()
                return self._extract_model_options(response.json())
            except httpx.HTTPStatusError as exc:
                last_error = f"{exc.response.status_code}: {exc.response.text[:160]}"
            except Exception as exc:
                last_error = str(exc)
        tried = "、".join(attempts)
        raise ValueError(f"获取模型列表失败。已尝试：{tried}。最后错误：{last_error}")

    def _model_list_candidates(self, base_url: str, api_key: str, api_format: str) -> list[tuple[str, dict[str, str]]]:
        clean_base = (base_url or "").strip().rstrip("/")
        if not clean_base:
            raise ValueError("Base URL（基础网址）不能为空。")
        bearer_headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        anthropic_headers = {
            **({"x-api-key": api_key, "Authorization": f"Bearer {api_key}"} if api_key else {}),
            "anthropic-version": "2023-06-01",
        }
        if api_format == "anthropic-messages":
            return [
                (self._endpoint(clean_base, "/v1/models"), anthropic_headers),
                (self._endpoint(clean_base, "/models"), bearer_headers or anthropic_headers),
            ]
        return [
            (self._endpoint(clean_base, "/models"), bearer_headers),
            (self._endpoint(clean_base, "/v1/models"), bearer_headers),
        ]

    def _extract_model_options(self, data: Any) -> list[dict[str, Any]]:
        candidates: Any = data
        if isinstance(data, dict):
            for key in ("data", "models", "model_options"):
                if isinstance(data.get(key), list):
                    candidates = data[key]
                    break
            else:
                candidates = [data] if (data.get("id") or data.get("model") or data.get("name")) else []
        if not isinstance(candidates, list):
            return []
        models: list[dict[str, Any]] = []
        for item in candidates:
            if isinstance(item, str):
                model_id = item.strip()
                label = model_id
            elif isinstance(item, dict):
                model_id = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
                label = str(item.get("display_name") or item.get("label") or item.get("name") or model_id).strip()
            else:
                continue
            if not model_id:
                continue
            models.append(
                {
                    "id": model_id,
                    "label": label or model_id,
                    "context_tokens": 0,
                    "vision": False,
                    "visible": True,
                    "reasoning": {"default_level": "", "parameter": self._default_reasoning_parameter(""), "levels": []},
                }
            )
        return models

    def _endpoint(self, base_url: str, suffix: str) -> str:
        clean_base = base_url.rstrip("/")
        clean_suffix = suffix if suffix.startswith("/") else f"/{suffix}"
        if clean_base.endswith("/v1") and clean_suffix.startswith("/v1/"):
            clean_suffix = clean_suffix[3:]
        return f"{clean_base}{clean_suffix}"

    def _normalize_thinking_options(self, options: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for option in options or []:
            option_id = str(option.get("id", "")).strip()
            if not option_id or option_id in seen:
                continue
            seen.add(option_id)
            item = {
                "id": option_id,
                "label": str(option.get("label") or option_id).strip(),
                "api_value": str(option.get("api_value", "")).strip(),
            }
            if bool(option.get("custom")):
                item["custom"] = True
            normalized.append(item)
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
        return str(env_values.get("LANGDRILL_DEFAULT_PROVIDER") or config.get("provider_id") or "mimo")

    def _api_key_env_key(self, provider_id: str) -> str:
        clean = "".join(ch if ch.isalnum() else "_" for ch in provider_id.upper()).strip("_")
        return f"LANGDRILL_PROVIDER_API_KEY_{clean or 'CUSTOM'}"

    def _provider_api_key(self, provider_id: str, env_values: dict[str, str], current_provider_id: str | None = None) -> str:
        specific = normalize_api_key(env_values.get(self._api_key_env_key(provider_id), ""))
        if specific:
            return specific
        if current_provider_id == provider_id:
            return normalize_api_key(env_values.get("LANGDRILL_PROVIDER_API_KEY", ""))
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
            clean_key = key.strip()
            clean_value = value.strip()
            if "API_KEY" in clean_key.upper() or clean_key.upper() == "MINERU_TOKEN":
                clean_value = normalize_api_key(clean_value)
            values[clean_key] = clean_value
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
            "MINERU_TOKEN",
        }
        values: dict[str, str] = {}
        for key in keys:
            value = os.environ.get(key)
            if value and value.strip():
                values[key] = normalize_api_key(value) if "API_KEY" in key.upper() or key.upper() == "MINERU_TOKEN" else value.strip()
        for key, value in os.environ.items():
            if key.startswith("LANGDRILL_PROVIDER_API_KEY_") and value and value.strip():
                values[key] = normalize_api_key(value)
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
            "MINERU_TOKEN",
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


class MinerUConfigService:
    ENV_KEY = "MINERU_TOKEN"
    TOKEN_URL = "https://mineru.net/apiManage/token"
    DOCS_URL = "https://mineru.net/apiManage/docs"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def status(self) -> dict[str, Any]:
        token = self.token_for_runtime()
        return {
            "token_url": self.TOKEN_URL,
            "docs_url": self.DOCS_URL,
            "env_key": self.ENV_KEY,
            "has_token": bool(token),
            "token_preview": self._preview(token),
        }

    def save(self, token: str, *, clear_token: bool = False) -> dict[str, Any]:
        env_service = ModelConfigService(self.conn)
        if clear_token:
            env_service._write_env({self.ENV_KEY: ""}, clear_empty=True)
            return self.status()
        clean_token = normalize_api_key(token)
        if clean_token:
            validate_http_header_value(clean_token, "MinerU token")
            env_service._write_env({self.ENV_KEY: clean_token})
        return self.status()

    def token_for_runtime(self) -> str:
        env_service = ModelConfigService(self.conn)
        values = {**env_service._read_env(), **env_service._read_process_env()}
        return normalize_api_key(values.get(self.ENV_KEY, ""))

    def _preview(self, token: str) -> str:
        if not token:
            return ""
        if len(token) <= 8:
            return "已配置"
        return f"{token[:4]}...{token[-4:]}"
