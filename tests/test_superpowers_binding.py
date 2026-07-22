import json

from langdrill_agent.providers import ModelResult
from langdrill_agent.runtime.planner import AgentRunPlanner
from langdrill_agent.runtime.workflows import WorkflowResolver


def test_complex_code_task_gets_superpowers_chain() -> None:
    skills = WorkflowResolver().resolve(
        "重构后端权限并新增数据库迁移和桌面发布，修改多个文件并运行完整测试"
    )

    assert [skill.id for skill in skills][:3] == [
        "using-superpowers",
        "brainstorming",
        "writing-plans",
    ]
    assert "test-driven-development" in {skill.id for skill in skills}
    assert "verification-before-completion" in {skill.id for skill in skills}


def test_simple_code_question_does_not_get_full_chain() -> None:
    assert WorkflowResolver().resolve("解释这段正则") == []


def test_planner_records_resolved_workflow_skills() -> None:
    class Provider:
        def complete(self, pack):
            return ModelResult(
                content=json.dumps(
                    {
                        "goal": "Refactor permissions and release",
                        "completion_criteria": ["all tests pass"],
                        "steps": [
                            {
                                "title": "Implement verified change",
                                "description": "Apply the migration and verify permissions.",
                                "tool_names": ["runtime.review"],
                                "completion_criteria": ["all tests pass"],
                                "max_attempts": 2,
                            }
                        ],
                    }
                ),
                input_tokens=1,
                output_tokens=1,
                latency_ms=1,
                model="workflow-test",
            )

    plan = AgentRunPlanner(Provider()).plan(
        "重构权限并迁移数据库，然后完成桌面发布和完整测试",
        context={},
        tools=["runtime.review"],
    )

    assert plan.workflow_skill_ids[:3] == [
        "using-superpowers",
        "brainstorming",
        "writing-plans",
    ]
    assert plan.workflow_skill_ids[-1] == "verification-before-completion"


def test_release_or_permission_change_requires_git_and_review_skills() -> None:
    skills = WorkflowResolver().resolve(
        "修改权限模型和三个模块，然后迁移数据库并发布新版本"
    )
    skill_ids = [skill.id for skill in skills]

    assert "using-git-worktrees" in skill_ids
    assert "requesting-code-review" in skill_ids
    assert skill_ids[-1] == "verification-before-completion"
