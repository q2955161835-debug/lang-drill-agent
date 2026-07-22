from pathlib import Path

import pytest
from pydantic import BaseModel

from langdrill_agent.db import connect, init_db
from langdrill_agent.runtime.executor import AgentRunExecutor
from langdrill_agent.runtime.models import AgentRunStep
from langdrill_agent.runtime.repository import AgentRunRepository
from langdrill_agent.runtime.tools import (
    RuntimeTool,
    ToolExecutionResult,
    ToolInputValidationError,
    ToolRegistry,
)


class EchoInput(BaseModel):
    text: str


def create_run(repo: AgentRunRepository, *, max_attempts: int = 2):
    run = repo.create(
        session_id="session-1",
        task_type="agentic_task",
        goal="Produce a verified echo",
        completion_criteria=["echo persisted"],
    )
    repo.replace_plan(
        run.id,
        [
            AgentRunStep(
                id="",
                run_id="",
                sequence=1,
                title="Produce echo evidence",
                description="hello",
                tool_names=["test.echo"],
                completion_criteria=["echo persisted"],
                max_attempts=max_attempts,
            )
        ],
    )
    return run


def test_executor_records_tool_result_before_step_completion(tmp_path: Path) -> None:
    db_path = tmp_path / "agent-runs.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = AgentRunRepository(conn)
        run = create_run(repo)
        registry = ToolRegistry()
        registry.register(
            RuntimeTool(
                name="test.echo",
                input_model=EchoInput,
                input_factory=lambda step: {"text": step.description},
                execute=lambda payload, context: ToolExecutionResult(
                    output={"echo": payload.text},
                    evidence={
                        "criteria": {"echo persisted": True},
                        "echo": payload.text,
                    },
                ),
            )
        )
        executor = AgentRunExecutor(repo, registry, worker_id="worker-1")

        outcome = executor.tick(run.id)

        assert outcome.status == "step_completed"
        assert outcome.action == "continue"
        assert repo.tool_calls(run.id)[0].status == "completed"
        assert repo.steps(run.id)[0].status == "completed"
        events = repo.events_after(run.id, 0)
        assert [event.event_type for event in events].index(
            "tool_call_completed"
        ) < [event.event_type for event in events].index("step_completed")


def test_failed_verification_retries_then_replans(tmp_path: Path) -> None:
    db_path = tmp_path / "agent-runs.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = AgentRunRepository(conn)
        run = create_run(repo, max_attempts=2)
        registry = ToolRegistry()
        registry.register(
            RuntimeTool(
                name="test.echo",
                input_model=EchoInput,
                input_factory=lambda step: {"text": step.description},
                execute=lambda payload, context: ToolExecutionResult(
                    output={"echo": payload.text},
                    evidence={"criteria": {"echo persisted": False}},
                ),
            )
        )
        executor = AgentRunExecutor(repo, registry, worker_id="worker-1")

        first = executor.tick(run.id)
        second = executor.tick(run.id)

        assert first.action == "retry"
        assert repo.steps(run.id)[0].attempts == 2
        assert second.action == "replan"
        assert repo.get(run.id).status == "paused"
        assert repo.steps(run.id)[0].status == "failed"
        assert len(repo.tool_calls(run.id)) == 2


def test_runtime_tool_rejects_unknown_input_fields() -> None:
    tool = RuntimeTool(
        name="test.echo",
        input_model=EchoInput,
        execute=lambda payload, context: ToolExecutionResult(output={}),
    )

    with pytest.raises(ToolInputValidationError, match="unknown fields"):
        tool.validate_input({"text": "hello", "unexpected": True})


def test_restart_reuses_completed_tool_call_without_duplicate_execution(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "agent-runs.db"
    init_db(db_path)
    executions: list[str] = []

    with connect(db_path) as conn:
        repo = AgentRunRepository(conn)
        run = create_run(repo)
        claimed = repo.claim_next_step(run.id, worker_id="crashed-worker", lease_seconds=1)
        assert claimed is not None
        call = repo.record_tool_call(
            run_id=run.id,
            step_id=claimed.id,
            tool_name="test.echo",
            input_payload={"text": "hello"},
        )
        repo.finish_tool_call(
            call.id,
            status="completed",
            output_payload={"echo": "hello"},
            evidence={
                "criteria": {"echo persisted": True},
                "echo": "hello",
            },
        )
        conn.execute(
            "UPDATE agent_run_steps SET lease_expires_at='2000-01-01 00:00:00' WHERE id=?",
            (claimed.id,),
        )

    with connect(db_path) as restarted_conn:
        restarted_repo = AgentRunRepository(restarted_conn)
        registry = ToolRegistry()
        registry.register(
            RuntimeTool(
                name="test.echo",
                input_model=EchoInput,
                input_factory=lambda step: {"text": step.description},
                execute=lambda payload, context: executions.append(payload.text),
            )
        )

        outcome = AgentRunExecutor(
            restarted_repo,
            registry,
            worker_id="restarted-worker",
        ).tick(run.id)

        assert outcome.status == "step_completed"
        assert executions == []
        assert len(restarted_repo.tool_calls(run.id)) == 1
        assert restarted_repo.steps(run.id)[0].status == "completed"


def test_cancelled_run_does_not_start_tool(tmp_path: Path) -> None:
    db_path = tmp_path / "agent-runs.db"
    init_db(db_path)
    calls: list[str] = []

    with connect(db_path) as conn:
        repo = AgentRunRepository(conn)
        run = create_run(repo)
        repo.set_status(run.id, "cancelled")
        registry = ToolRegistry()
        registry.register(
            RuntimeTool(
                name="test.echo",
                input_model=EchoInput,
                input_factory=lambda step: {"text": step.description},
                execute=lambda payload, context: calls.append(payload.text),
            )
        )

        outcome = AgentRunExecutor(repo, registry, worker_id="worker-1").tick(run.id)

        assert outcome.status == "cancelled"
        assert calls == []
        assert repo.tool_calls(run.id) == []
