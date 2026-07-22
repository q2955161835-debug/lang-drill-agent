from __future__ import annotations

import hashlib
import sqlite3

from ..utils import dumps, loads, new_id
from .models import (
    PaperDocument,
    PaperDocumentInput,
    PaperQuestion,
    PaperQuestionInput,
    PaperSource,
    PaperSourceInput,
)


class PastPaperRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_source(self, source: PaperSourceInput) -> PaperSource:
        self.conn.execute(
            """
            INSERT INTO past_paper_sources
            (id, exam_id, title, source_url, year, session, set_number,
             answer_source_url, source_host, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              exam_id=excluded.exam_id,
              title=excluded.title,
              source_url=excluded.source_url,
              year=excluded.year,
              session=excluded.session,
              set_number=excluded.set_number,
              answer_source_url=excluded.answer_source_url,
              source_host=excluded.source_host,
              metadata_json=excluded.metadata_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                source.id,
                source.exam_id,
                source.title,
                source.source_url,
                source.year,
                source.session,
                source.set_number,
                source.answer_source_url,
                source.source_host,
                dumps(source.metadata),
            ),
        )
        row = self.conn.execute(
            "SELECT * FROM past_paper_sources WHERE id=?",
            (source.id,),
        ).fetchone()
        return self._source_from_row(row)

    def list_sources(self, exam_id: str) -> list[PaperSource]:
        rows = self.conn.execute(
            "SELECT * FROM past_paper_sources WHERE exam_id=? ORDER BY year DESC, session, set_number, id",
            (exam_id,),
        ).fetchall()
        return [self._source_from_row(row) for row in rows]

    def create_document(self, document: PaperDocumentInput) -> PaperDocument:
        document_id = new_id("paperdoc")
        self.conn.execute(
            """
            INSERT INTO past_paper_documents
            (id, source_id, exam_id, title, year, session, set_number, source_url,
             raw_path, markdown_path, structured_path, content_hash, status,
             parser, parser_version, error_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                document.source_id,
                document.exam_id,
                document.title,
                document.year,
                document.session,
                document.set_number,
                document.source_url,
                document.raw_path,
                document.markdown_path,
                document.structured_path,
                document.content_hash,
                document.status,
                document.parser,
                document.parser_version,
                document.error_code,
            ),
        )
        return self.get_document(document_id)

    def update_document_state(
        self,
        document_id: str,
        *,
        status: str,
        markdown_path: str | None = None,
        structured_path: str | None = None,
        parser: str | None = None,
        parser_version: str | None = None,
        error_code: str | None = None,
    ) -> PaperDocument:
        cursor = self.conn.execute(
            """
            UPDATE past_paper_documents
            SET status=?,
                markdown_path=COALESCE(?, markdown_path),
                structured_path=COALESCE(?, structured_path),
                parser=COALESCE(?, parser),
                parser_version=COALESCE(?, parser_version),
                error_code=COALESCE(?, error_code),
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                status,
                markdown_path,
                structured_path,
                parser,
                parser_version,
                error_code,
                document_id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(document_id)
        return self.get_document(document_id)

    def get_document(self, document_id: str) -> PaperDocument:
        row = self.conn.execute(
            "SELECT * FROM past_paper_documents WHERE id=?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise KeyError(document_id)
        return self._document_from_row(row)

    def list_documents(self, exam_id: str) -> list[PaperDocument]:
        rows = self.conn.execute(
            "SELECT * FROM past_paper_documents WHERE exam_id=? ORDER BY year DESC, created_at, id",
            (exam_id,),
        ).fetchall()
        return [self._document_from_row(row) for row in rows]

    def find_document_by_source_hash(
        self,
        *,
        exam_id: str,
        source_url: str,
        content_hash: str,
    ) -> PaperDocument | None:
        row = self.conn.execute(
            """
            SELECT * FROM past_paper_documents
            WHERE exam_id=? AND source_url=? AND content_hash=?
            """,
            (exam_id, source_url, content_hash),
        ).fetchone()
        return self._document_from_row(row) if row else None

    def replace_questions(
        self,
        document_id: str,
        questions: list[PaperQuestionInput],
    ) -> list[PaperQuestion]:
        self.get_document(document_id)
        if not questions:
            raise ValueError("paper questions cannot be empty")
        numbers = [question.question_number for question in questions if question.question_number]
        if len(numbers) != len(set(numbers)):
            raise ValueError("duplicate question number")
        self.conn.execute("SAVEPOINT replace_paper_questions")
        try:
            existing_ids = [
                row[0]
                for row in self.conn.execute(
                    "SELECT id FROM past_paper_questions WHERE document_id=?",
                    (document_id,),
                )
            ]
            if existing_ids:
                placeholders = ",".join("?" for _ in existing_ids)
                self.conn.execute(
                    f"DELETE FROM past_paper_question_fts WHERE question_id IN ({placeholders})",
                    existing_ids,
                )
            self.conn.execute(
                "DELETE FROM past_paper_questions WHERE document_id=?",
                (document_id,),
            )
            result = []
            for question in questions:
                question_id = new_id("paperq")
                content_hash = question.content_hash or _question_hash(question)
                self.conn.execute(
                    """
                    INSERT INTO past_paper_questions
                    (id, document_id, question_number, question_type, prompt,
                     options_json, answer_json, explanation, knowledge_tags_json,
                     difficulty, source_page, answer_confidence, verification_status, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        question_id,
                        document_id,
                        question.question_number,
                        question.question_type,
                        question.prompt,
                        dumps(question.options),
                        dumps(question.answer),
                        question.explanation,
                        dumps(question.knowledge_tags),
                        question.difficulty,
                        question.source_page,
                        question.answer_confidence,
                        question.verification_status,
                        content_hash,
                    ),
                )
                self.conn.execute(
                    """
                    INSERT INTO past_paper_question_fts
                    (question_id, document_id, question_type, prompt, options, explanation, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        question_id,
                        document_id,
                        question.question_type,
                        question.prompt,
                        " ".join(question.options),
                        question.explanation,
                        " ".join(question.knowledge_tags),
                    ),
                )
                result.append(
                    PaperQuestion(
                        id=question_id,
                        document_id=document_id,
                        **question.model_dump(exclude={"content_hash"}),
                        content_hash=content_hash,
                    )
                )
            self.conn.execute("RELEASE SAVEPOINT replace_paper_questions")
            return result
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT replace_paper_questions")
            self.conn.execute("RELEASE SAVEPOINT replace_paper_questions")
            raise

    def rebuild_question_fts(self, document_id: str) -> int:
        questions = self.list_questions(document_id)
        self.conn.execute(
            "DELETE FROM past_paper_question_fts WHERE document_id=?",
            (document_id,),
        )
        self.conn.executemany(
            """
            INSERT INTO past_paper_question_fts
            (question_id, document_id, question_type, prompt, options, explanation, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    question.id,
                    question.document_id,
                    question.question_type,
                    question.prompt,
                    " ".join(question.options),
                    question.explanation,
                    " ".join(question.knowledge_tags),
                )
                for question in questions
            ],
        )
        return len(questions)

    def list_questions(self, document_id: str) -> list[PaperQuestion]:
        rows = self.conn.execute(
            """
            SELECT * FROM past_paper_questions
            WHERE document_id=? ORDER BY CAST(question_number AS INTEGER), question_number, id
            """,
            (document_id,),
        ).fetchall()
        return [self._question_from_row(row) for row in rows]

    @staticmethod
    def _source_from_row(row: sqlite3.Row) -> PaperSource:
        return PaperSource(
            id=row["id"],
            exam_id=row["exam_id"],
            title=row["title"],
            source_url=row["source_url"],
            year=row["year"],
            session=row["session"],
            set_number=row["set_number"],
            answer_source_url=row["answer_source_url"],
            source_host=row["source_host"],
            metadata=loads(row["metadata_json"], {}),
            discovered_at=row["discovered_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> PaperDocument:
        return PaperDocument(
            id=row["id"],
            source_id=row["source_id"],
            exam_id=row["exam_id"],
            title=row["title"],
            year=row["year"],
            session=row["session"],
            set_number=row["set_number"],
            source_url=row["source_url"],
            raw_path=row["raw_path"],
            markdown_path=row["markdown_path"],
            structured_path=row["structured_path"],
            content_hash=row["content_hash"],
            status=row["status"],
            parser=row["parser"],
            parser_version=row["parser_version"],
            error_code=row["error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _question_from_row(row: sqlite3.Row) -> PaperQuestion:
        return PaperQuestion(
            id=row["id"],
            document_id=row["document_id"],
            section_id=row["section_id"],
            passage_id=row["passage_id"],
            question_number=row["question_number"],
            question_type=row["question_type"],
            prompt=row["prompt"],
            options=loads(row["options_json"], []),
            answer=loads(row["answer_json"], {}),
            explanation=row["explanation"],
            knowledge_tags=loads(row["knowledge_tags_json"], []),
            difficulty=row["difficulty"],
            source_page=row["source_page"],
            answer_confidence=row["answer_confidence"],
            verification_status=row["verification_status"],
            content_hash=row["content_hash"],
        )


def _question_hash(question: PaperQuestionInput) -> str:
    payload = dumps(
        {
            "number": question.question_number,
            "type": question.question_type,
            "prompt": question.prompt,
            "options": question.options,
            "answer": question.answer,
        }
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
