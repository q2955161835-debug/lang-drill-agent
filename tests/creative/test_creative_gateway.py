from pathlib import Path

from langdrill_agent.creative.gateway import (
    AgentRuntimeGateway,
    CreativeToolResult,
)
from langdrill_agent.creative.pi_adapter import PiRunRequest
from langdrill_agent.creative.repository import CreativeRepository
from langdrill_agent.db import connect, init_db
from langdrill_agent.runtime.models import AgentRunStep
from langdrill_agent.runtime.repository import AgentRunRepository


class FakeAdapter:
    def __init__(self, events):
        self.events = events
        self.results: list[dict] = []

    def run(self, request):
        yield from self.events

    def send_tool_result(self, **payload):
        self.results.append(payload)


class FakeExecutor:
    def execute(self, request):
        return CreativeToolResult(
            output="verified",
            is_error=False,
            evidence={"path_exists": True, "content_hash": "sha256:abc"},
        )


def seed_creative_run(conn) -> str:
    creative = CreativeRepository(conn)
    creative.save_runtime_status(state="ready", version="0.80.10")
    creative.save_settings(enabled=True, permission_profile="full_access")
    repo = AgentRunRepository(conn)
    run = repo.create(
        session_id="session-1",
        task_type="agentic_task",
        goal="write report",
        completion_criteria=["policy-authorized tool evidence is verified"],
    )
    repo.replace_plan(
        run.id,
        [
            AgentRunStep(
                id="",
                run_id=run.id,
                sequence=1,
                title="Execute through Pi",
                description="Use policy-checked tools and persist evidence.",
                tool_names=["pi.execute"],
                completion_criteria=["policy-authorized tool evidence is verified"],
            )
        ],
    )
    return run.id


def request(run_id: str) -> PiRunRequest:
    return PiRunRequest(
        request_id=run_id,
        prompt="write report",
        provider="openai",
        model="gpt-test",
    )


def test_gateway_completes_only_after_persisted_tool_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.db"
    init_db(db_path)

    with connect(db_path) as conn:
        run_id = seed_creative_run(conn)
        adapter = FakeAdapter(
            [
                {
                    "type": "tool.requested",
                    "requestId": run_id,
                    "toolCallId": "pi-tool-1",
                    "toolName": "write",
                    "arguments": {"path": str(tmp_path / "report.md"), "content": "ok"},
                },
                {"type": "run.completed", "requestId": run_id},
            ]
        )
        AgentRuntimeGateway(
            conn,
            adapter,
            workspace_root=tmp_path,
            tool_executor=FakeExecutor(),
        ).execute(run_id, request(run_id))

        repo = AgentRunRepository(conn)
        assert repo.get(run_id).status == "completed"
        assert repo.steps(run_id)[0].evidence["criteria"] == {
            "policy-authorized tool evidence is verified": True
        }
        assert repo.tool_calls(run_id)[0].status == "completed"
        assert len(adapter.results) == 1


def test_gateway_pauses_when_pi_finishes_without_tool_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway.db"
    init_db(db_path)

    with connect(db_path) as conn:
        run_id = seed_creative_run(conn)
        adapter = FakeAdapter(
            [{"type": "run.completed", "requestId": run_id}]
        )
        AgentRuntimeGateway(conn, adapter, workspace_root=tmp_path).execute(
            run_id,
            request(run_id),
        )

        repo = AgentRunRepository(conn)
        assert repo.get(run_id).status == "paused"
        assert repo.get(run_id).error_code == "VERIFICATION_EVIDENCE_MISSING"
        assert repo.steps(run_id)[0].status == "failed"
