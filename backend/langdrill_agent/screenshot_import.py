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
    INCOMPLETE_TERM_RE = re.compile(r"^[A-Za-z][A-Za-z'-]{1,40}[\.．…]$")
    INLINE_POS_RE = re.compile(
        r"^([A-Za-z][A-Za-z'-]{1,40})\s+"
        r"((?:n|v|vi|vt|adj|adv|prep|conj|pron|num|art|aux)\..+)$",
        re.I,
    )
    INLINE_SEPARATOR_RE = re.compile(r"^([A-Za-z][A-Za-z'-]{1,40})\s*[:：]\s*(.+)$")
    PART_OF_SPEECH_RE = re.compile(r"^(?:n|v|vi|vt|adj|adv|prep|conj|pron|num|art|aux)\.", re.I)
    UI_NOISE_EXACT = {
        "abc",
        "单词列表",
        "展开",
        "速听",
        "速刷",
        "单词选义",
        "拼写",
        "听写",
    }
    UI_NOISE_PATTERNS = (
        re.compile(r"^截图导入文本[:：]?$"),
        re.compile(r"^\d{1,2}:\d{2}$"),
        re.compile(r"^\d{1,3}%?$"),
        re.compile(r"^共\s*\d+\s*词$"),
        re.compile(r"^按.+排序$"),
        re.compile(r"^已思考\s*\d+\s*s\s*[>＞]?$", re.I),
    )
    COMMON_REPAIR_TERMS = {
        "adequate",
        "altogether",
        "aware",
        "blood",
        "bow",
        "champion",
        "class",
        "contrary",
        "course",
        "cultivate",
        "discard",
        "evident",
        "executive",
        "extreme",
        "fall",
        "fierce",
        "forever",
        "hence",
        "laser",
        "loyalty",
        "material",
        "process",
        "research",
        "robe",
        "root",
        "skin",
        "state",
        "vigorous",
        "waterfall",
    }

    def parse_text(self, text: str, source_image_path: str = "") -> dict[str, Any]:
        cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        options = []
        for match in self.OPTION_RE.finditer(cleaned):
            option_text = " ".join(match.group(2).split())
            if option_text:
                options.append(option_text)
        prompt = self.OPTION_RE.split(cleaned)[0].strip() if options else cleaned
        prompt = prompt or "Imported screenshot question"
        words, diagnostics = self._parse_vocabulary_words(cleaned)
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
            "diagnostics": diagnostics,
            "confidence": confidence,
            "raw_text": cleaned,
            "source_image_path": source_image_path,
            "next_step": self._next_step(confidence, diagnostics),
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

    def _parse_vocabulary_words(self, cleaned: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        words: list[dict[str, str]] = []
        skipped_lines: list[dict[str, str]] = []
        repaired_terms: list[dict[str, str]] = []
        current_term = ""
        current_meaning: list[str] = []

        def flush() -> None:
            nonlocal current_term, current_meaning
            meaning = " ".join(current_meaning).strip()
            if current_term and meaning:
                words.append({"term": current_term, "meaning": meaning})
            current_term = ""
            current_meaning = []

        def reset_current(reason: str = "") -> None:
            nonlocal current_term, current_meaning
            if current_term and current_meaning:
                flush()
            elif current_term and reason:
                skipped_lines.append({"text": current_term, "reason": reason})
                current_term = ""
                current_meaning = []

        for line in lines:
            if self._is_ui_noise(line):
                if current_term and current_meaning:
                    flush()
                continue
            inline_word = self._parse_inline_word(line)
            if inline_word:
                reset_current("missing_meaning")
                words.append(inline_word)
                continue
            if self._looks_like_term(line):
                reset_current("missing_meaning")
                current_term = line.lower()
                continue
            repaired_term = self._repair_incomplete_term(line)
            if repaired_term:
                reset_current("missing_meaning")
                current_term = repaired_term
                repaired_terms.append({"text": line, "term": repaired_term, "reason": "ocr_clipped_term_repaired"})
                continue
            if self._looks_like_incomplete_term(line):
                reset_current()
                skipped_lines.append({"text": line, "reason": "ocr_clipped_term"})
                continue
            if current_term and self._looks_like_meaning(line):
                current_meaning.append(line)
                continue
            if self._looks_like_meaning(line):
                skipped_lines.append({"text": line, "reason": "meaning_without_term"})
                continue
            reset_current("unrecognized_line_interrupted_entry")
        reset_current("missing_meaning")
        diagnostics = {
            "skipped_lines": skipped_lines[:20],
            "repaired_terms": repaired_terms[:20],
            "skipped_count": len(skipped_lines),
            "repaired_count": len(repaired_terms),
        }
        return words, diagnostics

    def _looks_like_term(self, line: str) -> bool:
        return bool(self.TERM_RE.fullmatch(line)) and line.lower() not in {"qq", "abc"}

    def _looks_like_incomplete_term(self, line: str) -> bool:
        return bool(self.INCOMPLETE_TERM_RE.fullmatch(line))

    def _looks_like_meaning(self, line: str) -> bool:
        return bool(self.PART_OF_SPEECH_RE.match(line)) or any("\u4e00" <= char <= "\u9fff" for char in line)

    def _parse_inline_word(self, line: str) -> dict[str, str] | None:
        for pattern in (self.INLINE_POS_RE, self.INLINE_SEPARATOR_RE):
            match = pattern.match(line)
            if not match:
                continue
            term = match.group(1).strip().lower()
            meaning = match.group(2).strip()
            if term and meaning and self._looks_like_meaning(meaning):
                return {"term": term, "meaning": meaning}
        return None

    def _is_ui_noise(self, line: str) -> bool:
        normalized = line.strip()
        if normalized in self.UI_NOISE_EXACT or normalized.lower() in self.UI_NOISE_EXACT:
            return True
        return any(pattern.match(normalized) for pattern in self.UI_NOISE_PATTERNS)

    def _repair_incomplete_term(self, line: str) -> str:
        if not self._looks_like_incomplete_term(line):
            return ""
        prefix = re.sub(r"[^a-z'-]", "", line.lower())
        if len(prefix) < 5:
            return ""
        matches = [term for term in self.COMMON_REPAIR_TERMS if term.startswith(prefix)]
        return matches[0] if len(matches) == 1 else ""

    def _next_step(self, confidence: str, diagnostics: dict[str, Any]) -> str:
        if confidence == "vocabulary_list":
            if diagnostics.get("skipped_count") or diagnostics.get("repaired_count"):
                return "已尽量过滤手机界面噪声并修复疑似截断词；请人工确认词条后导入练习。"
            return "已识别为词表；确认后可直接导入并开始练习。"
        return "请人工确认题干和选项；确认后可把文本发送到主聊天生成练习。"
