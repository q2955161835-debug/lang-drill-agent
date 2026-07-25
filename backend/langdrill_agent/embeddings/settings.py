from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from ..config import env_file_path, load_settings
from ..utils import dumps, loads
from .models import EmbeddingIdentity, EmbeddingSettings, EmbeddingSettingsPatch

SETTING_KEY = "embeddings.settings"
HF_TOKEN_ENV = "LANGDRILL_EMBEDDING_HF_TOKEN"
CLOUD_API_KEY_ENV = "LANGDRILL_EMBEDDING_CLOUD_API_KEY"


def normalize_api_key(value: str) -> str:
    cleaned = (value or "").strip().strip('"\'').strip()
    for _ in range(2):
        next_value = re.sub(
            r"^(?:authorization\s*[:：]?\s*)?bearer\s*[:：]?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        next_value = re.sub(
            r"^(?:api[_ -]?key|apikey)\s*[:：]\s*",
            "",
            next_value,
            flags=re.IGNORECASE,
        )
        if next_value == cleaned:
            break
        cleaned = next_value.strip()
    if not cleaned:
        return cleaned
    if "\n" in cleaned or "\r" in cleaned:
        raise ValueError("EMBEDDING_API_KEY_INVALID")
    try:
        cleaned.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("EMBEDDING_API_KEY_INVALID") from exc
    return cleaned


def update_env_value(path: Path, key: str, value: str) -> None:
    current: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                current_key, current_value = line.split("=", 1)
                current[current_key.strip()] = current_value
    if value:
        current[key] = value
    else:
        current.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"{item_key}={item_value}" for item_key, item_value in current.items())
        + "\n",
        encoding="utf-8",
    )


class EmbeddingSettingsService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self) -> EmbeddingSettings:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (SETTING_KEY,),
        ).fetchone()
        payload = loads(row["value_json"], {}) if row else {}
        # Always invoke load_settings() so load_dotenv refreshes os.environ
        # from .env before we read the secret presence flag below.
        settings = load_settings()
        model_dir = payload.get("model_dir") or str(
            settings.user_data_dir / "models" / "embeddings"
        )
        api_key_configured = bool(os.getenv(HF_TOKEN_ENV, "").strip()) or bool(
            os.getenv(CLOUD_API_KEY_ENV, "").strip()
        )
        enabled_identity_raw = payload.get("enabled_identity")
        enabled_identity = (
            EmbeddingIdentity.model_validate(enabled_identity_raw)
            if enabled_identity_raw
            else None
        )
        return EmbeddingSettings(
            mode=payload.get("mode", "off"),
            model_id=payload.get("model_id", ""),
            revision=payload.get("revision", ""),
            dimensions=payload.get("dimensions", 0),
            model_dir=model_dir,
            base_url=payload.get("base_url", ""),
            api_key_configured=api_key_configured,
            enabled_identity=enabled_identity,
        )

    def save(self, patch: EmbeddingSettingsPatch) -> EmbeddingSettings:
        current = self.get()
        payload = current.model_copy(
            update=patch.model_dump(exclude={"api_key"}, exclude_none=True)
        )
        if patch.api_key is not None:
            key = (
                HF_TOKEN_ENV
                if payload.mode == "huggingface_cloud"
                else CLOUD_API_KEY_ENV
            )
            update_env_value(
                env_file_path(),
                key,
                normalize_api_key(patch.api_key),
            )
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                SETTING_KEY,
                dumps(payload.model_dump(exclude={"api_key_configured"})),
            ),
        )
        return self.get()

    def set_enabled_identity(
        self, identity: EmbeddingIdentity | None
    ) -> EmbeddingSettings:
        """Persist the enabled identity returned by a successful health probe.

        ``enabled_identity`` is stored in the same ``app_settings`` payload as
        the rest of the embedding settings so retrieval can compare the current
        runtime identity against the identity recorded at probe time.
        """

        current = self.get()
        payload = current.model_copy(update={"enabled_identity": identity})
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                SETTING_KEY,
                dumps(payload.model_dump(exclude={"api_key_configured"})),
            ),
        )
        return self.get()
