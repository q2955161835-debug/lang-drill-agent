from __future__ import annotations

from .models import Question


class QuestionValidationError(ValueError):
    pass


class QuestionValidator:
    def validate(self, question: Question) -> Question:
        if question.type == "multiple_choice":
            if len(question.options) < 2:
                raise QuestionValidationError("选择题至少需要两个选项")
            valid_letters = [chr(ord("A") + index) for index in range(len(question.options))]
            letter = str(question.answer.get("letter") or "").strip().upper()
            correct = question.answer.get("correct")
            correct_text = str(correct or "").strip()
            resolved_correct = ""
            if letter:
                if letter not in valid_letters:
                    raise QuestionValidationError("选择题答案字母必须对应现有选项")
                resolved_correct = question.options[ord(letter) - ord("A")]
            if correct_text in valid_letters:
                resolved_correct = question.options[ord(correct_text) - ord("A")]
            elif correct_text in question.options:
                if resolved_correct and resolved_correct != correct_text:
                    raise QuestionValidationError("选择题答案字母与答案文本不一致")
                resolved_correct = correct_text
            if not resolved_correct:
                raise QuestionValidationError("选择题答案必须对应选项或选项字母")
        if not question.knowledge_tags:
            raise QuestionValidationError("题目必须包含 knowledge_tags")
        if question.difficulty < 0 or question.difficulty > 1:
            raise QuestionValidationError("difficulty 必须在 0 到 1 之间")
        return question
