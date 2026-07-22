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

    def validate_source_refs(
        self,
        question: Question,
        allowed_past_paper_question_ids: set[str],
    ) -> Question:
        forbidden_claims = {
            "original_paper_question",
            "original_exam_question",
            "verbatim_past_paper",
        }
        for source_ref in question.source_refs:
            if source_ref.get("type") != "past_paper_evidence":
                continue
            question_id = str(source_ref.get("question_id") or "")
            if question_id not in allowed_past_paper_question_ids:
                raise QuestionValidationError("真题来源引用不在本轮检索证据中")
            if str(source_ref.get("claim") or "") in forbidden_claims:
                raise QuestionValidationError("生成题不得声明为真题原题")
        return question
