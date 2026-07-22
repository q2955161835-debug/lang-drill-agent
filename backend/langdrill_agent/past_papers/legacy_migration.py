from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from ..paper_assets import source_manifest_text
from ..utils import loads
from .models import PaperSourceInput
from .repository import PastPaperRepository


@dataclass(frozen=True, slots=True)
class LegacyMigrationReport:
    catalogued: int = 0
    removed_generated_files: int = 0
    preserved_modified: int = 0
    skipped: int = 0
    backup_path: str = ""


def migrate_legacy_manifests(
    conn: sqlite3.Connection,
    papers_root: Path,
) -> LegacyMigrationReport:
    rows = conn.execute(
        """
        SELECT id, exam_id, title, year, source_url, local_path, metadata_json
        FROM exam_assets
        WHERE asset_type='past_paper'
        ORDER BY id
        """
    ).fetchall()
    catalogued = 0
    removed_files = 0
    preserved = 0
    skipped = 0
    backup_path = ""
    backup_created = False
    repo = PastPaperRepository(conn)

    for row in rows:
        metadata = loads(row["metadata_json"], {})
        markers = {metadata.get("import_mode"), metadata.get("parse_status")}
        if not markers.intersection({"default_recent_source_manifest", "source_manifest_only"}):
            skipped += 1
            continue
        raw_path = _resolve_asset_path(papers_root, metadata.get("raw_path") or row["local_path"])
        parsed_path = _resolve_asset_path(papers_root, metadata.get("parsed_path") or "")
        expected = source_manifest_text(
            exam_id=row["exam_id"],
            title=row["title"],
            year=row["year"],
            source_url=row["source_url"],
            summary=str(metadata.get("summary") or ""),
            question_types=[str(item) for item in metadata.get("question_types", [])],
        )
        if not raw_path.is_file() or _sha256(raw_path.read_text(encoding="utf-8")) != _sha256(expected):
            preserved += 1
            continue
        if not backup_created:
            backup_path = _backup_database(conn)
            backup_created = True
        parsed_url = urlparse(row["source_url"] or "")
        repo.upsert_source(
            PaperSourceInput(
                id=f"legacy-{row['id']}",
                exam_id=row["exam_id"],
                title=row["title"],
                source_url=row["source_url"] or "",
                year=row["year"],
                source_host=parsed_url.hostname or "",
                metadata={"migrated_from": row["id"], "catalog_only": True},
            )
        )
        conn.execute("DELETE FROM exam_assets WHERE id=?", (row["id"],))
        for path in (raw_path, parsed_path):
            if path.is_file():
                path.unlink()
                removed_files += 1
        catalogued += 1

    return LegacyMigrationReport(
        catalogued=catalogued,
        removed_generated_files=removed_files,
        preserved_modified=preserved,
        skipped=skipped,
        backup_path=backup_path,
    )


def _resolve_asset_path(papers_root: Path, raw_path: str) -> Path:
    if not raw_path:
        return papers_root / "missing"
    path = Path(raw_path)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0].lower() == "papers":
        path = Path(*parts[1:])
    return papers_root / path


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _backup_database(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None or not row[2]:
        return ""
    db_path = Path(row[2])
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.stem}.pre-paper-migration-{stamp}{db_path.suffix}")
    with sqlite3.connect(backup_path) as backup_conn:
        conn.backup(backup_conn)
    return str(backup_path)
