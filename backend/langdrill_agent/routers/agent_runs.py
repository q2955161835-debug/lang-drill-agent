from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..db import init_db, transaction
from ..runtime.models import RunStatus
from ..runtime.repository import AgentRunRepository
from ..utils import dumps

router = APIRouter(prefix="/api/agent-runs", tags=["agent-runs"])
_TERMINAL_STATUSES = {
    RunStatus.completed,
    RunStatus.failed,
    RunStatus.cancelled,
}


def _not_found(run_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "AGENT_RUN_NOT_FOUND", "params": {"run_id": run_id}},
    )


@router.get("/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        try:
            run = AgentRunRepository(conn).get(run_id)
        except KeyError as exc:
            raise _not_found(run_id) from exc
    return {"run": run.model_dump(mode="json")}


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str) -> dict[str, Any]:
    init_db()
    with transaction() as conn:
        repo = AgentRunRepository(conn)
        try:
            run = repo.get(run_id)
            if run.status not in _TERMINAL_STATUSES:
                run = repo.set_status(run_id, RunStatus.cancelled)
                repo.append_event(run_id, "cancelled", {})
        except KeyError as exc:
            raise _not_found(run_id) from exc
    return {"run": run.model_dump(mode="json")}


@router.get("/{run_id}/events")
def stream_run_events(run_id: str, after: int = 0) -> StreamingResponse:
    init_db()
    with transaction() as conn:
        try:
            AgentRunRepository(conn).get(run_id)
        except KeyError as exc:
            raise _not_found(run_id) from exc

    def event_stream() -> Iterator[str]:
        last_event_id = max(after, 0)
        while True:
            with transaction() as conn:
                repo = AgentRunRepository(conn)
                try:
                    run = repo.get(run_id)
                    events = repo.events_after(run_id, last_event_id)
                except KeyError:
                    return
            for event in events:
                last_event_id = event.id
                yield (
                    f"id: {event.id}\n"
                    f"event: {event.event_type}\n"
                    f"data: {dumps(event.payload)}\n\n"
                )
            if run.status in _TERMINAL_STATUSES and not events:
                return
            time.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
