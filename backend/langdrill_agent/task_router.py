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
    "为啥", "原因", "详细", "提示", "给点提示", "不要告诉答案",
    "hint", "give me a hint",
)

_SETTINGS_MUTATION_PATTERN = re.compile(
    r"(?:打开|进入|跳到|前往|更改|修改|配置|调整|切换|新增|添加|删除|移除|填写|填入|保存)"
    r".{0,18}(?:设置|设置页|供应商|模型|目标|背景|人格|权限|上下文|数据库|MinerU|api\s*key|apikey|密钥)"
    r"|(?:设置页|供应商|模型|目标|背景|人格|权限|上下文|数据库|MinerU|api\s*key|apikey|密钥)"
    r".{0,18}(?:打开|进入|更改|修改|配置|调整|切换|新增|添加|删除|移除|填写|填入|保存)"
    r"|(?:把|将).{0,28}(?:目标|背景|人格|模型|供应商|权限|上下文).{0,12}"
    r"(?:改成|改为|设为|设置为|换成|切到|调整为)"
    r"|(?:设置|设定).{0,3}(?:供应商|模型|目标|背景|人格|权限|上下文|数据库|MinerU|api\s*key|apikey|密钥)"
    r"|(?<!已)(?:开启|关闭|启用|禁用).{0,18}(?:联网|截图|词表|数据库|真题|模型|密钥|权限|Skill|Skills|skill|skills)",
    re.IGNORECASE,
)
_PAST_PAPER_SETTINGS_PATTERN = re.compile(
    r"(?:真题|试卷|样卷|past paper|paper).{0,24}(?:导入|填入|填写|填表|设置|保存|解析)"
    r"|(?:导入|填入|填写|填表|设置|保存|解析).{0,24}(?:真题|试卷|样卷|past paper|paper)",
    re.IGNORECASE,
)

_SUMMARY_KEYWORDS = ("总结", "复盘", "今天表现", "今日表现", "复习报告")
_CONTINUE_KEYWORDS = ("下一题", "继续", "下一个", "next", "Next", "NEXT")

_ADVICE_OR_CHAT_KEYWORDS = (
    "怎么", "如何", "为什么", "为啥", "吗", "？", "?",
    "是不是", "建议", "推荐", "计划", "规划", "应该",
)
_FORCE_DRILL_PATTERN = re.compile(
    r"(?:出题|出.{0,16}题|生成题|生成.{0,16}题|刷题|做题|练题|考我|测验|小测)"
    r"|(?:quiz|drill|practice|test me)",
    re.IGNORECASE,
)
_DRILL_ACTION_PATTERN = re.compile(
    r"(?:出题|出.{0,16}题|生成题|生成.{0,16}题)"
    r"|(?:给我|帮我|请|来|开始|现在|我要|我想)?.{0,8}"
    r"(?:刷题|做题|练题|"
    r"练(?:习|单词|词汇|听力|阅读|写作)?|考我|测验|小测|训练)"
    r"|(?:quiz|drill|practice|test me)",
    re.IGNORECASE,
)
_START_LEARNING_PATTERN = re.compile(
    r"(?:今天|今日|现在|开始|我要|我想).{0,12}"
    r"(?:学习|复习|背单词|练习|练|训练|刷题)",
    re.IGNORECASE,
)
_VOCAB_DEFINITION_PATTERN = re.compile(
    r"^[A-Za-z][A-Za-z' -]{1,40}\s*[:：]\s*\S+"
    r"|^[A-Za-z][A-Za-z' -]{1,40}\s+"
    r"(?:n|v|vi|vt|adj|adv|prep|conj|pron|num|art|aux)\.\s*\S+",
    re.IGNORECASE,
)


def _has_advice_or_chat_cue(text: str) -> bool:
    return any(keyword in text for keyword in _ADVICE_OR_CHAT_KEYWORDS)


def _looks_like_explicit_drill_request(text: str) -> bool:
    if not text.strip():
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if any(_VOCAB_DEFINITION_PATTERN.match(line) for line in lines):
        return True
    if _has_advice_or_chat_cue(text) and not _FORCE_DRILL_PATTERN.search(text):
        return False
    if _DRILL_ACTION_PATTERN.search(text):
        return True
    return bool(_START_LEARNING_PATTERN.search(text))


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

        # 3. 设置：只有明确修改、打开或导入设置时才进入设置流程。
        if _SETTINGS_MUTATION_PATTERN.search(text) or _PAST_PAPER_SETTINGS_PATTERN.search(text):
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

        # 8. 明确学习 / 练题意图才进入日常训练；普通寒暄和咨询只聊天。
        if _looks_like_explicit_drill_request(text):
            return TaskType.daily_drill

        return TaskType.general_chat
