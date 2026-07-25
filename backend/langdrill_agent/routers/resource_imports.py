from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..db import init_db, transaction
from ..resource_imports.models import ImportTarget
from ..resource_imports.service import ResourceImportError, ResourceImportService

router = APIRouter(prefix="/api/resource-imports", tags=["resource-imports"])


class ParseRequest(BaseModel):
    title: str = ""
    language: str = ""
    exam_id: str = ""
    year: int | None = None
    source_url: str = ""
    parser: Literal["auto", "mineru", "rapidocr", "text"] = "auto"


class ConfirmRequest(ParseRequest):
    confirmed: bool


def _error_status(code: str) -> int:
    if code in {
        "RESOURCE_IMPORT_TYPE_UNSUPPORTED",
        "RESOURCE_IMPORT_EMPTY",
        "RESOURCE_IMPORT_TOO_LARGE",
        "RESOURCE_IMPORT_CONFIRMATION_REQUIRED",
    }:
        return 400
    if code == "RESOURCE_IMPORT_PREVIEW_REQUIRED":
        return 409
    return 400


@router.post("/stage", status_code=status.HTTP_202_ACCEPTED)
async def stage(
    request: Request,
    target: ImportTarget,
    filename: str,
) -> dict[str, Any]:
    init_db()
    data = await request.body()
    mime_type = request.headers.get("content-type", "application/octet-stream")
    with transaction() as conn:
        service = ResourceImportService(conn)
        try:
            item = service.stage_bytes(
                target=target,
                filename=filename,
                mime_type=mime_type,
                data=data,
            )
        except ResourceImportError as exc:
            raise HTTPException(
                status_code=_error_status(exc.code),
                detail={"code": exc.code, "params": {}},
            ) from exc
    return {"item": item.model_dump(mode="json")}


@router.post("/{import_id}/parse")
def parse(import_id: str, request: ParseRequest) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        service = ResourceImportService(conn)
        try:
            item = service.parse(
                import_id,
                metadata=request.model_dump(exclude_none=False),
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "RESOURCE_IMPORT_NOT_FOUND",
                    "params": {"import_id": import_id},
                },
            ) from exc
        except ResourceImportError as exc:
            raise HTTPException(
                status_code=_error_status(exc.code),
                detail={"code": exc.code, "params": {}},
            ) from exc
    return {"item": item.model_dump(mode="json")}


@router.post("/{import_id}/confirm")
def confirm(import_id: str, request: ConfirmRequest) -> dict[str, Any]:
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail={"code": "RESOURCE_IMPORT_CONFIRMATION_REQUIRED", "params": {}},
        )
    init_db()
    with transaction() as conn:
        service = ResourceImportService(conn)
        try:
            result = service.confirm(
                import_id,
                metadata=request.model_dump(exclude={"confirmed"}, exclude_none=False),
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "RESOURCE_IMPORT_NOT_FOUND",
                    "params": {"import_id": import_id},
                },
            ) from exc
        except ResourceImportError as exc:
            raise HTTPException(
                status_code=_error_status(exc.code),
                detail={"code": exc.code, "params": {}},
            ) from exc
    return result


@router.delete("/{import_id}")
def cancel(import_id: str) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        service = ResourceImportService(conn)
        try:
            item = service.cancel(import_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "RESOURCE_IMPORT_NOT_FOUND",
                    "params": {"import_id": import_id},
                },
            ) from exc
    return {"item": item.model_dump(mode="json")}
