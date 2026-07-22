from pathlib import Path

from langdrill_agent.data_paths import DataPathService
from langdrill_agent.db import connect, init_db
from langdrill_agent.knowledge.repository import KnowledgeRepository


def test_migrating_user_data_copies_knowledge_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_db = source_root / "data" / "langdrill_agent.db"
    source_raw = source_root / "knowledge" / "raw" / "document.md"
    source_parsed = source_root / "knowledge" / "parsed" / "document.md"
    source_raw.parent.mkdir(parents=True)
    source_parsed.parent.mkdir(parents=True)
    source_raw.write_text("raw document", encoding="utf-8")
    source_parsed.write_text("# Parsed\n\ncontent", encoding="utf-8")
    init_db(source_db)
    with connect(source_db) as conn:
        document = KnowledgeRepository(conn).create_document(
            title="Document",
            source_name="document.md",
            mime_type="text/markdown",
            content_hash="sha256:document",
            raw_path=str(source_raw),
            parsed_path=str(source_parsed),
            status="ready",
        )

    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(source_root))
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(source_db))
    monkeypatch.setenv("LANGDRILL_ENV_FILE", str(tmp_path / ".env"))

    result = DataPathService().configure_question_database_folder(
        str(target_root),
        migrate=True,
    )

    assert result["migrated"] is True
    assert (target_root / "knowledge" / "raw" / "document.md").read_text(encoding="utf-8") == "raw document"
    assert (target_root / "knowledge" / "parsed" / "document.md").read_text(encoding="utf-8") == "# Parsed\n\ncontent"
    with connect(target_root / "data" / "langdrill_agent.db") as conn:
        migrated = KnowledgeRepository(conn).get_document(document.id)
    assert Path(migrated.raw_path) == target_root / "knowledge" / "raw" / "document.md"
    assert Path(migrated.parsed_path) == target_root / "knowledge" / "parsed" / "document.md"
