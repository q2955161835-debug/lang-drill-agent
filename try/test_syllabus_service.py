from __future__ import annotations

from pathlib import Path

from langdrill_agent.db import init_db, transaction
from langdrill_agent.services import SourceService, SyllabusService


def test_exam_options_include_builtin_and_custom_choice(tmp_path: Path) -> None:
    db_path = tmp_path / "syllabus.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        options = SyllabusService(conn).exam_options()

    ids = [item["id"] for item in options]
    assert ids[:7] == ["cet4", "cet6", "cjt4", "cjt6", "ielts", "toefl", "gaokao-english"]
    assert "custom" in ids


def test_manual_syllabus_check_keeps_old_years_and_reports_latest(tmp_path: Path) -> None:
    db_path = tmp_path / "syllabus.db"
    init_db(db_path)

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
