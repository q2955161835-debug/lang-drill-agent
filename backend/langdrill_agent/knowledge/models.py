from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    queued = "queued"
    importing = "importing"
    ready = "ready"
    failed = "failed"
    deleted = "deleted"


class KnowledgeDocument(BaseModel):
    id: str
    title: str
    source_name: str
    mime_type: str
    raw_path: str = ""
    parsed_path: str = ""
    content_hash: str
    language: str = ""
    status: DocumentStatus = DocumentStatus.queued
    parser: str = ""
    parser_version: str = ""
    error_code: str = ""
    created_at: str = ""
    updated_at: str = ""


class KnowledgeChunkInput(BaseModel):
    ordinal: int = Field(ge=0)
    heading: str = ""
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    content: str = Field(min_length=1)
    content_hash: str
    token_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeChunk(KnowledgeChunkInput):
    id: str
    document_id: str
