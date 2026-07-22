from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.paper_assets import source_manifest_text
from langdrill_agent.past_papers.legacy_migration import migrate_legacy_manifests
from langdrill_agent.past_papers.repository import PastPaperRepository
from langdrill_agent.services import PastPaperService
from langdrill_agent.utils import dumps


def _seed_manifest(conn, root: Path, *, modified: bool) -> Path:
    raw_path = root / "cet4" / "raw" / "2025.md"
    parsed_path = root / "cet4" / "parsed" / "2025.json"
    raw_path.parent.mkdir(parents=True)
    parsed_path.parent.mkdir(parents=True)
    manifest = source_manifest_text(
        exam_id="cet4",
        title="大学英语四级 2025 年真题参考索引",
        year=2025,
        source_url="https://source.test/exams",
        summary="默认近三年真题索引，用于参考大学英语四级的题型结构、难度和常见主题。",
        question_types=["reading", "translation"],
    )
    raw_path.write_text(manifest + ("\n用户补充" if modified else ""), encoding="utf-8")
    parsed_path.write_text("{}", encoding="utf-8")
    metadata = {
        "summary": "默认近三年真题索引，用于参考大学英语四级的题型结构、难度和常见主题。",
        "question_types": ["reading", "translation"],
        "import_mode": "default_recent_source_manifest",
        "raw_path": str(raw_path),
        "parsed_path": str(parsed_path),
        "parse_status": "source_manifest_only",
    }
    conn.execute(
        """
        INSERT INTO exam_assets
        (id, exam_id, asset_type, title, year, source_url, local_path,
         trusted_level, copyright_boundary, metadata_json)
        VALUES ('paper_cet4_2025', 'cet4', 'past_paper', ?, 2025, ?, ?,
                'needs_verification', 'style_reference_only', ?)
        """,
        (
            "大学英语四级 2025 年真题参考索引",
            "https://source.test/exams",
            str(raw_path),
            dumps(metadata),
        ),
    )
    return raw_path


def test_generated_manifest_moves_to_remote_catalog(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    papers_root = tmp_path / "papers"
    init_db(db_path)

    with connect(db_path) as conn:
        raw_path = _seed_manifest(conn, papers_root, modified=False)
        report = migrate_legacy_manifests(conn, papers_root)

        assert report.catalogued == 1
        assert report.removed_generated_files == 2
        assert not raw_path.exists()
        assert PastPaperRepository(conn).list_sources("cet4")
        assert PastPaperRepository(conn).list_documents("cet4") == []


def test_status_does_not_reseed_placeholder_papers(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "papers.db"
    papers_root = tmp_path / "papers"
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(papers_root))
    init_db(db_path)

    with connect(db_path) as conn:
        status = PastPaperService(conn).status("cet4")

        assert status["remote_count"] == 0
        assert status["installed_count"] == 0
        assert status["papers"] == []
        assert not list(papers_root.rglob("*.md"))
        assert conn.execute("SELECT COUNT(*) FROM exam_assets").fetchone()[0] == 0


def test_user_modified_manifest_is_preserved(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    papers_root = tmp_path / "papers"
    init_db(db_path)

    with connect(db_path) as conn:
        raw_path = _seed_manifest(conn, papers_root, modified=True)
        report = migrate_legacy_manifests(conn, papers_root)

        assert report.preserved_modified == 1
        assert raw_path.exists()
        assert conn.execute("SELECT COUNT(*) FROM exam_assets").fetchone()[0] == 1
