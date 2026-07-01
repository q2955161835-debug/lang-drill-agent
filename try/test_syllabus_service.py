from __future__ import annotations

from pathlib import Path

from langdrill_agent.db import init_db, transaction
from langdrill_agent.services import SourceService, SyllabusService


OFFICIAL_SYLLABUS_HTML = """
<a>全国大学法语四级考试大纲（2023版）</a>
<a>《全国大学日语四、六级考试大纲》 （2024年启用）</a>
<a>《全国大学英语四、六级考试大纲（2016年修订版）》</a>
"""


def test_exam_options_include_builtin_and_custom_choice(tmp_path: Path) -> None:
    db_path = tmp_path / "syllabus.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        options = SyllabusService(conn).exam_options()

    ids = [item["id"] for item in options]
    assert ids[:8] == [
        "cet4",
        "cet6",
        "cft4",
        "cjt4",
        "cjt6",
        "ielts",
        "toefl",
        "gaokao-english",
    ]
    assert "custom" in ids


def test_parse_official_syllabus_candidates_keeps_language_titles() -> None:
    candidates = SyllabusService.parse_official_syllabus_candidates(
        OFFICIAL_SYLLABUS_HTML, SyllabusService.CET_SYLLABUS_PAGE
    )

    assert {
        "title": "全国大学法语四级考试大纲（2023版）",
        "year": 2023,
        "url": SyllabusService.CET_SYLLABUS_PAGE,
    } in candidates
    assert {
        "title": "《全国大学英语四、六级考试大纲（2016年修订版）》",
        "year": 2016,
        "url": SyllabusService.CET_SYLLABUS_PAGE,
    } in candidates


def test_manual_syllabus_check_keeps_english_2016_when_french_2023_exists(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "syllabus.db"
    init_db(db_path)

    monkeypatch.setattr(
        SyllabusService,
        "_fetch_official_syllabus_candidates",
        lambda self, url: SyllabusService.parse_official_syllabus_candidates(
            OFFICIAL_SYLLABUS_HTML, url
        ),
    )

    with transaction(db_path) as conn:
        SourceService(conn).seed_common_sources()
        service = SyllabusService(conn)
        status_before = service.status("cet4")
        result = service.manual_check("cet4")
        status_after = service.status("cet4")

    assert status_before["current_year"] == 2016
    assert result["changed"] is False
    assert "已是最新考纲" in result["message"]
    assert status_after["sources"][0]["year"] == 2016
    assert "法语" not in status_after["current_title"]


def test_manual_syllabus_check_recognizes_french_2023_from_official_page(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "syllabus.db"
    init_db(db_path)

    monkeypatch.setattr(
        SyllabusService,
        "_fetch_official_syllabus_candidates",
        lambda self, url: SyllabusService.parse_official_syllabus_candidates(
            OFFICIAL_SYLLABUS_HTML, url
        ),
    )

    with transaction(db_path) as conn:
        SourceService(conn).seed_common_sources()
        service = SyllabusService(conn)
        result = service.manual_check("cft4")
        status_after = service.status("cft4")

    assert result["changed"] is False
    assert "已是最新考纲" in result["message"]
    assert status_after["current_year"] == 2023
    assert status_after["current_title"] == "全国大学法语四级考试大纲（2023版）"
