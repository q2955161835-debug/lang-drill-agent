from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .memory.hooks import MemoryHooks
from .utils import dumps, estimate_tokens, loads, new_id, today_str


DEFAULT_CONTEXT_LIMIT = 1_000_000
CONTEXT_SETTINGS_KEY = "context.settings"


class ContextService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def settings(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (CONTEXT_SETTINGS_KEY,),
        ).fetchone()
        settings = loads(row["value_json"], {}) if row else {}
        max_tokens = int(settings.get("max_tokens") or DEFAULT_CONTEXT_LIMIT)
        if max_tokens < 1_000:
            max_tokens = DEFAULT_CONTEXT_LIMIT
        return {
            "max_tokens": max_tokens,
            "compression_project": "Microsoft LLMLingua",
            "compression_project_url": "https://github.com/microsoft/LLMLingua",
            "compression_optional_extra": "context-compression",
        }

    def save_settings(self, max_tokens: int) -> dict[str, Any]:
        clean_limit = max(1_000, min(int(max_tokens or DEFAULT_CONTEXT_LIMIT), 10_000_000))
        data = {
            "max_tokens": clean_limit,
            "compression_project": "Microsoft LLMLingua",
            "compression_project_url": "https://github.com/microsoft/LLMLingua",
            "compression_optional_extra": "context-compression",
        }
        self.conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (CONTEXT_SETTINGS_KEY, dumps(data)),
        )
        return self.settings()

    def usage(self, session_id: str | None = None) -> dict[str, Any]:
        settings = self.settings()
        snapshot = self.session_context_snapshot(session_id) if session_id else {}
        context_tokens = estimate_tokens(dumps(snapshot)) if snapshot else 0
        summary = str(snapshot.get("session", {}).get("summary", "")) if snapshot else ""
        compressed_tokens = estimate_tokens(summary)
        limit = int(settings["max_tokens"])
        return {
            "estimated_current_context": context_tokens,
            "context_limit": limit,
            "context_percent": round(context_tokens / limit, 4) if limit else 0,
            "context_messages": len(snapshot.get("messages", [])) if snapshot else 0,
            "compressed_context_tokens": compressed_tokens,
            "compression_method": "study_sessions.summary" if summary else "",
            "compression_available": True,
            "compression_project": settings["compression_project"],
            "compression_project_url": settings["compression_project_url"],
        }

    def session_context_snapshot(self, session_id: str | None, *, max_messages: int = 200) -> dict[str, Any]:
        if not session_id:
            return {}
        session = self.conn.execute(
            "SELECT id, title, folder_date, exam_id, status, summary FROM study_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if not session:
            return {}
        profile = self.conn.execute("SELECT * FROM user_profiles WHERE id=1").fetchone()
        messages = self.conn.execute(
            """
            SELECT role, content, created_at
            FROM messages
            WHERE session_id=?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
        if len(messages) > max_messages:
            messages = messages[-max_messages:]
        active_question = self.conn.execute(
            """
            SELECT sequence, type, prompt, options_json, answer_json, explanation, knowledge_tags_json
            FROM questions
            WHERE session_id=? AND status='ready'
            ORDER BY sequence ASC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        attempts = self.conn.execute(
            """
            SELECT user_answer, is_correct, feedback, created_at
            FROM attempts
            WHERE session_id=?
            ORDER BY created_at DESC
            LIMIT 12
            """,
            (session_id,),
        ).fetchall()
        return {
            "profile": self._profile_context(dict(profile)) if profile else {},
            "session": dict(session),
            "messages": [dict(row) for row in messages],
            "active_question": self._question_context(dict(active_question)) if active_question else None,
            "recent_attempts": [dict(row) for row in attempts],
        }

    def prompt_context(self, session_id: str | None) -> dict[str, Any]:
        snapshot = self.session_context_snapshot(session_id, max_messages=120)
        usage = self.usage(session_id)
        available = max(
            0,
            int(usage["context_limit"]) - int(usage["estimated_current_context"]),
        )
        session_scope = "global"
        if snapshot:
            session_scope = f"exam:{snapshot.get('session', {}).get('exam_id') or 'global'}"
        memory_query = " ".join(
            [
                str(item.get("content") or "")
                for item in (snapshot.get("messages", [])[-8:] if snapshot else [])
            ]
            + [
                str(item.get("feedback") or "")
                for item in (snapshot.get("recent_attempts", [])[:4] if snapshot else [])
            ]
        ).strip()
        memory_context = MemoryHooks(self.conn).recall(
            memory_query,
            scope=session_scope,
            available_context_tokens=available,
        )
        return {
            "context_usage": usage,
            "compressed_summary": snapshot.get("session", {}).get("summary", "") if snapshot else "",
            "conversation": snapshot.get("messages", []) if snapshot else [],
            "recent_attempts": snapshot.get("recent_attempts", []) if snapshot else [],
            "profile": snapshot.get("profile", {}) if snapshot else {},
            "memory": memory_context.model_dump(mode="json"),
        }

    def compress_session(self, session_id: str, target_tokens: int | None = None) -> dict[str, Any]:
        snapshot = self.session_context_snapshot(session_id, max_messages=400)
        MemoryHooks(self.conn).before_context_compaction(
            messages=snapshot.get("messages", []) if snapshot else [],
            scope=f"exam:{snapshot.get('session', {}).get('exam_id') or 'global'}" if snapshot else "global",
        )
        if not snapshot:
            raise ValueError("会话不存在，无法压缩上下文。")
        raw_text = self._format_snapshot(snapshot)
        settings = self.settings()
        target = int(target_tokens or min(max(settings["max_tokens"] // 4, 2_000), 50_000))
        target = max(500, target)
        compressed, method, note = self._compress_text(raw_text, target)
        self.conn.execute(
            """
            UPDATE study_sessions
            SET summary=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (compressed, session_id),
        )
        self.conn.execute(
            """
            INSERT INTO audit_events (id, level, event_type, message, payload_json)
            VALUES (?, 'info', 'context_compressed', ?, ?)
            """,
            (
                new_id("audit"),
                "主动压缩会话上下文",
                dumps(
                    {
                        "session_id": session_id,
                        "method": method,
                        "raw_tokens": estimate_tokens(raw_text),
                        "compressed_tokens": estimate_tokens(compressed),
                        "note": note,
                    }
                ),
            ),
        )
        usage = self.usage(session_id)
        return {
            "session_id": session_id,
            "summary": compressed,
            "method": method,
            "note": note,
            "raw_tokens": estimate_tokens(raw_text),
            "compressed_tokens": estimate_tokens(compressed),
            "token_usage": usage,
        }

    def global_usage_stats(self) -> dict[str, Any]:
        totals = self.conn.execute(
            """
            SELECT
              COALESCE(SUM(input_tokens), 0) AS input,
              COALESCE(SUM(output_tokens), 0) AS output,
              COUNT(*) AS calls,
              COALESCE(AVG(latency_ms), 0) AS avg_latency_ms
            FROM model_calls
            """
        ).fetchone()
        sessions = self.conn.execute(
            "SELECT COUNT(*) AS count FROM study_sessions WHERE status!='deleted'"
        ).fetchone()
        messages = self.conn.execute("SELECT COUNT(*) AS count FROM messages").fetchone()
        active_days = self.conn.execute(
            "SELECT COUNT(DISTINCT folder_date) AS count FROM study_sessions WHERE status!='deleted'"
        ).fetchone()
        model_rows = self.conn.execute(
            """
            SELECT provider_id, model,
                   COALESCE(SUM(input_tokens), 0) AS input,
                   COALESCE(SUM(output_tokens), 0) AS output,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                   COUNT(*) AS calls
            FROM model_calls
            GROUP BY provider_id, model
            ORDER BY tokens DESC, calls DESC
            LIMIT 8
            """
        ).fetchall()
        total_tokens = int(totals["input"] or 0) + int(totals["output"] or 0)
        breakdown = []
        for row in model_rows:
            tokens = int(row["tokens"] or 0)
            breakdown.append(
                {
                    "provider_id": row["provider_id"],
                    "model": row["model"],
                    "input": int(row["input"] or 0),
                    "output": int(row["output"] or 0),
                    "tokens": tokens,
                    "calls": int(row["calls"] or 0),
                    "percent": round(tokens / total_tokens, 4) if total_tokens else 0,
                }
            )
        daily_activity = self._daily_activity()
        provider_breakdown = self._provider_breakdown(total_tokens)
        task_breakdown = self._task_breakdown(total_tokens)
        today = today_str()
        today_stats = self._period_usage("DATE(created_at, 'localtime') = ?", (today,))
        yesterday_date = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_stats = self._period_usage("DATE(created_at, 'localtime') = ?", (yesterday_date,))
        last_7_days_stats = self._period_usage(
            "DATE(created_at, 'localtime') >= ?",
            ((datetime.strptime(today, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d"),),
        )
        last_30_days_stats = self._period_usage(
            "DATE(created_at, 'localtime') >= ?",
            ((datetime.strptime(today, "%Y-%m-%d") - timedelta(days=29)).strftime("%Y-%m-%d"),),
        )
        month_stats = self._period_usage(
            "strftime('%Y-%m', created_at, 'localtime') = ?",
            (today[:7],),
        )
        total_calls = int(totals["calls"] or 0)
        return {
            "input": int(totals["input"] or 0),
            "output": int(totals["output"] or 0),
            "total": total_tokens,
            "total_calls": total_calls,
            "average_tokens_per_call": round(total_tokens / total_calls, 2) if total_calls else 0,
            "average_latency_ms": int(totals["avg_latency_ms"] or 0),
            "today": today_stats,
            "yesterday": yesterday_stats,
            "last_7_days": last_7_days_stats,
            "last_30_days": last_30_days_stats,
            "current_month": month_stats,
            "sessions_total": int(sessions["count"] or 0),
            "messages_total": int(messages["count"] or 0),
            "active_days": int(active_days["count"] or 0),
            "current_streak_days": self._current_streak_days(),
            "most_used_model": breakdown[0]["model"] if breakdown else "",
            "most_used_model_percent": breakdown[0]["percent"] if breakdown else 0,
            "model_breakdown": breakdown,
            "provider_breakdown": provider_breakdown,
            "task_breakdown": task_breakdown,
            "daily_activity": daily_activity,
            "recent_calls": self._recent_calls(),
        }

    def _daily_activity(self) -> list[dict[str, Any]]:
        end = datetime.strptime(today_str(), "%Y-%m-%d")
        start = end - timedelta(days=29)
        rows = self.conn.execute(
            """
            SELECT DATE(created_at, 'localtime') AS date,
                   COALESCE(SUM(input_tokens), 0) AS input,
                   COALESCE(SUM(output_tokens), 0) AS output,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                   COUNT(*) AS calls
            FROM model_calls
            WHERE DATE(created_at, 'localtime') >= ?
            GROUP BY DATE(created_at, 'localtime')
            """,
            (start.strftime("%Y-%m-%d"),),
        ).fetchall()
        by_date = {str(row["date"]): row for row in rows}
        activity = []
        for offset in range(30):
            date = (start + timedelta(days=offset)).strftime("%Y-%m-%d")
            row = by_date.get(date)
            activity.append(
                {
                    "date": date,
                    "input": int(row["input"] or 0) if row else 0,
                    "output": int(row["output"] or 0) if row else 0,
                    "tokens": int(row["tokens"] or 0) if row else 0,
                    "calls": int(row["calls"] or 0) if row else 0,
                }
            )
        return activity

    def _period_usage(self, where_sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
        row = self.conn.execute(
            f"""
            SELECT
              COALESCE(SUM(input_tokens), 0) AS input,
              COALESCE(SUM(output_tokens), 0) AS output,
              COUNT(*) AS calls,
              COALESCE(AVG(latency_ms), 0) AS avg_latency_ms
            FROM model_calls
            WHERE {where_sql}
            """,
            params,
        ).fetchone()
        input_tokens = int(row["input"] or 0)
        output_tokens = int(row["output"] or 0)
        calls = int(row["calls"] or 0)
        return {
            "input": input_tokens,
            "output": output_tokens,
            "total": input_tokens + output_tokens,
            "calls": calls,
            "average_tokens_per_call": round((input_tokens + output_tokens) / calls, 2) if calls else 0,
            "average_latency_ms": int(row["avg_latency_ms"] or 0),
        }

    def _provider_breakdown(self, total_tokens: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT provider_id,
                   COALESCE(SUM(input_tokens), 0) AS input,
                   COALESCE(SUM(output_tokens), 0) AS output,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                   COUNT(*) AS calls
            FROM model_calls
            GROUP BY provider_id
            ORDER BY tokens DESC, calls DESC
            LIMIT 12
            """
        ).fetchall()
        return [
            {
                "provider_id": row["provider_id"],
                "input": int(row["input"] or 0),
                "output": int(row["output"] or 0),
                "tokens": int(row["tokens"] or 0),
                "calls": int(row["calls"] or 0),
                "percent": round(int(row["tokens"] or 0) / total_tokens, 4) if total_tokens else 0,
            }
            for row in rows
        ]

    def _task_breakdown(self, total_tokens: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT task_type,
                   COALESCE(SUM(input_tokens), 0) AS input,
                   COALESCE(SUM(output_tokens), 0) AS output,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                   COUNT(*) AS calls
            FROM model_calls
            GROUP BY task_type
            ORDER BY tokens DESC, calls DESC
            LIMIT 12
            """
        ).fetchall()
        return [
            {
                "task_type": row["task_type"],
                "input": int(row["input"] or 0),
                "output": int(row["output"] or 0),
                "tokens": int(row["tokens"] or 0),
                "calls": int(row["calls"] or 0),
                "percent": round(int(row["tokens"] or 0) / total_tokens, 4) if total_tokens else 0,
            }
            for row in rows
        ]

    def _recent_calls(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, agent_name, task_type, provider_id, model,
                   input_tokens, output_tokens, latency_ms, validation_status, created_at
            FROM model_calls
            ORDER BY created_at DESC
            LIMIT 24
            """
        ).fetchall()
        return [
            {
                "id": row["id"],
                "agent_name": row["agent_name"],
                "task_type": row["task_type"],
                "provider_id": row["provider_id"],
                "model": row["model"],
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
                "total_tokens": int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0),
                "latency_ms": int(row["latency_ms"] or 0),
                "validation_status": row["validation_status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _current_streak_days(self) -> int:
        rows = self.conn.execute(
            """
            SELECT DISTINCT folder_date
            FROM study_sessions
            WHERE status!='deleted'
            ORDER BY folder_date DESC
            """
        ).fetchall()
        days = {str(row["folder_date"]) for row in rows}
        cursor = datetime.strptime(today_str(), "%Y-%m-%d")
        streak = 0
        while cursor.strftime("%Y-%m-%d") in days:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    def _profile_context(self, profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "display_name": profile.get("display_name"),
            "target_language": profile.get("target_language"),
            "exam_id": profile.get("exam_id"),
            "exam_name": profile.get("exam_name"),
            "learning_goal": profile.get("learning_goal"),
            "learning_background": profile.get("learning_background"),
            "persona": profile.get("persona"),
            "global_user_prompt": profile.get("global_user_prompt"),
        }

    def _question_context(self, question: dict[str, Any]) -> dict[str, Any]:
        return {
            "sequence": question.get("sequence"),
            "type": question.get("type"),
            "prompt": question.get("prompt"),
            "options": loads(question.get("options_json", "[]"), []),
            "answer": loads(question.get("answer_json", "{}"), {}),
            "explanation": question.get("explanation"),
            "knowledge_tags": loads(question.get("knowledge_tags_json", "[]"), []),
        }

    def _format_snapshot(self, snapshot: dict[str, Any]) -> str:
        lines = [
            f"用户：{snapshot.get('profile', {}).get('display_name', '')}",
            f"考试：{snapshot.get('profile', {}).get('exam_name', '')}",
            f"目标：{snapshot.get('profile', {}).get('learning_goal', '')}",
            f"背景：{snapshot.get('profile', {}).get('learning_background', '')}",
            "",
            "会话消息：",
        ]
        for message in snapshot.get("messages", []):
            lines.append(f"{message.get('role')}: {message.get('content')}")
        attempts = snapshot.get("recent_attempts", [])
        if attempts:
            lines.append("")
            lines.append("最近作答：")
            for attempt in attempts:
                result = "正确" if attempt.get("is_correct") else "不正确"
                lines.append(f"- {result}；答案：{attempt.get('user_answer')}；反馈：{attempt.get('feedback')}")
        return "\n".join(lines)

    def _compress_text(self, text: str, target_tokens: int) -> tuple[str, str, str]:
        if os.getenv("LANGDRILL_ENABLE_LLMLINGUA", "").strip() == "1":
            try:
                from llmlingua import PromptCompressor  # type: ignore

                compressor = PromptCompressor()
                result = compressor.compress_prompt(text, target_token=target_tokens)
                compressed = str(result.get("compressed_prompt") or "").strip()
                if compressed:
                    return compressed, "llmlingua", "使用可选 LLMLingua 压缩器。"
            except Exception as exc:
                note = f"LLMLingua 不可用，已使用本地摘要兜底：{exc}"
                return self._extractive_summary(text, target_tokens), "extractive_fallback", note
        return (
            self._extractive_summary(text, target_tokens),
            "extractive_fallback",
            "未启用 LANGDRILL_ENABLE_LLMLINGUA=1，使用本地抽取式摘要兜底。",
        )

    def _extractive_summary(self, text: str, target_tokens: int) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        budget = max(target_tokens, 200)
        selected: list[str] = []
        score_words = ("不正确", "错误", "正确答案", "知识点", "目标", "背景", "用户:", "assistant:")
        for line in lines:
            if any(word in line for word in score_words) or len(selected) < 12:
                selected.append(line)
            if estimate_tokens("\n".join(selected)) >= budget:
                break
        if estimate_tokens("\n".join(selected)) < budget:
            for line in lines[-80:]:
                if line not in selected:
                    selected.append(line)
                if estimate_tokens("\n".join(selected)) >= budget:
                    break
        return "\n".join(selected)
