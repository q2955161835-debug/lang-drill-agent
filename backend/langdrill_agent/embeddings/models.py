from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

EmbeddingMode = Literal["off", "local", "huggingface_cloud", "openai_compatible"]
EmbeddingJobKind = Literal["model", "runtime"]
EmbeddingJobStatus = Literal[
    "pending", "running", "completed", "failed", "cancelled"
]


class EmbeddingIdentity(BaseModel):
    provider: str
    model_id: str
    revision: str
    dimensions: int = Field(ge=1)

    @property
    def key(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class EmbeddingSettings(BaseModel):
    mode: EmbeddingMode = "off"
    model_id: str = ""
    revision: str = ""
    dimensions: int = 0
    model_dir: str = ""
    base_url: str = ""
    api_key_configured: bool = False
    enabled_identity: EmbeddingIdentity | None = None


class EmbeddingSettingsPatch(BaseModel):
    mode: EmbeddingMode | None = None
    model_id: str | None = None
    revision: str | None = None
    dimensions: int | None = Field(default=None, ge=0)
    model_dir: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class EmbeddingModelSummary(BaseModel):
    model_id: str
    revision: str = ""
    license: str = ""
    library: str = ""
    pipeline_tag: str = ""
    downloads: int = 0
    likes: int = 0
    size_bytes: int = 0
    compatible: bool = False
    blockers: list[str] = Field(default_factory=list)
    recommended: bool = False


class EmbeddingModelDetail(EmbeddingModelSummary):
    download_files: list[str] = Field(default_factory=list)


class EmbeddingDownloadJob(BaseModel):
    id: str
    kind: EmbeddingJobKind = "model"
    model_id: str = ""
    revision: str = ""
    target_dir: str = ""
    status: EmbeddingJobStatus
    files_total: int = 0
    files_completed: int = 0
    bytes_downloaded: int = 0
    cancel_requested: bool = False
    error_code: str = ""
    error_detail: str = ""
    created_at: str = ""
    updated_at: str = ""
