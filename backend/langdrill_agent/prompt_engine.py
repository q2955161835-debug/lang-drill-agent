from __future__ import annotations

import sqlite3
from typing import Any

from .models import PromptPack


class PromptRegistry:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def select_modules(
        self,
        task_type: str,
        exam_id: str,
        persona: str = "professional",
        include_user_prompt: bool = True,
    ) -> list[dict[str, str]]:
        rows = self.conn.execute(
            """
            SELECT id, version, scope, task_type, exam_id, priority, content
            FROM prompt_modules
            WHERE enabled = 1
              AND (
                task_type = 'all'
                OR task_type = ?
                OR (scope = 'persona' AND ? IN ('general_chat', 'branch_chat', 'chat_summary', 'summary'))
              )
              AND (exam_id = 'any' OR exam_id = ?)
            ORDER BY priority DESC, id ASC
            """,
            (task_type, task_type, exam_id),
        ).fetchall()

        modules = [dict(row) for row in rows if row["scope"] != "persona"]
        if task_type in {"general_chat", "branch_chat", "chat_summary", "summary"} and persona != "none":
            persona_id = f"persona.{persona}"
            modules.extend(dict(row) for row in rows if row["id"] == persona_id)

        if not include_user_prompt:
            return modules
        return modules


class PromptAssembler:
    def __init__(self, registry: PromptRegistry):
        self.registry = registry

    def assemble(
        self,
        *,
        task_type: str,
        exam_id: str,
        persona: str,
        context_pack: dict[str, Any],
        user_content: str,
        output_schema: dict[str, Any] | None = None,
        allow_global_user_prompt: bool = True,
    ) -> PromptPack:
        modules = self.registry.select_modules(
            task_type=task_type,
            exam_id=exam_id,
            persona=persona,
            include_user_prompt=allow_global_user_prompt,
        )
        safe_context = {
            key: value
            for key, value in context_pack.items()
            if key not in {"raw_history", "full_syllabus", "full_papers"}
        }
        return PromptPack(
            system_modules=modules,
            context_pack=safe_context,
            user_content=user_content,
            output_schema=output_schema,
        )
