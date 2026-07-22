from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import dumps, loads, new_id
from .models import (
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeChunkInput,
    KnowledgeDocument,
)


class KnowledgeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_document(
        self,
        *,
        title: str,
        source_name: str,
        mime_type: str,
        content_hash: str,
        raw_path: str = "",
        parsed_path: str = "",
        language: str = "",
        status: DocumentStatus | str = DocumentStatus.queued,
        parser: str = "",
        parser_version: str = "",
        error_code: str = "",
    ) -> KnowledgeDocument:
        document_id = new_id("knowledge")
        normalized_status = DocumentStatus(status)
        self.conn.execute(
            """
            INSERT INTO knowledge_documents
            (id, title, source_name, mime_type, raw_path, parsed_path, content_hash,
             language, status, parser, parser_version, error_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                title,
                source_name,
                mime_type,
                raw_path,
                parsed_path,
                content_hash,
                language,
                normalized_status.value,
                parser,
                parser_version,
                error_code,
            ),
        )
        return self.get_document(document_id)

    def get_document(self, document_id: str) -> KnowledgeDocument:
        row = self.conn.execute(
            "SELECT * FROM knowledge_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise KeyError(document_id)
        return self._document_from_row(row)

    def list_documents(self) -> list[KnowledgeDocument]:
        rows = self.conn.execute(
            "SELECT * FROM knowledge_documents ORDER BY created_at, id"
        ).fetchall()
        return [self._document_from_row(row) for row in rows]

    def set_document_status(
        self,
        document_id: str,
        status: DocumentStatus | str,
        *,
        raw_path: str | None = None,
        parsed_path: str | None = None,
        parser: str | None = None,
        parser_version: str | None = None,
        error_code: str | None = None,
    ) -> KnowledgeDocument:
        self.get_document(document_id)
        updates: dict[str, Any] = {"status": DocumentStatus(status).value}
        for key, value in {
            "raw_path": raw_path,
            "parsed_path": parsed_path,
            "parser": parser,
            "parser_version": parser_version,
            "error_code": error_code,
        }.items():
            if value is not None:
                updates[key] = value
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = [*updates.values(), document_id]
        self.conn.execute(
            f"UPDATE knowledge_documents SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        return self.get_document(document_id)

    def upsert_chunks(
        self,
        document_id: str,
        chunks: list[KnowledgeChunkInput],
    ) -> list[KnowledgeChunk]:
        self.get_document(document_id)
        self.conn.execute(
            "DELETE FROM knowledge_chunk_fts WHERE document_id = ?",
            (document_id,),
        )
        self.conn.execute(
            "DELETE FROM knowledge_chunks WHERE document_id = ?",
            (document_id,),
        )
        result: list[KnowledgeChunk] = []
        for chunk in chunks:
            chunk_id = new_id("chunk")
            self.conn.execute(
                """
                INSERT INTO knowledge_chunks
                (id, document_id, ordinal, heading, page_start, page_end, content,
                 content_hash, token_count, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    document_id,
                    chunk.ordinal,
                    chunk.heading,
                    chunk.page_start,
                    chunk.page_end,
                    chunk.content,
                    chunk.content_hash,
                    chunk.token_count,
                    dumps(chunk.metadata),
                ),
            )
            self.conn.execute(
                "INSERT INTO knowledge_chunk_fts(chunk_id, document_id, heading, content) VALUES (?, ?, ?, ?)",
                (chunk_id, document_id, chunk.heading, chunk.content),
            )
            result.append(
                KnowledgeChunk(
                    id=chunk_id,
                    document_id=document_id,
                    **chunk.model_dump(),
                )
            )
        return result

    def list_chunks(self, document_id: str) -> list[KnowledgeChunk]:
        rows = self.conn.execute(
            "SELECT * FROM knowledge_chunks WHERE document_id = ? ORDER BY ordinal, id",
            (document_id,),
        ).fetchall()
        return [self._chunk_from_row(row) for row in rows]

    def delete_document(self, document_id: str) -> None:
        self.get_document(document_id)
        self.conn.execute(
            "DELETE FROM knowledge_chunk_fts WHERE document_id = ?",
            (document_id,),
        )
        self.conn.execute(
            "DELETE FROM knowledge_documents WHERE id = ?",
            (document_id,),
        )

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=row["id"],
            title=row["title"],
            source_name=row["source_name"],
            mime_type=row["mime_type"],
            raw_path=row["raw_path"],
            parsed_path=row["parsed_path"],
            content_hash=row["content_hash"],
            language=row["language"],
            status=row["status"],
            parser=row["parser"],
            parser_version=row["parser_version"],
            error_code=row["error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _chunk_from_row(row: sqlite3.Row) -> KnowledgeChunk:
        return KnowledgeChunk(
            id=row["id"],
            document_id=row["document_id"],
            ordinal=row["ordinal"],
            heading=row["heading"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            content=row["content"],
            content_hash=row["content_hash"],
            token_count=row["token_count"],
            metadata=loads(row["metadata_json"], {}),
        )
