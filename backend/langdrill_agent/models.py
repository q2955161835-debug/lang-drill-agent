from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentName(str, Enum):
    orchestrator = "orchestrator"
    question_author = "question_author"
    evaluator_tutor = "evaluator_tutor"


class TaskType(str, Enum):
    onboarding = "onboarding"
    daily_drill = "daily_drill"
    answer_question = "answer_question"
    branch_chat = "branch_chat"
    settings = "settings"
    summary = "summary"


class UserProfile(BaseModel):
    display_name: str = "boss"
    target_language: str = "未设置"
    exam_id: str = "unassigned"
    exam_name: str = "未设置"
    deadline: str | None = None
    daily_minutes: int = 35
    learning_goal: str = ""
    learning_background: str = ""
    persona: Literal["none", "warm", "professional", "humorous", "custom"] = "professional"
    global_user_prompt: str = ""


class ChatRequest(BaseModel):
    content: str
    session_id: str | None = None
    selected_text: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    message: dict[str, Any]
    daily_panel: dict[str, Any]
    active_question: dict[str, Any] | None = None
    token_usage: dict[str, int]


class Question(BaseModel):
    id: str
    session_id: str
    sequence: int
    type: Literal["multiple_choice", "short_answer", "cloze", "translation"]
    prompt: str = Field(min_length=6)
    options: list[str] = Field(default_factory=list)
    answer: dict[str, Any]
    explanation: str = Field(min_length=6)
    knowledge_tags: list[str] = Field(default_factory=list)
    difficulty: float = Field(ge=0, le=1, default=0.5)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    is_correct: bool
    feedback: str
    mastery_delta: float
    next_action: str


class PromptPack(BaseModel):
    system_modules: list[dict[str, Any]]
    context_pack: dict[str, Any]
    user_content: str
    output_schema: dict[str, Any] | None = None


class InitRequest(BaseModel):
    provider_id: str = "mock"
    model: str = "mock-tutor-v1"
    base_url: str = ""
    api_key: str = ""
    display_name: str = "boss"
    target_language: str = "未设置"
    exam_id: str = "unassigned"
    exam_name: str = "未设置"
    learning_goal: str = ""
    learning_background: str = ""
    search_years: int = Field(default=3, ge=1, le=10)


class BranchRequest(BaseModel):
    session_id: str
    selected_text: str = Field(min_length=1)
    message: str


class ModelConfigRequest(BaseModel):
    provider_id: str = "mock"
    model: str = "mock-tutor-v1"
    base_url: str = ""
    api_key: str = ""
