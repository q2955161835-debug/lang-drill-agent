"""Confirmed embedding model downloads with resume and cancellation."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from ..utils import new_id
from .catalog import EmbeddingModelCatalog
from .models import EmbeddingDownloadJob

JOB_NOT_FOUND_ERROR = "EMBEDDING_DOWNLOAD_JOB_NOT_FOUND"
CONFIRMATION_ERROR = "EMBEDDING_DOWNLOAD_CONFIRMATION_REQUIRED"
MODEL_INCOMPATIBLE_ERROR = "EMBEDDING_MODEL_INCOMPATIBLE"
DISK_SPACE_ERROR = "EMBEDDING_DISK_SPACE_INSUFFICIENT"
DOWNLOAD_FAILED_ERROR = "EMBEDDING_DOWNLOAD_FAILED"

MIN_FREE_SPACE_BYTES = 256 * 1024 * 1024
ERROR_DETAIL_MAX_LENGTH = 300


def safe_model_dir(model_id: str) -> str:
    """Convert ``org/name`` to a single directory component."""

    return model_id.replace("/", "__")


class EmbeddingDownloadService:
    """Create, run, cancel, and inspect embedding model download jobs.

    Every download or activation requires ``confirmed=True``. ``run`` checks
    ``cancel_requested`` between files and is idempotent for terminal states.
    """

    def __init__(
        self, conn: sqlite3.Connection, hub: Any | None = None
    ) -> None:
        self.conn = conn
        self.hub = hub
        self.catalog = EmbeddingModelCatalog(client=hub)

    def _resolve_hub(self) -> Any:
        if self.hub is None:
            import huggingface_hub

            self.hub = huggingface_hub
        return self.hub

    def create(
        self,
        model_id: str,
        revision: str,
        model_root: Path,
        *,
        confirmed: bool,
    ) -> EmbeddingDownloadJob:
        if not confirmed:
            raise ValueError(CONFIRMATION_ERROR)
        detail = self.catalog.detail(model_id, revision=revision)
        if not detail.compatible:
            raise ValueError(MODEL_INCOMPATIBLE_ERROR)
        required = detail.size_bytes + max(
            detail.size_bytes // 10, MIN_FREE_SPACE_BYTES
        )
        if shutil.disk_usage(model_root.parent).free < required:
            raise ValueError(DISK_SPACE_ERROR)
        job_id = new_id("embeddl")
        target_dir = str(model_root / safe_model_dir(model_id) / detail.revision)
        self.conn.execute(
            """
            INSERT INTO embedding_download_jobs
              (id, kind, model_id, revision, target_dir, status,
               files_total, files_completed, bytes_downloaded,
               cancel_requested, error_code, error_detail)
            VALUES (?, 'model', ?, ?, ?, 'pending', ?, 0, 0, 0, '', '')
            """,
            (
                job_id,
                model_id,
                detail.revision,
                target_dir,
                len(detail.download_files),
            ),
        )
        return self._load_job(job_id)

    def run(self, job_id: str) -> None:
        row = self._fetch_job(job_id)
        if row is None:
            raise ValueError(JOB_NOT_FOUND_ERROR)
        if row["status"] not in ("pending", "running"):
            return
        self.conn.execute(
            "UPDATE embedding_download_jobs SET status='running', "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (job_id,),
        )
        try:
            detail = self.catalog.detail(
                row["model_id"], revision=row["revision"]
            )
            hub = self._resolve_hub()
            files_completed = int(row["files_completed"])
            bytes_downloaded = int(row["bytes_downloaded"])
            for filename in detail.download_files:
                cancel_row = self.conn.execute(
                    "SELECT cancel_requested FROM embedding_download_jobs WHERE id=?",
                    (job_id,),
                ).fetchone()
                if cancel_row is None or cancel_row["cancel_requested"]:
                    self.conn.execute(
                        "UPDATE embedding_download_jobs SET status='cancelled', "
                        "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (job_id,),
                    )
                    return
                local_path = hub.hf_hub_download(
                    repo_id=row["model_id"],
                    revision=row["revision"],
                    filename=filename,
                    local_dir=Path(row["target_dir"]),
                    repo_type="model",
                )
                files_completed += 1
                bytes_downloaded += self._file_size(local_path)
                self.conn.execute(
                    "UPDATE embedding_download_jobs SET files_completed=?, "
                    "bytes_downloaded=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (files_completed, bytes_downloaded, job_id),
                )
            self.conn.execute(
                "UPDATE embedding_download_jobs SET status='completed', "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )
        except Exception as exc:
            self.conn.execute(
                "UPDATE embedding_download_jobs SET status='failed', "
                "error_code=?, error_detail=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=?",
                (
                    DOWNLOAD_FAILED_ERROR,
                    self._sanitize_error(exc),
                    job_id,
                ),
            )

    def cancel(self, job_id: str) -> None:
        self.conn.execute(
            "UPDATE embedding_download_jobs SET cancel_requested=1, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (job_id,),
        )

    def status(self, job_id: str) -> EmbeddingDownloadJob:
        return self._load_job(job_id)

    def _load_job(self, job_id: str) -> EmbeddingDownloadJob:
        row = self._fetch_job(job_id)
        if row is None:
            raise ValueError(JOB_NOT_FOUND_ERROR)
        return _row_to_job(row)

    def _fetch_job(self, job_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM embedding_download_jobs WHERE id=?",
            (job_id,),
        ).fetchone()

    @staticmethod
    def _file_size(local_path: Any) -> int:
        if not local_path:
            return 0
        try:
            return Path(local_path).stat().st_size
        except OSError:
            return 0

    @staticmethod
    def _sanitize_error(exc: Exception) -> str:
        message = str(exc) or exc.__class__.__name__
        return message[:ERROR_DETAIL_MAX_LENGTH]


def _row_to_job(row: sqlite3.Row) -> EmbeddingDownloadJob:
    return EmbeddingDownloadJob(
        id=row["id"],
        kind=row["kind"],
        model_id=row["model_id"],
        revision=row["revision"],
        target_dir=row["target_dir"],
        status=row["status"],
        files_total=row["files_total"],
        files_completed=row["files_completed"],
        bytes_downloaded=row["bytes_downloaded"],
        cancel_requested=bool(row["cancel_requested"]),
        error_code=row["error_code"],
        error_detail=row["error_detail"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
