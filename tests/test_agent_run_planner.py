import json

import pytest

from langdrill_agent.providers import ModelResult
from langdrill_agent.runtime.planner import AgentRunPlanner, PlanValidationError


class FakePlannerProvider:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.pack = None

    def complete(self, pack):
        self.pack = pack
        content = json.dumps(self.payload)
        return ModelResult(
            content=content,
            input_tokens=10,
            output_tokens=20,
            latency_ms=1,
            model="planner-test",
        )


def valid_payload() -> dict:
    return {
        "goal": "Organize documents and generate a report",
        "completion_criteria": [
            "report.md exists",
            "report.md contains a summary for every input document",
        ],
        "steps": [
            {
                "title": "Read source documents",
                "description": "Read each supplied document and extract facts.",
                "tool_names": ["documents.read"],
                "completion_criteria": ["Every input document has a recorded content hash"],
                "max_attempts": 2,
            },
            {
                "title": "Write verified report",
                "description": "Write report.md from the extracted facts.",
                "tool_names": ["reports.write"],
                "completion_criteria": ["report.md exists and is not empty"],
                "max_attempts": 2,
            },
        ],
    }


def test_plan_requires_verifiable_criteria_and_known_tools() -> None:
    provider = FakePlannerProvider(valid_payload())
    planner = AgentRunPlanner(provider)

    plan = planner.plan(
        "整理文档并生成报告",
        context={"scope": "workspace"},
        tools=["documents.read", "reports.write"],
    )

    assert plan.completion_criteria
    assert all(step.completion_criteria for step in plan.steps)
    assert [step.sequence for step in plan.steps] == [1, 2]
    assert provider.pack.user_content == "整理文档并生成报告"
    assert "整理文档并生成报告" not in "\n".join(
        module["content"] for module in provider.pack.system_modules
    )


def test_plan_rejects_unknown_tool() -> None:
    payload = valid_payload()
    payload["steps"][0]["tool_names"] = ["shell.unregistered"]
    planner = AgentRunPlanner(FakePlannerProvider(payload))

    with pytest.raises(PlanValidationError, match="unknown tool"):
        planner.plan(
            "整理文档并生成报告",
            context={},
            tools=["documents.read", "reports.write"],
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(completion_criteria=[]),
        lambda payload: payload["steps"][0].update(completion_criteria=[]),
        lambda payload: payload["steps"][1].update(title="Read source documents"),
        lambda payload: payload.update(steps=payload["steps"] * 11),
    ],
)
def test_plan_rejects_unverifiable_duplicate_or_oversized_output(mutation) -> None:
    payload = valid_payload()
    mutation(payload)
    planner = AgentRunPlanner(FakePlannerProvider(payload))

    with pytest.raises(PlanValidationError):
        planner.plan(
            "整理文档并生成报告",
            context={},
            tools=["documents.read", "reports.write"],
        )
