from __future__ import annotations

import re
from typing import Any


class ScreenshotImportService:
    OPTION_RE = re.compile(r"(?:^|\n)\s*([A-D])\s*[\.．、)]\s*(.+?)(?=\n\s*[A-D]\s*[\.．、)]|$)", re.S | re.I)

    def parse_text(self, text: str) -> dict[str, Any]:
        cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        options = []
        for match in self.OPTION_RE.finditer(cleaned):
            option_text = " ".join(match.group(2).split())
            if option_text:
                options.append(option_text)
        prompt = self.OPTION_RE.split(cleaned)[0].strip() if options else cleaned
        prompt = prompt or "Imported screenshot question"
        return {
            "prompt": prompt,
            "options": options[:4],
            "confidence": "structured" if len(options) >= 2 else "text_only",
            "raw_text": cleaned,
            "next_step": "请人工确认题干和选项；确认后可把文本发送到主聊天生成练习。",
        }
