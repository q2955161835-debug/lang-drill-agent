from __future__ import annotations

import sqlite3

from pydantic import BaseModel

from ..utils import dumps, loads

SAFE_RUNTIME_TOOL_NAMES = frozenset({"runtime.review"})


class CapabilityRuntimeSettings(BaseModel):
    enabled: bool = False


def safe_runtime_tool_names() -> list[str]:
    return sorted(SAFE_RUNTIME_TOOL_NAMES)


class CapabilityRuntimeSettingsService:
    SETTINGS_KEY = "runtime.capabilities"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self) -> CapabilityRuntimeSettings:
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (self.SETTINGS_KEY,),
        ).fetchone()
        payload = loads(row["value_json"], {}) if row else {}
        return CapabilityRuntimeSettings(**payload)

    def save(self, *, enabled: bool) -> CapabilityRuntimeSettings:
        settings = CapabilityRuntimeSettings(enabled=enabled)
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (self.SETTINGS_KEY, dumps(settings.model_dump(mode="json"))),
        )
        return settings
