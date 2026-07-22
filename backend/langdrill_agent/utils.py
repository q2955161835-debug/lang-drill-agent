from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def loads(text: str, default: Any) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return default


def normalize_api_key(value: str) -> str:
    cleaned = (value or "").strip().strip('"\'').strip()
    for _ in range(2):
        next_value = re.sub(r"^(?:authorization\s*[:：]?\s*)?bearer\s*[:：]?\s*", "", cleaned, flags=re.IGNORECASE)
        next_value = re.sub(r"^(?:api[_ -]?key|apikey)\s*[:：]\s*", "", next_value, flags=re.IGNORECASE)
        if next_value == cleaned:
            break
        cleaned = next_value.strip()
    return cleaned


def validate_http_header_value(value: str, label: str) -> str:
    if "\r" in value or "\n" in value:
        raise RuntimeError(f"{label} 包含换行符，请只填写纯 API Key。")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RuntimeError(f"{label} 包含非 ASCII 字符，请只填写纯 API Key，不要包含中文冒号或说明文字。") from exc
    return value


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin = max(len(text) - cjk, 0)
    return max(1, cjk + latin // 4)
