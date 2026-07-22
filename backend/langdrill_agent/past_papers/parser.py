from __future__ import annotations

import re

from pydantic import BaseModel, Field


class ParsedPaperSection(BaseModel):
    title: str
    question_type: str = ""
    source_page: int | None = Field(default=None, ge=1)


class ParsedPaperPassage(BaseModel):
    title: str = ""
    section_title: str = ""
    content: str
    source_page: int | None = Field(default=None, ge=1)


class ParsedPaperQuestion(BaseModel):
    question_number: str = ""
    section_title: str = ""
    passage_title: str = ""
    question_type: str = ""
    prompt: str
    options: list[str] = Field(default_factory=list)
    answer: dict[str, object] = Field(default_factory=dict)
    explanation: str = ""
    knowledge_tags: list[str] = Field(default_factory=list)
    difficulty: float | None = Field(default=None, ge=0, le=1)
    source_page: int | None = Field(default=None, ge=1)
    answer_confidence: float = Field(default=0, ge=0, le=1)
    verification_status: str = "unverified"


class PaperParseResult(BaseModel):
    schema_version: int = 2
    exam_id: str = ""
    title: str
    year: int | None = None
    source_url: str = ""
    sections: list[ParsedPaperSection] = Field(default_factory=list)
    passages: list[ParsedPaperPassage] = Field(default_factory=list)
    questions: list[ParsedPaperQuestion] = Field(default_factory=list)


def parse_extracted_paper_text(
    text: str,
    *,
    exam_id: str,
    title: str,
    year: int | None,
    source_url: str,
) -> PaperParseResult:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    section_title = "General"
    sections = [ParsedPaperSection(title=section_title)]
    questions: list[ParsedPaperQuestion] = []
    current_number = ""
    current_lines: list[str] = []

    def flush_question() -> None:
        nonlocal current_number, current_lines
        if not current_number:
            return
        prompt_lines: list[str] = []
        options: list[str] = []
        answer: dict[str, object] = {}
        for line in current_lines:
            option_match = re.match(r"^[A-H][.)、．]\s*(.+)$", line, re.IGNORECASE)
            answer_match = re.match(
                r"^(?:answer|答案)\s*[:：]\s*([A-H])\b",
                line,
                re.IGNORECASE,
            )
            if option_match:
                options.append(option_match.group(1).strip())
            elif answer_match:
                answer = {"letter": answer_match.group(1).upper()}
            elif line.strip():
                prompt_lines.append(line.strip())
        prompt = "\n".join(prompt_lines).strip()
        if prompt:
            questions.append(
                ParsedPaperQuestion(
                    question_number=current_number,
                    section_title=section_title,
                    question_type=_infer_question_type(section_title, prompt),
                    prompt=prompt,
                    options=options,
                    answer=answer,
                    answer_confidence=0.75 if answer else 0,
                    verification_status="unverified",
                )
            )
        current_number = ""
        current_lines = []

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        heading_match = re.match(r"^(?:#{1,4}\s+|Section\s+\w+[:：.\s-]+)(.+)$", line, re.IGNORECASE)
        question_match = re.match(
            r"^(?:Question\s+|Q)?(\d{1,3})[.)、．\s]+(.+)$",
            line,
            re.IGNORECASE,
        )
        if heading_match and not question_match:
            flush_question()
            section_title = heading_match.group(1).strip() or "General"
            if all(section.title != section_title for section in sections):
                sections.append(
                    ParsedPaperSection(
                        title=section_title,
                        question_type=_infer_question_type(section_title, ""),
                    )
                )
            continue
        if question_match:
            flush_question()
            current_number = question_match.group(1)
            current_lines = [question_match.group(2)]
            continue
        if current_number:
            current_lines.append(line)
    flush_question()
    return PaperParseResult(
        exam_id=exam_id,
        title=title,
        year=year,
        source_url=source_url,
        sections=sections,
        questions=questions,
    )


def _infer_question_type(section_title: str, prompt: str) -> str:
    text = f"{section_title} {prompt}".lower()
    for question_type, keywords in (
        ("reading", ("reading", "passage", "阅读")),
        ("translation", ("translation", "translate", "翻译")),
        ("writing", ("writing", "essay", "写作", "作文")),
        ("cloze", ("cloze", "blank", "完形", "填空")),
        ("grammar", ("grammar", "语法")),
        ("vocabulary", ("vocabulary", "word", "词汇")),
    ):
        if any(keyword in text for keyword in keywords):
            return question_type
    return "unknown"
