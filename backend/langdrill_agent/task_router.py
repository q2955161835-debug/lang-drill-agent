from __future__ import annotations

import re

from .models import TaskType


# 严格匹配答案的模式：A/B/C/D（可选前缀"选"/"答案是"），或"不会"/"跳过"/"不确定"
_ANSWER_PATTERN = re.compile(
    r"^(?:选择?\s*)?[A-Da-d]$"
    r"|^答案是\s*[A-Da-d]$"
    r"|^(?:不会|跳过|不确定)$",
    re.IGNORECASE,
)

# 追问 / 讲解关键词 —— 出现任意一个就不算答题
_EXPLANATION_KEYWORDS = (
    "为什么", "解释", "讲讲", "什么意思", "换种说法", "换种讲法",
    "怎么理解", "能不能讲", "不太懂", "看不懂", "再讲一遍",
    "为啥", "原因", "详细",
)

_SETTINGS_KEYWORDS = (
    "设置", "供应商", "模型", "更改目标", "修改背景",
    "配置", "调整人格", "切换供应商",
)

_SUMMARY_KEYWORDS = ("总结", "复盘", "今天表现", "今日表现", "复习报告")
_CONTINUE_KEYWORDS = ("下一题", "继续", "下一个", "next", "Next", "NEXT")


class TaskRouter:
    def route(
        self,
        content: str,
        *,
        has_active_question: bool,
        selected_text: str | None = None,
        selected_option: str | None = None,
    ) -> TaskType:
        text = content.strip()

        # 1. 分支对话：有选中文本
        if selected_text:
            return TaskType.branch_chat

        # 2. 题目选项来自结构化提交，即使附带追问也先进入答题流程
        if has_active_question and selected_option and selected_option.strip().upper() in {"A", "B", "C", "D"}:
            return TaskType.answer_question

        # 3. 设置：匹配设置关键词
        if any(keyword in text for keyword in _SETTINGS_KEYWORDS):
            return TaskType.settings

        # 4. 总结：匹配总结关键词
        if any(keyword in text for keyword in _SUMMARY_KEYWORDS):
            return TaskType.summary

        # 5. 追问 / 讲解：有当前题且命中讲解关键词
        if has_active_question and any(keyword in text for keyword in _EXPLANATION_KEYWORDS):
            return TaskType.explanation

        # 6. 答题：严格正则匹配
        if has_active_question and _ANSWER_PATTERN.match(text):
            return TaskType.answer_question

        # 7. 推进：只取数据库里的下一道待答题，不重新初始化
        if any(keyword == text or keyword in text for keyword in _CONTINUE_KEYWORDS):
            return TaskType.continue_drill

        # 8. 默认：日常训练
        return TaskType.daily_drill
