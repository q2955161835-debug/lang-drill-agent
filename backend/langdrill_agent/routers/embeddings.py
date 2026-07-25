"""User-controlled embedding model management API (Plan 2 Task 4).

Exposes settings, model catalog, downloads, runtime install, reindex, and
health probe endpoints under ``/api/embeddings``. Every download, install,
reindex, or activation requires ``confirmed=True``; the API never returns
plaintext tokens, only ``api_key_configured`` flags.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..config import load_settings
from ..db import init_db, transaction
from ..embeddings.catalog import EmbeddingModelCatalog
from ..embeddings.downloads import (
    CONFIRMATION_ERROR as DOWNLOAD_CONFIRMATION_ERROR,
    EmbeddingDownloadService,
)
from ..embeddings.indexing import EmbeddingIndexCoordinator
from ..embeddings.models import EmbeddingIdentity, EmbeddingSettingsPatch
from ..embeddings.runtime import (
    HEALTH_PROBE_FAILED,
    EmbeddingRuntime,
)
from ..embeddings.runtime_install import (
    RUNTIME_INSTALL_CONFIRMATION_ERROR,
    EmbeddingRuntimeInstallService,
)
from ..embeddings.settings import EmbeddingSettingsService

router = APIRouter(prefix="/api/embeddings", tags=["embeddings"])

CONFIRMATION_REQUIRED_ERROR = "EMBEDDING_REINDEX_CONFIRMATION_REQUIRED"
JOB_NOT_FOUND_ERROR = "EMBEDDING_JOB_NOT_FOUND"
ERROR_DETAIL_MAX_LENGTH = 200


class DownloadRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=240)
    revision: str = Field(min_length=1, max_length=120)
    target_dir: str = ""
    confirmed: bool = False


class RuntimeInstallRequest(BaseModel):
    confirmed: bool = False


class ReindexRequest(BaseModel):
    targets: list[Literal["knowledge", "past_papers", "memory"]]
    confirmed: bool = False


class SettingsRequest(BaseModel):
    mode: Literal["off", "local", "huggingface_cloud", "openai_compatible"] | None = None
    model_id: str | None = None
    revision: str | None = None
    dimensions: int | None = Field(default=None, ge=0)
    model_dir: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    activate: bool = False


def _confirmation_error(code: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": code})


def _runtime_status(conn) -> dict[str, Any]:
    return EmbeddingRuntime(conn).status()


def _effective_mode(settings, runtime: dict[str, Any]) -> str:
    if settings.enabled_identity is not None and runtime.get("healthy"):
        return "hybrid"
    return "fts"


@router.get("/status")
def status() -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        settings = EmbeddingSettingsService(conn).get()
        indexes = EmbeddingIndexCoordinator(conn).status()
        runtime = _runtime_status(conn)
        return {
            "settings": settings.model_dump(mode="json"),
            "effective_mode": _effective_mode(settings, runtime),
            "runtime": runtime,
            "indexes": indexes,
        }


@router.post("/settings")
def save_settings(request: SettingsRequest) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        service = EmbeddingSettingsService(conn)
        previous_mode = service.get().mode
        patch = EmbeddingSettingsPatch(
            mode=request.mode,
            model_id=request.model_id,
            revision=request.revision,
            dimensions=request.dimensions,
            model_dir=request.model_dir,
            base_url=request.base_url,
            api_key=request.api_key,
        )
        saved = service.save(patch)
        if request.activate and saved.mode != "off":
            runtime = EmbeddingRuntime(conn)
            try:
                identity = runtime.health_probe(saved)
            except Exception as exc:
                detail = _sanitize_error(exc)
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": HEALTH_PROBE_FAILED,
                        "message": detail,
                    },
                ) from exc
            saved = service.set_enabled_identity(identity)
        if previous_mode != saved.mode:
            EmbeddingIndexCoordinator(conn).mark_stale_all()
        indexes = EmbeddingIndexCoordinator(conn).status()
        runtime = _runtime_status(conn)
        return {
            "settings": saved.model_dump(mode="json"),
            "effective_mode": _effective_mode(saved, runtime),
            "runtime": runtime,
            "indexes": indexes,
        }


@router.get("/models")
def list_models(q: str = "") -> dict[str, Any]:
    catalog = EmbeddingModelCatalog()
    recommendations = catalog.recommendations()
    search_results = catalog.search(q) if q.strip() else []
    return {
        "recommendations": [item.model_dump(mode="json") for item in recommendations],
        "search_results": [item.model_dump(mode="json") for item in search_results],
    }


@router.get("/models/{model_id:path}")
def model_detail(model_id: str, revision: str = "") -> dict[str, Any]:
    catalog = EmbeddingModelCatalog()
    try:
        detail = catalog.detail(model_id, revision=revision or None)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EMBEDDING_MODEL_DETAIL_FAILED",
                "message": _sanitize_error(exc),
            },
        ) from exc
    return {"detail": detail.model_dump(mode="json")}


@router.post("/downloads", status_code=202)
def start_download(request: DownloadRequest, background: BackgroundTasks) -> dict[str, Any]:
    if not request.confirmed:
        raise _confirmation_error(DOWNLOAD_CONFIRMATION_ERROR)
    init_db()
    target_dir = (
        Path(request.target_dir) if request.target_dir else _default_model_dir()
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    with transaction() as conn:
        try:
            job = EmbeddingDownloadService(conn).create(
                request.model_id,
                request.revision,
                target_dir,
                confirmed=True,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": str(exc)},
            ) from exc
        job_payload = job.model_dump(mode="json")
    background.add_task(_run_download_job, job.id)
    return {"job": job_payload}


@router.get("/downloads/{job_id}")
def download_status(job_id: str) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        service = EmbeddingDownloadService(conn)
        try:
            job = service.status(job_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": JOB_NOT_FOUND_ERROR},
            ) from exc
        return {"job": job.model_dump(mode="json")}


@router.post("/downloads/{job_id}/cancel")
def cancel_download(job_id: str) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        service = EmbeddingDownloadService(conn)
        try:
            service.cancel(job_id)
            job = service.status(job_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": JOB_NOT_FOUND_ERROR},
            ) from exc
        return {"job": job.model_dump(mode="json")}


@router.post("/runtime/install", status_code=202)
def install_runtime(
    request: RuntimeInstallRequest, background: BackgroundTasks
) -> dict[str, Any]:
    if not request.confirmed:
        raise _confirmation_error(RUNTIME_INSTALL_CONFIRMATION_ERROR)
    init_db()
    with transaction() as conn:
        job = EmbeddingRuntimeInstallService(conn).create(confirmed=True)
        job_payload = job.model_dump(mode="json")
    background.add_task(_run_runtime_install_job, job.id)
    return {"job": job_payload}


@router.post("/reindex", status_code=202)
def reindex(request: ReindexRequest) -> dict[str, Any]:
    if not request.confirmed:
        raise _confirmation_error(CONFIRMATION_REQUIRED_ERROR)
    init_db()
    with transaction() as conn:
        try:
            results = EmbeddingIndexCoordinator(conn).reindex(
                request.targets, confirmed=True
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": str(exc)},
            ) from exc
        return {"results": results}


@router.post("/test")
def test_connection() -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        runtime = EmbeddingRuntime(conn)
        settings = EmbeddingSettingsService(conn).get()
        try:
            identity = runtime.health_probe(settings)
        except Exception as exc:
            return {"healthy": False, "error": _sanitize_error(exc)}
        return {
            "healthy": True,
            "identity": identity.model_dump(mode="json"),
        }


def _default_model_dir() -> Path:
    return load_settings().user_data_dir / "models" / "embeddings"


def _run_download_job(job_id: str) -> None:
    init_db()
    with transaction() as conn:
        EmbeddingDownloadService(conn).run(job_id)


def _run_runtime_install_job(job_id: str) -> None:
    init_db()
    with transaction() as conn:
        EmbeddingRuntimeInstallService(conn).run(job_id)


def _sanitize_error(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return message[:ERROR_DETAIL_MAX_LENGTH]


__all__ = ["router", "EmbeddingIdentity"]
