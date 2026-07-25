from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

EmbeddingMode = Literal["off", "local", "huggingface_cloud", "openai_compatible"]


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
