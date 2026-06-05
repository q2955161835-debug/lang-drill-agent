from langdrill_agent.algorithm import MasteryInputs, mastery_score, next_review_at
from langdrill_agent import services as service_module
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import Question
from langdrill_agent.services import ModelConfigService
from langdrill_agent.task_router import TaskRouter
from langdrill_agent.validator import QuestionValidator


def test_mastery_score_penalizes_wrong_repeat():
    strong = mastery_score(
        MasteryInputs(
            correct_rate=1,
            days_since_last_attempt=0,
            difficulty=0.4,
            answered_after_hint=False,
            answered_in_integrated_item=True,
            wrong_repeat_count=0,
        )
    )
    weak = mastery_score(
        MasteryInputs(
            correct_rate=0,
            days_since_last_attempt=10,
            difficulty=0.8,
            answered_after_hint=True,
            answered_in_integrated_item=False,
            wrong_repeat_count=3,
        )
    )
    assert strong > weak
    assert next_review_at(weak) < next_review_at(strong)


def test_task_router_answers_active_question():
    router = TaskRouter()
    assert router.route("A", has_active_question=True).value == "answer_question"
    assert router.route("今天学まで", has_active_question=False).value == "daily_drill"


def test_question_validator_accepts_structured_question():
    question = Question(
        id="q1",
        session_id="s1",
        sequence=1,
        type="multiple_choice",
        prompt="第 1 题：选择正确答案。",
        options=["到终点", "从起点"],
        answer={"correct": "到终点", "letter": "A"},
        explanation="まで表示到达的终点。",
        knowledge_tags=["particle:まで"],
    )
    assert QuestionValidator().validate(question) == question


def test_add_custom_provider_persists_provider(tmp_path):
    db_path = tmp_path / "agent.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        service = ModelConfigService(conn)
        service.add_custom_provider("My Provider", "https://example.test/v1", "my-model")
        providers = service.providers()

    custom = next(provider for provider in providers if provider["label"] == "My Provider（自定义）")
    assert custom["base_url"] == "https://example.test/v1"
    assert custom["model"] == "my-model"


def test_reset_model_defaults_clears_custom_provider_and_secret(tmp_path, monkeypatch):
    for key in (
        "LANGDRILL_DEFAULT_PROVIDER",
        "LANGDRILL_DEFAULT_MODEL",
        "LANGDRILL_PROVIDER_BASE_URL",
        "LANGDRILL_PROVIDER_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(service_module, "PROJECT_ROOT", tmp_path)
    db_path = tmp_path / "agent.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        service = ModelConfigService(conn)
        service.add_custom_provider("My Provider", "https://example.test/v1", "my-model")
        service.save("openai", "https://api.example.test/v1", "gpt-test", "secret-test")
        config = service.reset_defaults()
        providers = service.providers()

    assert config["provider_id"] == "mock"
    assert config["model"] == "mock-tutor-v1"
    assert not config["has_api_key"]
    assert not any(provider["id"].startswith("custom_") for provider in providers)
    assert "LANGDRILL_PROVIDER_API_KEY=" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_empty_process_env_does_not_override_env_file_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(service_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("LANGDRILL_PROVIDER_API_KEY", "")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LANGDRILL_DEFAULT_PROVIDER=mimo",
                "LANGDRILL_DEFAULT_MODEL=mimo-v2.5",
                "LANGDRILL_PROVIDER_BASE_URL=https://api.example.test/v1",
                "LANGDRILL_PROVIDER_API_KEY=file-secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "agent.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        service = ModelConfigService(conn)
        service.save("mimo", "https://api.example.test/v1", "mimo-v2.5", "")
        config = service.current_with_secret()

    assert config["provider_id"] == "mimo"
    assert config["model"] == "mimo-v2.5"
    assert config["api_key"] == "file-secret"
