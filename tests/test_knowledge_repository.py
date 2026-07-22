from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.knowledge.models import KnowledgeChunkInput
from langdrill_agent.knowledge.repository import KnowledgeRepository


def test_document_and_chunks_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = KnowledgeRepository(conn)
        document = repo.create_document(
            title="Unit 1",
            source_name="unit1.pdf",
            mime_type="application/pdf",
            content_hash="sha256:abc",
        )
        repo.upsert_chunks(
            document.id,
            [
                KnowledgeChunkInput(
                    ordinal=0,
                    heading="Vocabulary",
                    page_start=2,
                    page_end=2,
                    content="consecutive means following continuously",
                    content_hash="sha256:c1",
                )
            ],
        )

        assert repo.get_document(document.id).title == "Unit 1"
        assert repo.list_chunks(document.id)[0].page_start == 2


def test_delete_document_removes_chunks_and_fts_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = KnowledgeRepository(conn)
        document = repo.create_document(
            title="Unit 1",
            source_name="unit1.md",
            mime_type="text/markdown",
            content_hash="sha256:abc",
        )
        repo.upsert_chunks(
            document.id,
            [
                KnowledgeChunkInput(
                    ordinal=0,
                    heading="Vocabulary",
                    content="consecutive means following continuously",
                    content_hash="sha256:c1",
                )
            ],
        )
        repo.delete_document(document.id)

        assert repo.list_documents() == []
        assert conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM knowledge_chunk_fts").fetchone()[0] == 0
