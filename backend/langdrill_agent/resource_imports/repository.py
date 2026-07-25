from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from ..utils import dumps, loads, new_id
from .models import ImportStatus, ImportTarget, ResourceImportPreview, ResourceImportRecord


class ResourceImportRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(
        self,
        *,
        target: ImportTarget,
        filename: str,
        mime_type: str,
        size_bytes: int,
        staged_path: str,
        record_id: str | None = None,
    ) -> ResourceImportRecord:
        now = datetime.now()
        import_id = record_id or new_id("import")
        created_at = now.isoformat(timespec="seconds")
        expires_at = (now + timedelta(hours=24)).isoformat(timespec="seconds")
        self.conn.execute(
            """INSERT INTO resource_import_staging
               (id,target,filename,mime_type,size_bytes,staged_path,status,
                created_at,updated_at,expires_at)
               VALUES (?,?,?,?,?,?,'staged',?,?,?)""",
            (
                import_id,
                target,
                filename,
                mime_type,
                size_bytes,
                staged_path,
                created_at,
                created_at,
                expires_at,
            ),
        )
        return self.get(import_id)

    def get(self, record_id: str) -> ResourceImportRecord:
        row = self.conn.execute(
            "SELECT * FROM resource_import_staging WHERE id=?", (record_id,)
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return self._from_row(row)

    def update(
        self,
        record_id: str,
        *,
        extracted_path: str | None = None,
        status: ImportStatus | None = None,
        parser: str | None = None,
        preview: ResourceImportPreview | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> ResourceImportRecord:
        changes: dict[str, Any] = {
            "extracted_path": extracted_path,
            "status": status,
            "parser": parser,
            "error_code": error_code,
            "error_detail": error_detail,
        }
        if preview is not None:
            changes["preview_json"] = dumps(preview.model_dump(mode="json"))
        changes = {key: value for key, value in changes.items() if value is not None}
        if not changes:
            return self.get(record_id)
        changes["updated_at"] = datetime.now().isoformat(timespec="seconds")
        assignments = ", ".join(f"{column}=?" for column in changes)
        cursor = self.conn.execute(
            f"UPDATE resource_import_staging SET {assignments} WHERE id=?",
            (*changes.values(), record_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(record_id)
        return self.get(record_id)

    def delete(self, record_id: str) -> None:
        cursor = self.conn.execute(
            "DELETE FROM resource_import_staging WHERE id=?", (record_id,)
        )
        if cursor.rowcount != 1:
            raise KeyError(record_id)

    def list_expired(self) -> list[ResourceImportRecord]:
        now = datetime.now().isoformat(timespec="seconds")
        rows = self.conn.execute(
            """SELECT * FROM resource_import_staging
               WHERE expires_at < ? ORDER BY expires_at, id""",
            (now,),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ResourceImportRecord:
        preview_data = loads(row["preview_json"], {})
        return ResourceImportRecord(
            id=row["id"],
            target=row["target"],
            filename=row["filename"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            staged_path=row["staged_path"],
            extracted_path=row["extracted_path"],
            status=row["status"],
            parser=row["parser"],
            preview=ResourceImportPreview(**preview_data) if preview_data else None,
            error_code=row["error_code"],
            error_detail=row["error_detail"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
        )
