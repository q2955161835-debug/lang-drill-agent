from __future__ import annotations

import json
import re

from .parser import (
    PaperParseResult,
    ParsedPaperPassage,
    ParsedPaperQuestion,
    ParsedPaperSection,
)


QUESTION_FENCE = "paper-question"
PASSAGE_FENCE = "paper-passage"
SECTION_PREFIX = "## Section:"
PASSAGE_PREFIX = "### Passage:"
QUESTION_PREFIX = "#### Question"


def render_paper_markdown(result: PaperParseResult) -> str:
    lines = [
        "---",
        "schema_version: 2",
        f"exam_id: {_scalar(result.exam_id)}",
        f"title: {_scalar(result.title)}",
        f"year: {result.year or ''}",
        f"source_url: {_scalar(result.source_url)}",
        "---",
        "# Paper",
        "",
    ]
    questions_by_section: dict[str, list[ParsedPaperQuestion]] = {}
    for question in result.questions:
        questions_by_section.setdefault(question.section_title, []).append(question)
    passages_by_section: dict[str, list[ParsedPaperPassage]] = {}
    for passage in result.passages:
        passages_by_section.setdefault(passage.section_title, []).append(passage)

    sections = list(result.sections)
    known_titles = {section.title for section in sections}
    for title in [*questions_by_section, *passages_by_section]:
        if title not in known_titles:
            sections.append(ParsedPaperSection(title=title or "General"))
            known_titles.add(title)
    if not sections and result.questions:
        sections = [ParsedPaperSection(title="General")]

    for section in sections:
        lines.extend([f"{SECTION_PREFIX} {section.title}", ""])
        section_meta = {
            "question_type": section.question_type,
            "source_page": section.source_page,
        }
        lines.extend(_metadata_block("paper-section", section_meta))
        for passage in passages_by_section.get(section.title, []):
            lines.extend([f"{PASSAGE_PREFIX} {passage.title or 'Untitled'}", ""])
            lines.extend(passage.content.strip().splitlines())
            lines.append("")
            lines.extend(
                _metadata_block(
                    PASSAGE_FENCE,
                    {"source_page": passage.source_page},
                )
            )
        for question in questions_by_section.get(section.title, []):
            lines.extend(_render_question(question))
    return "\n".join(lines).rstrip() + "\n"


def parse_paper_markdown(text: str) -> PaperParseResult:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    front_matter, body = _parse_front_matter(normalized)
    sections: list[ParsedPaperSection] = []
    passages: list[ParsedPaperPassage] = []
    questions: list[ParsedPaperQuestion] = []
    current_section = ""
    blocks = re.split(r"(?=^## Section:|^### Passage:|^#### Question)", body, flags=re.MULTILINE)
    for block in blocks:
        stripped = block.strip()
        if not stripped or stripped == "# Paper":
            continue
        first_line, _, remainder = stripped.partition("\n")
        if first_line.startswith(SECTION_PREFIX):
            current_section = first_line[len(SECTION_PREFIX) :].strip()
            metadata, _ = _extract_metadata(remainder, "paper-section")
            sections.append(
                ParsedPaperSection(
                    title=current_section,
                    question_type=str(metadata.get("question_type") or ""),
                    source_page=_optional_int(metadata.get("source_page")),
                )
            )
        elif first_line.startswith(PASSAGE_PREFIX):
            title = first_line[len(PASSAGE_PREFIX) :].strip()
            metadata, content = _extract_metadata(remainder, PASSAGE_FENCE)
            passages.append(
                ParsedPaperPassage(
                    title=title,
                    section_title=current_section,
                    content=content.strip(),
                    source_page=_optional_int(metadata.get("source_page")),
                )
            )
        elif first_line.startswith(QUESTION_PREFIX):
            question_number = first_line[len(QUESTION_PREFIX) :].strip()
            metadata, question_body = _extract_metadata(remainder, QUESTION_FENCE)
            prompt_lines: list[str] = []
            options: list[str] = []
            for line in question_body.strip().splitlines():
                option_match = re.match(r"^-\s+\[[A-Z0-9]+\]\s*(.+)$", line.strip())
                if option_match:
                    options.append(option_match.group(1).strip())
                elif line.strip():
                    prompt_lines.append(line.strip())
            answer = metadata.get("answer")
            if not isinstance(answer, dict):
                answer = {}
            verification_status = str(metadata.get("verification_status") or "unverified")
            if not answer:
                verification_status = "unverified"
            questions.append(
                ParsedPaperQuestion(
                    question_number=question_number,
                    section_title=current_section,
                    passage_title=str(metadata.get("passage_title") or ""),
                    question_type=str(metadata.get("question_type") or ""),
                    prompt="\n".join(prompt_lines).strip(),
                    options=options,
                    answer=answer,
                    explanation=str(metadata.get("explanation") or ""),
                    knowledge_tags=[
                        str(item) for item in metadata.get("knowledge_tags", []) if str(item).strip()
                    ],
                    difficulty=_optional_float(metadata.get("difficulty")),
                    source_page=_optional_int(metadata.get("source_page")),
                    answer_confidence=(
                        _optional_float(metadata.get("answer_confidence")) or 0
                    ),
                    verification_status=verification_status,
                )
            )
    if questions and not sections:
        sections = [ParsedPaperSection(title="General")]
        questions = [
            question.model_copy(update={"section_title": "General"}) for question in questions
        ]
    return PaperParseResult(
        schema_version=int(front_matter.get("schema_version") or 2),
        exam_id=str(front_matter.get("exam_id") or ""),
        title=str(front_matter.get("title") or "Paper"),
        year=_optional_int(front_matter.get("year")),
        source_url=str(front_matter.get("source_url") or ""),
        sections=sections,
        passages=passages,
        questions=questions,
    )


def _render_question(question: ParsedPaperQuestion) -> list[str]:
    lines = [f"{QUESTION_PREFIX} {question.question_number}", "", question.prompt.strip(), ""]
    for index, option in enumerate(question.options):
        label = chr(ord("A") + index)
        lines.append(f"- [{label}] {option}")
    if question.options:
        lines.append("")
    metadata = {
        "passage_title": question.passage_title,
        "question_type": question.question_type,
        "answer": question.answer,
        "explanation": question.explanation,
        "knowledge_tags": question.knowledge_tags,
        "difficulty": question.difficulty,
        "source_page": question.source_page,
        "answer_confidence": question.answer_confidence,
        "verification_status": question.verification_status if question.answer else "unverified",
    }
    lines.extend(_metadata_block(QUESTION_FENCE, metadata))
    return lines


def _metadata_block(name: str, metadata: dict[str, object]) -> list[str]:
    return [
        f"```{name}",
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2),
        "```",
        "",
    ]


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()
    return metadata, text[end + 5 :]


def _extract_metadata(text: str, fence: str) -> tuple[dict[str, object], str]:
    pattern = re.compile(rf"```{re.escape(fence)}\n(.*?)\n```", re.DOTALL)
    match = pattern.search(text)
    if not match:
        return {}, text
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    content = text[: match.start()] + text[match.end() :]
    return metadata, content


def _scalar(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ").strip()


def _optional_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def _optional_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None
