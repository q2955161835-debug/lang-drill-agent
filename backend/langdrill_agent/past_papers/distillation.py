from __future__ import annotations

import sqlite3
from collections import defaultdict
from pydantic import BaseModel, Field

from ..utils import dumps, loads, new_id
from .models import DistillationFinding


class DistillationRunResult(BaseModel):
    exam_id: str
    version: int
    status: str
    findings: list[DistillationFinding] = Field(default_factory=list)
    aggregate: dict[str, object] = Field(default_factory=dict)


class PastPaperDistillationService:
    MIN_PAPERS = 2
    MIN_EVIDENCE = 3

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def distill(
        self,
        exam_id: str,
        document_ids: list[str],
        *,
        prompt_version: str = "deterministic-v1",
        model: str = "program",
    ) -> DistillationRunResult:
        clean_ids = list(dict.fromkeys(item for item in document_ids if item))
        version = self._next_version(exam_id)
        if not clean_ids:
            return DistillationRunResult(
                exam_id=exam_id,
                version=version,
                status="insufficient_evidence",
            )
        placeholders = ",".join("?" for _ in clean_ids)
        rows = self.conn.execute(
            f"""
            SELECT q.id, q.document_id, q.question_type, q.difficulty,
                   q.verification_status, q.answer_confidence,
                   q.knowledge_tags_json, d.year
            FROM past_paper_questions q
            JOIN past_paper_documents d ON d.id=q.document_id
            WHERE d.exam_id=? AND d.status='ready'
              AND d.id IN ({placeholders})
            ORDER BY d.year, d.id, q.id
            """,
            [exam_id, *clean_ids],
        ).fetchall()
        paper_ids = {row["document_id"] for row in rows}
        verified_rows = [row for row in rows if row["verification_status"] == "verified"]
        aggregate = self._aggregate(rows, verified_rows, paper_ids)
        if len(paper_ids) < self.MIN_PAPERS:
            return DistillationRunResult(
                exam_id=exam_id,
                version=version,
                status="insufficient_evidence",
                aggregate=aggregate,
            )

        groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in verified_rows:
            groups[row["question_type"]].append(row)
        findings: list[DistillationFinding] = []
        for label, evidence_rows in sorted(groups.items()):
            evidence_papers = {row["document_id"] for row in evidence_rows}
            if len(evidence_rows) < self.MIN_EVIDENCE or len(evidence_papers) < self.MIN_PAPERS:
                continue
            evidence_ids = [row["id"] for row in evidence_rows]
            years = sorted({int(row["year"]) for row in evidence_rows if row["year"] is not None})
            confidence = min(
                1.0,
                0.35
                + 0.1 * min(len(evidence_rows), 5)
                + 0.1 * min(len(evidence_papers), 3),
            )
            finding_id = new_id("paperfinding")
            finding_payload = {
                "question_type": label,
                "share_of_verified": (
                    len(evidence_rows) / len(verified_rows) if verified_rows else 0
                ),
                "average_difficulty": _average_difficulty(evidence_rows),
                "verification_coverage": aggregate["verification_coverage"],
            }
            self.conn.execute(
                """
                INSERT INTO past_paper_distillations
                (id, exam_id, version, status, finding_type, label, finding_json,
                 evidence_count, paper_count, years_json, confidence, prompt_version, model)
                VALUES (?, ?, ?, 'ready', 'question_type_frequency', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding_id,
                    exam_id,
                    version,
                    label,
                    dumps(finding_payload),
                    len(evidence_ids),
                    len(evidence_papers),
                    dumps(years),
                    confidence,
                    prompt_version,
                    model,
                ),
            )
            self.conn.executemany(
                """
                INSERT INTO past_paper_distillation_evidence
                (distillation_id, question_id) VALUES (?, ?)
                """,
                [(finding_id, question_id) for question_id in evidence_ids],
            )
            findings.append(
                DistillationFinding(
                    id=finding_id,
                    exam_id=exam_id,
                    version=version,
                    status="ready",
                    finding_type="question_type_frequency",
                    label=label,
                    evidence_count=len(evidence_ids),
                    paper_count=len(evidence_papers),
                    years=years,
                    confidence=confidence,
                    evidence_question_ids=evidence_ids,
                )
            )
        status = "ready" if findings else "insufficient_evidence"
        return DistillationRunResult(
            exam_id=exam_id,
            version=version,
            status=status,
            findings=findings,
            aggregate=aggregate,
        )

    def latest_findings(self, exam_id: str) -> list[DistillationFinding]:
        version_row = self.conn.execute(
            """
            SELECT MAX(version) FROM past_paper_distillations
            WHERE exam_id=? AND status='ready'
            """,
            (exam_id,),
        ).fetchone()
        version = int(version_row[0] or 0)
        if not version:
            return []
        rows = self.conn.execute(
            """
            SELECT * FROM past_paper_distillations
            WHERE exam_id=? AND version=? AND status='ready'
            ORDER BY confidence DESC, evidence_count DESC, id
            """,
            (exam_id, version),
        ).fetchall()
        findings = []
        for row in rows:
            evidence_ids = [
                item[0]
                for item in self.conn.execute(
                    """
                    SELECT question_id FROM past_paper_distillation_evidence
                    WHERE distillation_id=? ORDER BY question_id
                    """,
                    (row["id"],),
                )
            ]
            findings.append(
                DistillationFinding(
                    id=row["id"],
                    exam_id=row["exam_id"],
                    version=row["version"],
                    status=row["status"],
                    finding_type=row["finding_type"],
                    label=row["label"],
                    evidence_count=row["evidence_count"],
                    paper_count=row["paper_count"],
                    years=loads(row["years_json"], []),
                    confidence=row["confidence"],
                    evidence_question_ids=evidence_ids,
                )
            )
        return findings

    def _next_version(self, exam_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM past_paper_distillations WHERE exam_id=?",
            (exam_id,),
        ).fetchone()
        return int(row[0])

    @staticmethod
    def _aggregate(
        rows: list[sqlite3.Row],
        verified_rows: list[sqlite3.Row],
        paper_ids: set[str],
    ) -> dict[str, object]:
        years = sorted({int(row["year"]) for row in rows if row["year"] is not None})
        type_counts: dict[str, int] = defaultdict(int)
        for row in rows:
            type_counts[row["question_type"]] += 1
        return {
            "question_count": len(rows),
            "verified_question_count": len(verified_rows),
            "paper_count": len(paper_ids),
            "years": years,
            "question_type_counts": dict(sorted(type_counts.items())),
            "verification_coverage": len(verified_rows) / len(rows) if rows else 0,
            "average_difficulty": _average_difficulty(rows),
        }


def _average_difficulty(rows: list[sqlite3.Row]) -> float | None:
    values = [float(row["difficulty"]) for row in rows if row["difficulty"] is not None]
    return sum(values) / len(values) if values else None
