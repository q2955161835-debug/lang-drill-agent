from langdrill_agent.algorithm import MasteryInputs, mastery_score, next_review_at
from langdrill_agent.models import Question
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
