from pathlib import Path

from langdrill_agent.data_paths import DataPathService
from langdrill_agent.db import connect, init_db
from langdrill_agent.knowledge.repository import KnowledgeRepository
from langdrill_agent.memory.models import MemoryCandidate
from langdrill_agent.memory.repository import MemoryRepository


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


def test_migrating_user_data_preserves_memory_evidence_and_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_db = source_root / "data" / "langdrill_agent.db"
    init_db(source_db)
    with connect(source_db) as conn:
        repository = MemoryRepository(conn)
        item = repository.commit(
            repository.stage(
                MemoryCandidate(
                    category="preference",
                    content="User prefers concise worked examples",
                    normalized_key="preference:worked-examples",
                    confidence=0.95,
                    importance=0.8,
                    evidence_ids=["message:memory-migration"],
                )
            )
        )
        repository.update(item.id, "User prefers concise worked grammar examples")

    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(source_root))
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(source_db))
    monkeypatch.setenv("LANGDRILL_ENV_FILE", str(tmp_path / ".env"))

    result = DataPathService().configure_question_database_folder(
        str(target_root),
        migrate=True,
    )

    assert result["migrated"] is True
    with connect(target_root / "data" / "langdrill_agent.db") as conn:
        repository = MemoryRepository(conn)
        migrated = repository.get(item.id)
        evidence = repository.evidence(item.id)
        revisions = repository.revisions(item.id)

    assert migrated.content == "User prefers concise worked grammar examples"
    assert [row.evidence_ref for row in evidence] == ["message:memory-migration"]
    assert [row.operation for row in revisions] == ["ADD", "UPDATE"]
