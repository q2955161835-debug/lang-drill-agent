from pathlib import Path

from langdrill_agent.db import connect, init_db
from langdrill_agent.runtime.models import AgentRunStep
from langdrill_agent.runtime.repository import AgentRunRepository


def _step(sequence: int, title: str) -> AgentRunStep:
    return AgentRunStep(
        id="",
        run_id="",
        sequence=sequence,
        title=title,
        description=f"Execute {title}",
        tool_names=["test.echo"],
        completion_criteria=[f"{title} has evidence"],
        max_attempts=2,
    )


def test_only_one_worker_claims_step(tmp_path: Path) -> None:
    db_path = tmp_path / "agent-runs.db"
    init_db(db_path)

    with connect(db_path) as first_conn, connect(db_path) as second_conn:
        first_repo = AgentRunRepository(first_conn)
        run = first_repo.create(
            session_id="session-1",
            task_type="agentic_task",
            goal="Generate a verified report",
        )
        first_repo.replace_plan(run.id, [_step(1, "Collect evidence")])

        first = first_repo.claim_next_step(run.id, worker_id="worker-1")
        second = AgentRunRepository(second_conn).claim_next_step(
            run.id,
            worker_id="worker-2",
        )

        assert first is not None
        assert first.status == "running"
        assert first.lease_owner == "worker-1"
        assert second is None


def test_restart_resumes_after_last_completed_step(tmp_path: Path) -> None:
    db_path = tmp_path / "agent-runs.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = AgentRunRepository(conn)
        run = repo.create(
            session_id="session-1",
            task_type="agentic_task",
            goal="Generate a verified report",
        )
        steps = repo.replace_plan(
            run.id,
            [
                _step(1, "Collect evidence"),
                _step(2, "Write report"),
            ],
        )
        claimed = repo.claim_next_step(run.id, worker_id="worker-1")
        assert claimed is not None
        repo.complete_step(
            claimed.id,
            evidence={"files": ["evidence.json"]},
            worker_id="worker-1",
        )
        assert steps[0].sequence == 1

    with connect(db_path) as restarted_conn:
        resumed = AgentRunRepository(restarted_conn).claim_next_step(
            run.id,
            worker_id="worker-2",
        )

        assert resumed is not None
        assert resumed.sequence == 2
        assert resumed.title == "Write report"
        assert resumed.attempts == 1


def test_replacing_plan_preserves_old_version_for_audit(tmp_path: Path) -> None:
    db_path = tmp_path / "agent-runs.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = AgentRunRepository(conn)
        run = repo.create(
            session_id=None,
            task_type="agentic_task",
            goal="Produce output",
        )
        first_plan = repo.replace_plan(run.id, [_step(1, "First approach")])
        second_plan = repo.replace_plan(run.id, [_step(1, "Replanned approach")])

        all_steps = repo.steps(run.id, current_plan_only=False)
        current_steps = repo.steps(run.id)

        assert first_plan[0].plan_version == 1
        assert second_plan[0].plan_version == 2
        assert len(all_steps) == 2
        assert all_steps[0].status == "cancelled"
        assert [step.title for step in current_steps] == ["Replanned approach"]


def test_tool_call_and_approval_are_auditable(tmp_path: Path) -> None:
    db_path = tmp_path / "agent-runs.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = AgentRunRepository(conn)
        run = repo.create(
            session_id="session-1",
            task_type="agentic_task",
            goal="Produce output",
        )
        step = repo.replace_plan(run.id, [_step(1, "Write report")])[0]
        claimed = repo.claim_next_step(run.id, worker_id="worker-1")
        assert claimed is not None

        tool_call = repo.record_tool_call(
            run_id=run.id,
            step_id=step.id,
            tool_name="test.echo",
            input_payload={"text": "hello"},
        )
        approval = repo.request_approval(
            run_id=run.id,
            step_id=step.id,
            tool_call_id=tool_call.id,
            capability="write_report",
            risk_level="medium",
            request_payload={"path": "report.md"},
        )

        assert repo.tool_calls(run.id)[0].input_payload == {"text": "hello"}
        assert repo.approvals(run.id)[0].id == approval.id
        assert approval.status == "pending"
