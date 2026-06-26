from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class AnkiConnectError(RuntimeError):
    pass


class AnkiConnectClient:
    def __init__(self, url: str = "http://127.0.0.1:8765"):
        self.url = url

    def request(self, action: str, params: dict[str, Any] | None = None) -> Any:
        payload = json.dumps({"action": action, "version": 6, "params": params or {}}).encode("utf-8")
        req = urllib.request.Request(self.url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AnkiConnectError("AnkiConnect 未连接。请先打开 Anki，并确认已安装 AnkiConnect 插件。") from exc
        if data.get("error"):
            raise AnkiConnectError(str(data["error"]))
        return data.get("result")

    def deck_names(self) -> list[str]:
        result = self.request("deckNames")
        return result if isinstance(result, list) else []

    def ensure_deck(self, deck_name: str) -> None:
        self.request("createDeck", {"deck": deck_name})

    def add_notes(self, deck_name: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        self.ensure_deck(deck_name)
        notes = []
        for item in items:
            term = str(item.get("term") or "").strip()
            if not term:
                continue
            back_parts = [
                str(item.get("meaning") or "").strip(),
                str(item.get("notes") or "").strip(),
                f"Mastery: {float(item.get('mastery_score') or 0):.2f}",
            ]
            notes.append(
                {
                    "deckName": deck_name,
                    "modelName": "Basic",
                    "fields": {
                        "Front": term,
                        "Back": "<br>".join(part for part in back_parts if part),
                    },
                    "tags": ["langdrill", str(item.get("exam_id") or "cet4")],
                    "options": {"allowDuplicate": False},
                }
            )
        if not notes:
            return {"created": 0, "note_ids": []}
        result = self.request("addNotes", {"notes": notes})
        created = len([item for item in result or [] if item])
        return {"created": created, "note_ids": result or []}
