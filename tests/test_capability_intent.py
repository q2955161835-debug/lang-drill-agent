import pytest

from langdrill_agent.runtime.intent import CapabilityIntentClassifier


@pytest.mark.parametrize(
    "text",
    [
        "帮我给这个项目增加导出功能",
        "请安装并配置这个工具",
        "请整理这个目录并生成报告",
    ],
)
def test_classifier_detects_agentic_actions(text: str) -> None:
    intent = CapabilityIntentClassifier().classify(text)

    assert intent.requires_runtime is True
    assert intent.reason == "explicit_action"


def test_classifier_does_not_capture_learning_request() -> None:
    intent = CapabilityIntentClassifier().classify("给我出五道四级阅读题")

    assert intent.requires_runtime is False
    assert intent.reason == "learning_flow"
