"""Confirmed local runtime installation with a fixed, untamperable package list."""

from __future__ import annotations

import sqlite3
import sys
from typing import Any, Callable

from ..utils import new_id
from .downloads import _row_to_job
from .models import EmbeddingDownloadJob

RUNTIME_INSTALL_CONFIRMATION_ERROR = (
    "EMBEDDING_RUNTIME_INSTALL_CONFIRMATION_REQUIRED"
)
RUNTIME_INSTALL_FAILED_ERROR = "EMBEDDING_RUNTIME_INSTALL_FAILED"
RUNTIME_JOB_NOT_FOUND_ERROR = "EMBEDDING_RUNTIME_INSTALL_JOB_NOT_FOUND"

RUNTIME_PACKAGES: list[str] = [
    "sentence-transformers>=5.0,<6",
    "safetensors>=0.5,<1",
]

RUNTIME_INSTALL_TIMEOUT_SECONDS = 1800
STDERR_EXCERPT_MAX_LENGTH = 300


class EmbeddingRuntimeInstallService:
    """Install the local embedding runtime via a fixed package list.

    Only ``confirmed=True`` creates a job. ``run`` invokes ``pip install``
    with a hard-coded command derived from ``sys.executable`` and
    ``RUNTIME_PACKAGES``. No package name, index URL, extra pip argument,
    or shell fragment is taken from the request.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        runner: Callable[..., Any] | None = None,
    ) -> None:
        self.conn = conn
        self.runner = runner

    def _resolve_runner(self) -> Callable[..., Any]:
        if self.runner is None:
            import subprocess

            self.runner = subprocess.run
        return self.runner

    def create(self, *, confirmed: bool) -> EmbeddingDownloadJob:
        if not confirmed:
            raise ValueError(RUNTIME_INSTALL_CONFIRMATION_ERROR)
        job_id = new_id("embedrt")
        self.conn.execute(
            """
            INSERT INTO embedding_download_jobs
              (id, kind, model_id, revision, target_dir, status,
               files_total, files_completed, bytes_downloaded,
               cancel_requested, error_code, error_detail)
            VALUES (?, 'runtime', '', '', '', 'pending', 0, 0, 0, 0, '', '')
            """,
            (job_id,),
        )
        return self._load_job(job_id)

    def run(self, job_id: str) -> None:
        row = self.conn.execute(
            "SELECT * FROM embedding_download_jobs WHERE id=? AND kind='runtime'",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError(RUNTIME_JOB_NOT_FOUND_ERROR)
        if row["status"] not in ("pending", "running"):
            return
        self.conn.execute(
            "UPDATE embedding_download_jobs SET status='running', "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (job_id,),
        )
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            *RUNTIME_PACKAGES,
        ]
        runner = self._resolve_runner()
        result = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=RUNTIME_INSTALL_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "")[:STDERR_EXCERPT_MAX_LENGTH]
            self.conn.execute(
                "UPDATE embedding_download_jobs SET status='failed', "
                "error_code=?, error_detail=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=?",
                (RUNTIME_INSTALL_FAILED_ERROR, stderr, job_id),
            )
        else:
            self.conn.execute(
                "UPDATE embedding_download_jobs SET status='completed', "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )

    def status(self, job_id: str) -> EmbeddingDownloadJob:
        return self._load_job(job_id)

    def _load_job(self, job_id: str) -> EmbeddingDownloadJob:
        row = self.conn.execute(
            "SELECT * FROM embedding_download_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError(RUNTIME_JOB_NOT_FOUND_ERROR)
        return _row_to_job(row)
