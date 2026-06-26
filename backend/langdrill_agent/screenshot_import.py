from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

from .utils import dumps, loads, new_id


logger = logging.getLogger(__name__)


class ScreenshotImportService:
    OPTION_RE = re.compile(r"(?:^|\n)\s*([A-D])\s*[\.．、)]\s*(.+?)(?=\n\s*[A-D]\s*[\.．、)]|$)", re.S | re.I)
    TERM_RE = re.compile(r"^[A-Za-z][A-Za-z'-]{1,40}$")
    PART_OF_SPEECH_RE = re.compile(r"^(?:n|v|vi|vt|adj|adv|prep|conj|pron|num|art|aux)\.", re.I)

    def parse_text(self, text: str, source_image_path: str = "") -> dict[str, Any]:
        cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        options = []
        for match in self.OPTION_RE.finditer(cleaned):
            option_text = " ".join(match.group(2).split())
            if option_text:
                options.append(option_text)
        prompt = self.OPTION_RE.split(cleaned)[0].strip() if options else cleaned
        prompt = prompt or "Imported screenshot question"
        words = self._parse_vocabulary_words(cleaned)
        confidence = "structured" if len(options) >= 2 else "text_only"
        if words and not options:
            confidence = "vocabulary_list"
        logger.info(
            "parsed screenshot text",
            extra={"confidence": confidence, "word_count": len(words), "option_count": len(options)},
        )
        return {
            "prompt": prompt,
            "options": options[:4],
            "words": words,
            "confidence": confidence,
            "raw_text": cleaned,
            "source_image_path": source_image_path,
            "next_step": "请人工确认题干和选项；确认后可把文本发送到主聊天生成练习。",
        }

    def import_words(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        parsed: dict[str, Any],
        exam_id: str,
        source_image_path: str = "",
    ) -> int:
        words = parsed.get("words") or []
        imported = 0
        for item in words:
            term = str(item.get("term", "")).strip()
            if not term:
                continue
            meaning = str(item.get("meaning", "")).strip()
            existing = conn.execute(
                """
                SELECT id FROM knowledge_items
                WHERE term=? AND exam_id=? AND source_scope='screenshot_import'
                LIMIT 1
                """,
                (term, exam_id),
            ).fetchone()
            notes = dumps(
                {
                    "source": "screenshot_import",
                    "session_id": session_id,
                    "source_image_path": source_image_path or parsed.get("source_image_path", ""),
                }
            )
            if existing:
                conn.execute(
                    """
                    UPDATE knowledge_items
                    SET meaning=?, notes=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (meaning, notes, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO knowledge_items
                    (id, kind, term, meaning, notes, exam_id, source_scope, mastery_score)
                    VALUES (?, 'word', ?, ?, ?, ?, 'screenshot_import', 0.2)
                    """,
                    (new_id("kn"), term, meaning, notes, exam_id),
                )
            imported += 1
        if imported:
            self._append_session_plan(conn, session_id, words[:20])
        logger.info("imported screenshot words", extra={"session_id": session_id, "count": imported})
        return imported

    def _append_session_plan(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        words: list[dict[str, str]],
    ) -> None:
        row = conn.execute(
            "SELECT daily_plan_json FROM study_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        plan = loads(row["daily_plan_json"], {}) if row else {}
        new_content = list(plan.get("new_content", []) or [])
        for item in words:
            term = item.get("term", "")
            meaning = item.get("meaning", "")
            summary = f"{term}: {meaning}".strip(": ")
            if summary and summary not in new_content:
                new_content.append(summary)
        plan["new_content"] = new_content
        plan["status"] = "screenshot_words_imported"
        plan["algorithm"] = "screenshot_vocabulary_import_v1"
        conn.execute(
            """
            UPDATE study_sessions
            SET daily_plan_json=?, status='active', updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (dumps(plan), session_id),
        )

    def _parse_vocabulary_words(self, cleaned: str) -> list[dict[str, str]]:
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        words: list[dict[str, str]] = []
        current_term = ""
        current_meaning: list[str] = []

        def flush() -> None:
            nonlocal current_term, current_meaning
            meaning = " ".join(current_meaning).strip()
            if current_term and meaning:
                words.append({"term": current_term, "meaning": meaning})
            current_term = ""
            current_meaning = []

        for line in lines:
            if self._looks_like_term(line):
                flush()
                current_term = line.lower()
                continue
            if current_term and self._looks_like_meaning(line):
                current_meaning.append(line)
        flush()
        return words

    def _looks_like_term(self, line: str) -> bool:
        return bool(self.TERM_RE.fullmatch(line)) and line.lower() not in {"qq", "abc"}

    def _looks_like_meaning(self, line: str) -> bool:
        return bool(self.PART_OF_SPEECH_RE.match(line)) or any("\u4e00" <= char <= "\u9fff" for char in line)
