from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.knowledge.chunking import ChunkingConfig, chunk_markdown
from langdrill_agent.knowledge.ingestion import KnowledgeIngestionService
from langdrill_agent.knowledge.repository import KnowledgeRepository
from langdrill_agent.runtime.repository import AgentRunRepository


def test_chunking_preserves_heading_and_page_marker() -> None:
    text = "# Unit 1\n<!-- page: 2 -->\n" + ("alpha beta gamma. " * 120)

    chunks = chunk_markdown(text, ChunkingConfig(target_tokens=80, overlap_tokens=10))

    assert len(chunks) > 1
    assert all(chunk.heading == "Unit 1" for chunk in chunks)
    assert chunks[0].page_start == 2
    assert chunks[0].content_hash.startswith("sha256:")


def test_chunking_is_deterministic() -> None:
    text = "# A\nOne paragraph.\n\nSecond paragraph."

    assert chunk_markdown(text, ChunkingConfig()) == chunk_markdown(text, ChunkingConfig())


def test_ingestion_copies_source_and_indexes_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    source = tmp_path / "notes.md"
    user_data = tmp_path / "user-data"
    source.write_text("# Notes\n<!-- page: 3 -->\nconsecutive means following continuously", encoding="utf-8")
    init_db(db_path)

    with connect(db_path) as conn:
        run = KnowledgeIngestionService(conn, user_data_dir=user_data).import_file(
            source,
            title="Notes",
            language="en",
        )
        document = KnowledgeRepository(conn).list_documents()[0]
        events = AgentRunRepository(conn).events_after(run.id, 0)

        assert run.status == "completed"
        assert document.status == "ready"
        assert Path(document.raw_path).exists()
        assert Path(document.parsed_path).exists()
        assert KnowledgeRepository(conn).list_chunks(document.id)
        assert [event.payload.get("percent") for event in events] == [10, 35, 60, 90, 100]


def test_ingestion_failure_marks_document_and_cleans_staging(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    source = tmp_path / "notes.md"
    user_data = tmp_path / "user-data"
    source.write_text("broken", encoding="utf-8")
    init_db(db_path)

    def fail_extract(path: Path, *, language: str) -> tuple[str, str]:
        raise RuntimeError("extract failed")

    with connect(db_path) as conn:
        run = KnowledgeIngestionService(
            conn,
            user_data_dir=user_data,
            extractor=fail_extract,
        ).import_file(source, title="Broken", language="en")
        document = KnowledgeRepository(conn).list_documents()[0]

        assert run.status == "failed"
        assert run.error_code == "KNOWLEDGE_EXTRACTION_FAILED"
        assert document.status == "failed"
        assert document.error_code == "KNOWLEDGE_EXTRACTION_FAILED"
        assert list((user_data / "knowledge" / "raw").glob("*.staging")) == []
