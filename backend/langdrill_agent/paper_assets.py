from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .past_papers.markdown import render_paper_markdown
from .past_papers.parser import PaperParseResult, parse_extracted_paper_text
from .utils import dumps


BUILTIN_PAPER_EXAM_IDS = [
    "cet4",
    "cet6",
    "cft4",
    "cjt4",
    "cjt6",
    "ielts",
    "toefl",
    "gaokao-english",
    "custom",
]
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".jp2", ".webp", ".gif", ".bmp"}
MINERU_FLASH_SUFFIXES = IMAGE_SUFFIXES | {".pptx", ".xlsx"}
_RAPIDOCR_ENGINE: Any | None = None


def paper_root() -> Path:
    configured = os.getenv("LANGDRILL_PAPER_ROOT", "").strip()
    if not configured:
        return PROJECT_ROOT / "papers"
    root = Path(os.path.expandvars(configured)).expanduser()
    return root if root.is_absolute() else PROJECT_ROOT / root


def ensure_exam_paper_dirs(exam_id: str) -> dict[str, Path]:
    root = paper_root() / safe_path_part(exam_id)
    raw_dir = root / "raw"
    parsed_dir = root / "parsed"
    structured_dir = root / "structured"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)
    structured_dir.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "raw": raw_dir,
        "parsed": parsed_dir,
        "structured": structured_dir,
    }


def ensure_builtin_paper_dirs() -> None:
    for exam_id in BUILTIN_PAPER_EXAM_IDS:
        ensure_exam_paper_dirs(exam_id)


def safe_path_part(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return clean or "paper"


def paper_slug(exam_id: str, title: str, year: int | None = None, paper_id: str = "") -> str:
    parts = [safe_path_part(exam_id)]
    if year:
        parts.append(str(year))
    title_slug = safe_path_part(title)[:48]
    if title_slug:
        parts.append(title_slug)
    if paper_id:
        parts.append(safe_path_part(paper_id)[-12:])
    return "-".join(parts)


def relative_display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def source_manifest_text(
    *,
    exam_id: str,
    title: str,
    year: int | None,
    source_url: str,
    summary: str,
    question_types: list[str],
) -> str:
    type_lines = "\n".join(f"- {item}" for item in question_types) or "- 未记录"
    return (
        f"# {title}\n\n"
        f"- exam_id: {exam_id}\n"
        f"- year: {year or 'unknown'}\n"
        f"- source_url: {source_url or 'unrecorded'}\n"
        "- copyright_boundary: reference_only\n\n"
        "## 解析摘要\n\n"
        f"{summary or '待导入真实试卷后补充解析摘要。'}\n\n"
        "## 题型\n\n"
        f"{type_lines}\n"
    )


def extract_text_from_file(path: Path, *, language: str = "ch", mineru_token: str = "") -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8"), "text"
    if suffix == ".pdf":
        return _extract_pdf_text(path, language=language, mineru_token=mineru_token)
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix in IMAGE_SUFFIXES:
        return _extract_image_text(path, language=language, mineru_token=mineru_token)
    if suffix in MINERU_FLASH_SUFFIXES:
        return _extract_with_mineru(path, language=language, mineru_token=mineru_token)
    raise RuntimeError(f"暂不支持解析 {suffix or '无扩展名'} 文件，请先转换为 Markdown/TXT/PDF/DOCX 或图片。")


def _extract_pdf_text(path: Path, *, language: str, mineru_token: str) -> tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)
        if text.strip():
            return text, "pypdf"
    except Exception:
        pass

    try:
        return _extract_with_mineru(path, language=language, mineru_token=mineru_token)
    except RuntimeError as exc:
        raise RuntimeError(f"PDF 解析失败：{exc}") from exc


def _extract_image_text(path: Path, *, language: str, mineru_token: str) -> tuple[str, str]:
    mineru_error = ""
    try:
        return _extract_with_mineru(path, language=language, mineru_token=mineru_token)
    except RuntimeError as exc:
        mineru_error = str(exc)
    try:
        return _extract_with_rapidocr_image(path)
    except RuntimeError as exc:
        raise RuntimeError(f"图片 OCR 失败：{mineru_error}；RapidOCR 失败：{exc}") from exc


def _extract_with_mineru(path: Path, *, language: str, mineru_token: str = "") -> tuple[str, str]:
    mineru = shutil.which("mineru-open-api")
    if not mineru:
        raise RuntimeError("图片或复杂文档解析需要安装 MinerU CLI：npm install -g mineru-open-api。")
    mode = "extract" if mineru_token.strip() else "flash-extract"
    env = os.environ.copy()
    if mineru_token.strip():
        env["MINERU_TOKEN"] = mineru_token.strip()
    attempts = 2
    last_error = ""
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            [mineru, mode, str(path), "--language", language],
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
            env=env,
        )
        if result.returncode == 0:
            return result.stdout, f"mineru-open-api {mode}"
        last_error = result.stderr.strip()[:300] or result.stdout.strip()[:300]
        if attempt < attempts and _should_retry_mineru_error(last_error):
            time.sleep(1.5)
            continue
        break
    raise RuntimeError(f"MinerU 解析失败：{last_error}")


def _should_retry_mineru_error(message: str) -> bool:
    lower = message.lower()
    retry_markers = ["eof", "timeout", "timed out", "temporarily", "connection reset"]
    return any(marker in lower for marker in retry_markers)


def _extract_with_rapidocr_image(path: Path) -> tuple[str, str]:
    engine = _rapidocr_engine()
    try:
        result, _elapsed = engine(str(path))
    except Exception as exc:
        raise RuntimeError(f"RapidOCR 解析失败：{exc}") from exc
    lines = []
    for item in result or []:
        if len(item) < 2:
            continue
        text = str(item[1]).strip()
        if text:
            lines.append(text)
    if not lines:
        raise RuntimeError("RapidOCR 未识别到文本。")
    return "\n".join(lines), "rapidocr-onnxruntime"


def _rapidocr_engine() -> Any:
    global _RAPIDOCR_ENGINE
    if _RAPIDOCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
        except Exception as exc:
            raise RuntimeError("本地 RapidOCR 不可用，请安装 rapidocr-onnxruntime。") from exc
        _RAPIDOCR_ENGINE = RapidOCR()
    return _RAPIDOCR_ENGINE


def _extract_docx_text(path: Path) -> tuple[str, str]:
    try:
        import docx  # type: ignore
    except Exception as exc:
        raise RuntimeError("DOCX 解析需要安装 python-docx。") from exc
    document = docx.Document(str(path))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
    return text, "python-docx"


def parse_paper_text(
    text: str,
    *,
    exam_id: str,
    title: str,
    year: int | None,
    source_url: str,
    raw_path: str,
    parser: str,
    fallback_summary: str = "",
    fallback_question_types: list[str] | None = None,
    parse_status: str = "parsed",
    parse_error: str = "",
) -> dict[str, Any]:
    clean_text = normalize_text(text)
    sections = split_sections(clean_text)
    inferred_types = infer_question_types(
        "\n".join([title, clean_text, *(fallback_question_types or [])])
    )
    for item in fallback_question_types or []:
        if item and item not in inferred_types:
            inferred_types.append(item)
    parsed_sections = [section_payload(heading, body) for heading, body in sections]
    summary = fallback_summary.strip() or summarize_sections(parsed_sections)
    excerpts = extract_useful_excerpts(clean_text)
    return {
        "schema_version": 1,
        "exam_id": exam_id,
        "title": title,
        "year": year,
        "source_url": source_url,
        "raw_path": raw_path,
        "parser": parser,
        "parse_status": parse_status,
        "parse_error": parse_error,
        "parsed_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "question_types": inferred_types,
        "sections": parsed_sections,
        "usable_excerpts": excerpts,
        "stats": {
            "characters": len(clean_text),
            "lines": len(clean_text.splitlines()),
            "sections": len(parsed_sections),
            "excerpts": len(excerpts),
        },
    }


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def split_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = [("正文", [])]
    for line in lines:
        stripped = line.strip()
        if is_heading(stripped):
            if sections[-1][1] or sections[-1][0] != "正文":
                sections.append((clean_heading(stripped), []))
            else:
                sections[-1] = (clean_heading(stripped), [])
            continue
        sections[-1][1].append(line)
    return [(heading, "\n".join(body).strip()) for heading, body in sections if heading or body]


def is_heading(line: str) -> bool:
    if not line:
        return False
    return bool(
        re.match(r"^#{1,4}\s+\S+", line)
        or re.match(r"^(Part|Section)\s+[IVX0-9]+[:：.\s-]+", line, re.IGNORECASE)
        or re.match(r"^[一二三四五六七八九十]+[、.．]\s*\S+", line)
        or re.match(r"^第[一二三四五六七八九十0-9]+部分[:：\s-]*\S+", line)
    )


def clean_heading(line: str) -> str:
    clean = re.sub(r"^#{1,4}\s+", "", line.strip())
    return clean[:80]


def section_payload(heading: str, body: str) -> dict[str, Any]:
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    preview = " ".join(body_lines)[:700]
    return {
        "heading": heading,
        "question_types": infer_question_types(f"{heading}\n{body}"),
        "question_count": count_question_like_lines(body_lines),
        "content_preview": preview,
    }


def count_question_like_lines(lines: list[str]) -> int:
    count = 0
    for line in lines:
        if re.match(r"^(\d{1,3}|Q\d{1,3}|Question\s+\d{1,3})[.)、．\s]", line, re.IGNORECASE):
            count += 1
    return count


def infer_question_types(text: str) -> list[str]:
    lower = text.lower()
    patterns = [
        ("listening", ["听力", "listening"]),
        ("reading", ["阅读", "reading", "passage", "match headings"]),
        ("cloze", ["完形", "cloze", "blank", "选词填空"]),
        ("grammar", ["语法", "grammar"]),
        ("translation", ["翻译", "translation"]),
        ("writing", ["写作", "作文", "writing", "essay"]),
        ("speaking", ["口语", "speaking"]),
        ("vocabulary", ["词汇", "vocabulary", "word", "lexical"]),
    ]
    result = []
    for type_id, keywords in patterns:
        if any(keyword.lower() in lower for keyword in keywords):
            result.append(type_id)
    return result


def summarize_sections(sections: list[dict[str, Any]]) -> str:
    if not sections:
        return "未解析到可用章节。"
    headings = [section["heading"] for section in sections[:6]]
    return "已解析章节：" + "、".join(headings)


def extract_useful_excerpts(text: str, limit: int = 24) -> list[dict[str, str]]:
    excerpts: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = re.sub(r"\s+", " ", line).strip()
        if not (12 <= len(stripped) <= 240):
            continue
        if not looks_useful_excerpt(stripped):
            continue
        excerpts.append({"text": stripped, "boundary": "short_excerpt_for_reference"})
        if len(excerpts) >= limit:
            break
    return excerpts


def looks_useful_excerpt(line: str) -> bool:
    lower = line.lower()
    return bool(
        "____" in line
        or "?" in line
        or "which " in lower
        or "choose " in lower
        or "translate " in lower
        or re.match(r"^\d{1,3}[.)、．\s]", line)
    )


def write_parsed_json(parsed_path: Path, payload: dict[str, Any]) -> None:
    parsed_path.write_text(dumps(payload), encoding="utf-8")


def write_paper_v2_assets(
    text: str,
    *,
    exam_id: str,
    title: str,
    year: int | None,
    source_url: str,
    markdown_path: Path,
    structured_path: Path,
) -> PaperParseResult:
    result = parse_extracted_paper_text(
        text,
        exam_id=exam_id,
        title=title,
        year=year,
        source_url=source_url,
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    structured_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_staging = markdown_path.with_name(markdown_path.name + ".staging")
    structured_staging = structured_path.with_name(structured_path.name + ".staging")
    try:
        markdown_staging.write_text(render_paper_markdown(result), encoding="utf-8")
        structured_staging.write_text(
            dumps(result.model_dump(mode="json")),
            encoding="utf-8",
        )
        markdown_staging.replace(markdown_path)
        structured_staging.replace(structured_path)
    except Exception:
        markdown_staging.unlink(missing_ok=True)
        structured_staging.unlink(missing_ok=True)
        raise
    return result
