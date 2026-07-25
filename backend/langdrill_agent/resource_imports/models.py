from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ImportTarget = Literal["knowledge", "past_paper"]
ImportStatus = Literal[
    "staged", "parsing", "preview_ready", "failed", "confirmed", "cancelled"
]


class ResourceImportPreview(BaseModel):
    title: str
    language: str = ""
    year: int | None = None
    parser: str
    text_preview: str
    characters: int
    pages: int | None = None
    chunk_count: int = 0
    question_count: int = 0
    question_types: list[str] = Field(default_factory=list)
    answer_confidence: float = 0
    warnings: list[str] = Field(default_factory=list)


class ResourceImportRecord(BaseModel):
    id: str
    target: ImportTarget
    filename: str
    mime_type: str
    size_bytes: int
    staged_path: str
    extracted_path: str = ""
    status: ImportStatus
    parser: str = ""
    preview: ResourceImportPreview | None = None
    error_code: str = ""
    error_detail: str = ""
    created_at: str
    updated_at: str
    expires_at: str
