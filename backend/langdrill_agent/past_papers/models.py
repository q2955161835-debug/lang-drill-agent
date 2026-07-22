from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PaperSourceInput(BaseModel):
    id: str
    exam_id: str
    title: str
    source_url: str
    year: int | None = None
    session: str = ""
    set_number: int | None = None
    answer_source_url: str = ""
    source_host: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperSource(PaperSourceInput):
    discovered_at: str = ""
    updated_at: str = ""


class PaperDocumentInput(BaseModel):
    source_id: str | None = None
    exam_id: str
    title: str
    year: int | None = None
    session: str = ""
    set_number: int | None = None
    source_url: str = ""
    raw_path: str = ""
    markdown_path: str = ""
    structured_path: str = ""
    content_hash: str
    status: str = "queued"
    parser: str = ""
    parser_version: str = ""
    error_code: str = ""


class PaperDocument(PaperDocumentInput):
    id: str
    created_at: str = ""
    updated_at: str = ""


class PaperQuestionInput(BaseModel):
    question_number: str = ""
    question_type: str
    prompt: str = Field(min_length=1)
    options: list[str] = Field(default_factory=list)
    answer: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""
    knowledge_tags: list[str] = Field(default_factory=list)
    difficulty: float | None = Field(default=None, ge=0, le=1)
    source_page: int | None = Field(default=None, ge=1)
    answer_confidence: float = Field(default=0, ge=0, le=1)
    verification_status: str = "unverified"
    content_hash: str = ""


class PaperQuestion(PaperQuestionInput):
    id: str
    document_id: str
    section_id: str | None = None
    passage_id: str | None = None


class DistillationFinding(BaseModel):
    id: str
    exam_id: str
    version: int
    status: str
    finding_type: str
    label: str
    evidence_count: int
    paper_count: int
    years: list[int] = Field(default_factory=list)
    confidence: float = 0
    evidence_question_ids: list[str] = Field(default_factory=list)


class CoverageLedger(BaseModel):
    exam_id: str
    question_type: str
    enabled: bool = True
    rolling_seen: int = 0
    rolling_selected: int = 0
    coverage_debt: float = 0
