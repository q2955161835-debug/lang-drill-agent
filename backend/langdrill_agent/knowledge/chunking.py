from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ..utils import estimate_tokens
from .models import KnowledgeChunkInput

_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
_PAGE_PATTERN = re.compile(r"^<!--\s*page:\s*(?P<page>\d+)\s*-->$", re.IGNORECASE)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    target_tokens: int = 400
    overlap_tokens: int = 80

    def __post_init__(self) -> None:
        if self.target_tokens < 1:
            raise ValueError("target_tokens must be positive")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens cannot be negative")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")


@dataclass(frozen=True, slots=True)
class _Segment:
    heading: str
    page: int | None
    content: str


def stable_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_markdown(
    text: str,
    config: ChunkingConfig | None = None,
) -> list[KnowledgeChunkInput]:
    active_config = config or ChunkingConfig()
    segments = _parse_segments(text, active_config.target_tokens)
    chunks: list[KnowledgeChunkInput] = []
    current: list[_Segment] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        content = "\n\n".join(segment.content for segment in current).strip()
        pages = [segment.page for segment in current if segment.page is not None]
        chunks.append(
            KnowledgeChunkInput(
                ordinal=len(chunks),
                heading=current[0].heading,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                content=content,
                content_hash=stable_hash(content),
                token_count=estimate_tokens(content),
            )
        )
        current = _overlap_segments(current, active_config.overlap_tokens)

    for segment in segments:
        if current and segment.heading != current[0].heading:
            flush()
            current = []
        projected = "\n\n".join(
            [*(item.content for item in current), segment.content]
        )
        if current and estimate_tokens(projected) > active_config.target_tokens:
            flush()
        current.append(segment)
    flush()
    return chunks


def _parse_segments(text: str, target_tokens: int) -> list[_Segment]:
    heading = ""
    page: int | None = None
    paragraph_lines: list[str] = []
    segments: list[_Segment] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = " ".join(line.strip() for line in paragraph_lines if line.strip()).strip()
        paragraph_lines.clear()
        for part in _split_oversized(paragraph, target_tokens):
            if part:
                segments.append(_Segment(heading=heading, page=page, content=part))

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for line in normalized.split("\n"):
        stripped = line.strip()
        heading_match = _HEADING_PATTERN.match(stripped)
        if heading_match:
            flush_paragraph()
            heading = heading_match.group("title").strip()
            continue
        page_match = _PAGE_PATTERN.match(stripped)
        if page_match:
            flush_paragraph()
            page = int(page_match.group("page"))
            continue
        if not stripped:
            flush_paragraph()
            continue
        paragraph_lines.append(stripped)
    flush_paragraph()
    return segments


def _split_oversized(text: str, target_tokens: int) -> list[str]:
    if estimate_tokens(text) <= target_tokens:
        return [text]
    sentences = [item.strip() for item in _SENTENCE_BOUNDARY.split(text) if item.strip()]
    if len(sentences) == 1:
        return _split_words(text, target_tokens)
    result: list[str] = []
    current = ""
    for sentence in sentences:
        if estimate_tokens(sentence) > target_tokens:
            if current:
                result.append(current)
                current = ""
            result.extend(_split_words(sentence, target_tokens))
            continue
        projected = f"{current} {sentence}".strip()
        if current and estimate_tokens(projected) > target_tokens:
            result.append(current)
            current = sentence
        else:
            current = projected
    if current:
        result.append(current)
    return result


def _split_words(text: str, target_tokens: int) -> list[str]:
    words = text.split()
    if not words:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    for word in words:
        projected = " ".join([*current, word])
        if current and estimate_tokens(projected) > target_tokens:
            parts.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        parts.append(" ".join(current))
    return parts


def _overlap_segments(segments: list[_Segment], overlap_tokens: int) -> list[_Segment]:
    if overlap_tokens <= 0:
        return []
    selected: list[_Segment] = []
    total = 0
    for segment in reversed(segments):
        segment_tokens = estimate_tokens(segment.content)
        if selected and total + segment_tokens > overlap_tokens:
            break
        selected.append(segment)
        total += segment_tokens
        if total >= overlap_tokens:
            break
    return list(reversed(selected))
