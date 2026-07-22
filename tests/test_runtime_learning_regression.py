from langdrill_agent.models import TaskType
from langdrill_agent.runtime.intent import CapabilityIntentClassifier
from langdrill_agent.task_router import TaskRouter


def test_greeting_remains_general_chat() -> None:
    task = TaskRouter().route("你好，今天状态怎么样？", has_active_question=False)

    assert task is TaskType.general_chat


def test_explicit_drill_remains_daily_drill() -> None:
    task = TaskRouter().route("给我出五道阅读题", has_active_question=False)

    assert task is TaskType.daily_drill


def test_structured_answer_remains_answer_question() -> None:
    task = TaskRouter().route(
        "我选 A",
        has_active_question=True,
        selected_option="A",
    )

    assert task is TaskType.answer_question


def test_creative_capability_detection_does_not_replace_learning_route() -> None:
    text = "给我出五道阅读题"

    task = TaskRouter().route(text, has_active_question=False)
    intent = CapabilityIntentClassifier().classify(text)

    assert task is TaskType.daily_drill
    assert intent.requires_runtime is False
