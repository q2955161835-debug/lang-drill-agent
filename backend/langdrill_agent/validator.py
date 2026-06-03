from __future__ import annotations

from .models import Question


class QuestionValidationError(ValueError):
    pass


class QuestionValidator:
    def validate(self, question: Question) -> Question:
        if question.type == "multiple_choice":
            if len(question.options) < 2:
                raise QuestionValidationError("选择题至少需要两个选项")
            correct = question.answer.get("correct")
            if correct not in question.options and correct not in ["A", "B", "C", "D"]:
                raise QuestionValidationError("选择题答案必须对应选项或选项字母")
        if not question.knowledge_tags:
            raise QuestionValidationError("题目必须包含 knowledge_tags")
        if question.difficulty < 0 or question.difficulty > 1:
            raise QuestionValidationError("difficulty 必须在 0 到 1 之间")
        return question
