from __future__ import annotations

from .models import TaskType


ANSWER_PREFIXES = ("A", "B", "C", "D", "不会", "不确定", "跳过")


class TaskRouter:
    def route(self, content: str, *, has_active_question: bool, selected_text: str | None = None) -> TaskType:
        text = content.strip()
        if selected_text:
            return TaskType.branch_chat
        if any(keyword in text for keyword in ["设置", "供应商", "模型", "目标", "背景"]):
            return TaskType.settings
        if has_active_question and (
            len(text) <= 20 or text.upper()[:1] in {"A", "B", "C", "D"} or text in ANSWER_PREFIXES
        ):
            return TaskType.answer_question
        if any(keyword in text for keyword in ["总结", "复盘", "今天表现"]):
            return TaskType.summary
        return TaskType.daily_drill
