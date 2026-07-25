from __future__ import annotations

import sqlite3

from ..utils import dumps, loads, new_id
from .models import MemoryCandidate, MemoryEvidence, MemoryItem, MemoryRevision


class MemoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def stage(self, candidate: MemoryCandidate) -> MemoryCandidate:
        candidate_id = candidate.id
        if not candidate_id and candidate.normalized_key:
            existing = self.conn.execute(
                """
                SELECT id FROM memory_candidates
                WHERE category=? AND scope=? AND normalized_key=? AND status='staged'
                ORDER BY created_at, id LIMIT 1
                """,
                (candidate.category, candidate.scope, candidate.normalized_key),
            ).fetchone()
            candidate_id = str(existing["id"]) if existing else ""
        candidate_id = candidate_id or new_id("memcand")
        row = self.conn.execute(
            "SELECT metadata_json FROM memory_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        if row:
            metadata = {**loads(row["metadata_json"], {}), **candidate.metadata}
            self.conn.execute(
                """
                UPDATE memory_candidates
                SET category=?, scope=?, content=?, normalized_key=?, confidence=?,
                    importance=?, status='staged', reason=?, valid_from=?, valid_to=?,
                    expires_at=?, pinned=?, metadata_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    candidate.category,
                    candidate.scope,
                    candidate.content,
                    candidate.normalized_key,
                    candidate.confidence,
                    candidate.importance,
                    candidate.reason,
                    candidate.valid_from,
                    candidate.valid_to,
                    candidate.expires_at,
                    int(candidate.pinned),
                    dumps(metadata),
                    candidate_id,
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO memory_candidates
                (id, category, scope, content, normalized_key, confidence, importance,
                 status, reason, valid_from, valid_to, expires_at, pinned, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    candidate.category,
                    candidate.scope,
                    candidate.content,
                    candidate.normalized_key,
                    candidate.confidence,
                    candidate.importance,
                    candidate.status,
                    candidate.reason,
                    candidate.valid_from,
                    candidate.valid_to,
                    candidate.expires_at,
                    int(candidate.pinned),
                    dumps(candidate.metadata),
                ),
            )
        existing_evidence = {
            str(item[0])
            for item in self.conn.execute(
                "SELECT evidence_ref FROM memory_evidence WHERE candidate_id=?",
                (candidate_id,),
            )
        }
        for evidence_ref in candidate.evidence_ids:
            if evidence_ref in existing_evidence:
                continue
            self.conn.execute(
                """
                INSERT INTO memory_evidence
                (id, candidate_id, evidence_type, evidence_ref)
                VALUES (?, ?, 'reference', ?)
                """,
                (new_id("memev"), candidate_id, evidence_ref),
            )
        self._event("candidate_staged", candidate_id=candidate_id)
        return self.get_candidate(candidate_id)

    def commit(self, candidate: MemoryCandidate) -> MemoryItem:
        staged = candidate if candidate.id else self.stage(candidate)
        if not staged.id:
            raise ValueError("memory candidate must be staged before commit")
        memory_id = new_id("memory")
        self.conn.execute("SAVEPOINT memory_commit")
        try:
            self.conn.execute(
                """
                INSERT INTO memory_items
                (id, category, scope, content, normalized_key, confidence, importance,
                 status, valid_from, valid_to, expires_at, pinned, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    staged.category,
                    staged.scope,
                    staged.content,
                    staged.normalized_key,
                    staged.confidence,
                    staged.importance,
                    staged.valid_from,
                    staged.valid_to,
                    staged.expires_at,
                    int(staged.pinned),
                    dumps(staged.metadata),
                ),
            )
            self.conn.execute(
                """
                UPDATE memory_evidence SET memory_id=? WHERE candidate_id=?
                """,
                (memory_id, staged.id),
            )
            self.conn.execute(
                """
                UPDATE memory_candidates
                SET status='committed', updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (staged.id,),
            )
            item = self.get(memory_id)
            self._revision(item, "ADD")
            self._refresh_fts(item)
            self._event("memory_committed", memory_id=memory_id, candidate_id=staged.id)
            self.conn.execute("RELEASE SAVEPOINT memory_commit")
            return self.get(memory_id)
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT memory_commit")
            self.conn.execute("RELEASE SAVEPOINT memory_commit")
            raise

    def update(
        self,
        memory_id: str,
        content: str,
        *,
        confidence: float | None = None,
        importance: float | None = None,
        pinned: bool | None = None,
        metadata: dict | None = None,
    ) -> MemoryItem:
        self.get(memory_id)
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("memory content cannot be empty")
        self.conn.execute("SAVEPOINT memory_update")
        try:
            self.conn.execute(
                """
                UPDATE memory_items
                SET content=?,
                    confidence=COALESCE(?, confidence),
                    importance=COALESCE(?, importance),
                    pinned=COALESCE(?, pinned),
                    metadata_json=COALESCE(?, metadata_json),
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    clean_content,
                    confidence,
                    importance,
                    int(pinned) if pinned is not None else None,
                    dumps(metadata) if metadata is not None else None,
                    memory_id,
                ),
            )
            item = self.get(memory_id)
            self._revision(item, "UPDATE")
            self._refresh_fts(item)
            self._event("memory_updated", memory_id=memory_id)
            self.conn.execute("RELEASE SAVEPOINT memory_update")
            return item
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT memory_update")
            self.conn.execute("RELEASE SAVEPOINT memory_update")
            raise

    def supersede(self, memory_id: str, replacement: MemoryCandidate) -> MemoryItem:
        old = self.get(memory_id)
        self.conn.execute("SAVEPOINT memory_supersede")
        try:
            self.conn.execute(
                """
                UPDATE memory_items
                SET status='superseded', updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (memory_id,),
            )
            superseded = self.get(memory_id)
            self._revision(superseded, "SUPERSEDE")
            self._refresh_fts(superseded)
            prepared = replacement.model_copy(
                update={"normalized_key": replacement.normalized_key or old.normalized_key}
            )
            staged = prepared if prepared.id else self.stage(prepared)
            new_item = self.commit(staged)
            self.conn.execute(
                "UPDATE memory_items SET supersedes_id=? WHERE id=?",
                (memory_id, new_item.id),
            )
            self._event(
                "memory_superseded",
                memory_id=memory_id,
                payload={"replacement_id": new_item.id},
            )
            self.conn.execute("RELEASE SAVEPOINT memory_supersede")
            return self.get(new_item.id)
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT memory_supersede")
            self.conn.execute("RELEASE SAVEPOINT memory_supersede")
            raise

    def archive(self, memory_id: str) -> MemoryItem:
        return self._set_status(memory_id, "archived", "ARCHIVE")

    def mark_superseded_from_import(self, memory_id: str) -> MemoryItem:
        return self._set_status(memory_id, "superseded", "SUPERSEDE")

    def delete(self, memory_id: str) -> MemoryItem:
        return self._set_status(memory_id, "deleted", "DELETE")

    def restore(self, memory_id: str) -> MemoryItem:
        return self._set_status(memory_id, "active", "RESTORE")

    def purge(self, memory_id: str, *, confirmed: bool = False) -> None:
        if not confirmed:
            raise ValueError("permanent memory purge requires confirmation")
        self.get(memory_id)
        self.conn.execute("DELETE FROM memory_item_fts WHERE memory_id=?", (memory_id,))
        self.conn.execute("DELETE FROM memory_items WHERE id=?", (memory_id,))

    def archive_categories(self, categories: list[str]) -> int:
        """Soft-archive every active memory item whose category is listed.

        Used by the user-facing group clear endpoint. Items are marked
        ``archived`` (not deleted) so evidence, revisions and history remain
        intact. Returns the number of rows touched.
        """
        if not categories:
            return 0
        placeholders = ",".join("?" for _ in categories)
        cursor = self.conn.execute(
            f"""UPDATE memory_items
                SET status='archived', updated_at=CURRENT_TIMESTAMP
                WHERE status='active' AND category IN ({placeholders})""",
            categories,
        )
        # Refresh FTS index so archived items drop out of recall results.
        self.conn.execute(
            f"""DELETE FROM memory_item_fts
                WHERE memory_id IN (
                    SELECT id FROM memory_items
                    WHERE status<>'active' AND category IN ({placeholders})
                )""",
            categories,
        )
        self._event(
            "memory_group_archived",
            payload={"categories": categories, "count": int(cursor.rowcount)},
        )
        return int(cursor.rowcount)

    def count_active_by_category(self) -> dict[str, int]:
        """Return ``{category: active_count}`` for all active memory items."""
        rows = self.conn.execute(
            "SELECT category, COUNT(*) AS count FROM memory_items "
            "WHERE status='active' GROUP BY category"
        ).fetchall()
        return {str(row["category"]): int(row["count"]) for row in rows}

    def get(self, memory_id: str) -> MemoryItem:
        row = self.conn.execute(
            "SELECT * FROM memory_items WHERE id=?",
            (memory_id,),
        ).fetchone()
        if row is None:
            raise KeyError(memory_id)
        return self._item_from_row(row)

    def get_candidate(self, candidate_id: str) -> MemoryCandidate:
        row = self.conn.execute(
            "SELECT * FROM memory_candidates WHERE id=?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        evidence_ids = [
            item[0]
            for item in self.conn.execute(
                "SELECT evidence_ref FROM memory_evidence WHERE candidate_id=? ORDER BY created_at, id",
                (candidate_id,),
            )
        ]
        return MemoryCandidate(
            id=row["id"],
            category=row["category"],
            scope=row["scope"],
            content=row["content"],
            normalized_key=row["normalized_key"],
            confidence=row["confidence"],
            importance=row["importance"],
            status=row["status"],
            reason=row["reason"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            expires_at=row["expires_at"],
            pinned=bool(row["pinned"]),
            evidence_ids=evidence_ids,
            metadata=loads(row["metadata_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_items(
        self,
        *,
        statuses: tuple[str, ...] = ("active",),
        categories: list[str] | None = None,
        scope: str | None = None,
    ) -> list[MemoryItem]:
        filters = []
        params: list[object] = []
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            filters.append(f"status IN ({placeholders})")
            params.extend(statuses)
        if categories:
            placeholders = ",".join("?" for _ in categories)
            filters.append(f"category IN ({placeholders})")
            params.extend(categories)
        if scope:
            filters.append("scope IN (?, 'global')")
            params.append(scope)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        rows = self.conn.execute(
            f"SELECT * FROM memory_items {where} ORDER BY pinned DESC, importance DESC, updated_at DESC, id",
            params,
        ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def mark_candidate_committed_existing(
        self,
        candidate_id: str,
        *,
        memory_id: str,
    ) -> MemoryCandidate:
        self.get(memory_id)
        self.get_candidate(candidate_id)
        self.conn.execute(
            "UPDATE memory_evidence SET memory_id=? WHERE candidate_id=?",
            (memory_id, candidate_id),
        )
        self.conn.execute(
            """
            UPDATE memory_candidates
            SET status='committed', reason='duplicate_memory', updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (candidate_id,),
        )
        self._event(
            "memory_candidate_linked",
            memory_id=memory_id,
            candidate_id=candidate_id,
        )
        return self.get_candidate(candidate_id)

    def mark_candidate_committed_external(
        self,
        candidate_id: str,
        *,
        provider_id: str,
        external_memory_id: str,
    ) -> MemoryCandidate:
        candidate = self.get_candidate(candidate_id)
        metadata = {
            **candidate.metadata,
            "provider_id": provider_id,
            "external_memory_id": external_memory_id,
        }
        self.conn.execute(
            """
            UPDATE memory_candidates
            SET status='committed', metadata_json=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (dumps(metadata), candidate_id),
        )
        self._event(
            "memory_committed_external",
            candidate_id=candidate_id,
            payload={
                "provider_id": provider_id,
                "external_memory_id": external_memory_id,
            },
        )
        return self.get_candidate(candidate_id)

    def discard_candidate(
        self,
        candidate_id: str,
        *,
        reason: str = "discarded",
    ) -> MemoryCandidate:
        self.get_candidate(candidate_id)
        self.conn.execute(
            """
            UPDATE memory_candidates
            SET status='discarded', reason=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (reason, candidate_id),
        )
        self._event("candidate_discarded", candidate_id=candidate_id, payload={"reason": reason})
        return self.get_candidate(candidate_id)

    def list_candidates(self, *, status: str | None = None) -> list[MemoryCandidate]:
        if status:
            rows = self.conn.execute(
                "SELECT id FROM memory_candidates WHERE status=? ORDER BY created_at, id",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id FROM memory_candidates ORDER BY created_at, id"
            ).fetchall()
        return [self.get_candidate(row["id"]) for row in rows]

    def evidence(self, memory_id: str) -> list[MemoryEvidence]:
        rows = self.conn.execute(
            "SELECT * FROM memory_evidence WHERE memory_id=? ORDER BY created_at, id",
            (memory_id,),
        ).fetchall()
        return [
            MemoryEvidence(
                id=row["id"],
                candidate_id=row["candidate_id"],
                memory_id=row["memory_id"],
                evidence_type=row["evidence_type"],
                evidence_ref=row["evidence_ref"],
                payload=loads(row["payload_json"], {}),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def revisions(self, memory_id: str) -> list[MemoryRevision]:
        rows = self.conn.execute(
            "SELECT * FROM memory_revisions WHERE memory_id=? ORDER BY id",
            (memory_id,),
        ).fetchall()
        return [
            MemoryRevision(
                id=row["id"],
                memory_id=row["memory_id"],
                operation=row["operation"],
                content=row["content"],
                snapshot=loads(row["snapshot_json"], {}),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def _set_status(self, memory_id: str, status: str, operation: str) -> MemoryItem:
        self.get(memory_id)
        self.conn.execute("SAVEPOINT memory_status")
        try:
            self.conn.execute(
                "UPDATE memory_items SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, memory_id),
            )
            item = self.get(memory_id)
            self._revision(item, operation)
            self._refresh_fts(item)
            self._event(f"memory_{status}", memory_id=memory_id)
            self.conn.execute("RELEASE SAVEPOINT memory_status")
            return item
        except Exception:
            self.conn.execute("ROLLBACK TO SAVEPOINT memory_status")
            self.conn.execute("RELEASE SAVEPOINT memory_status")
            raise

    def _refresh_fts(self, item: MemoryItem) -> None:
        self.conn.execute("DELETE FROM memory_item_fts WHERE memory_id=?", (item.id,))
        if item.status != "active":
            return
        self.conn.execute(
            """
            INSERT INTO memory_item_fts
            (memory_id, category, scope, content, normalized_key)
            VALUES (?, ?, ?, ?, ?)
            """,
            (item.id, item.category, item.scope, item.content, item.normalized_key),
        )

    def _revision(self, item: MemoryItem, operation: str) -> None:
        self.conn.execute(
            """
            INSERT INTO memory_revisions
            (memory_id, operation, content, snapshot_json)
            VALUES (?, ?, ?, ?)
            """,
            (item.id, operation, item.content, dumps(item.model_dump(mode="json"))),
        )

    def _event(
        self,
        event_type: str,
        *,
        memory_id: str | None = None,
        candidate_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO memory_events
            (id, memory_id, candidate_id, event_type, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (new_id("memevent"), memory_id, candidate_id, event_type, dumps(payload or {})),
        )

    @staticmethod
    def _item_from_row(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            category=row["category"],
            scope=row["scope"],
            content=row["content"],
            normalized_key=row["normalized_key"],
            confidence=row["confidence"],
            importance=row["importance"],
            status=row["status"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            expires_at=row["expires_at"],
            supersedes_id=row["supersedes_id"],
            pinned=bool(row["pinned"]),
            metadata=loads(row["metadata_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
