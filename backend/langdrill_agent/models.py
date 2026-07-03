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
    general_chat = "general_chat"
    daily_drill = "daily_drill"
    extra_drill_setup = "extra_drill_setup"
    continue_drill = "continue_drill"
    answer_question = "answer_question"
    explanation = "explanation"
    branch_chat = "branch_chat"
    settings = "settings"
    summary = "summary"


class UserProfile(BaseModel):
    display_name: str = "boss"
    target_language: str = "英语"
    exam_id: str = "cet4"
    exam_name: str = "大学英语四级"
    deadline: str | None = None
    daily_minutes: int = 35
    learning_goal: str = ""
    learning_background: str = ""
    persona: Literal["none", "warm", "professional", "humorous", "custom"] = "professional"
    global_user_prompt: str = ""


class ChatAttachment(BaseModel):
    type: Literal["image"] = "image"
    filename: str = ""
    mime_type: str = ""
    data_url: str = ""


class ChatRequest(BaseModel):
    content: str
    session_id: str | None = None
    selected_text: str | None = None
    selected_option: str | None = None
    question_id: str | None = None
    extra_prompt: str = ""
    force_new_session: bool = False
    attachments: list[ChatAttachment] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session_id: str
    message: dict[str, Any]
    daily_panel: dict[str, Any]
    active_question: dict[str, Any] | None = None
    answered_question: dict[str, Any] | None = None
    token_usage: dict[str, Any]
    learning_stats: dict[str, Any]


class ContextSettingsRequest(BaseModel):
    max_tokens: int = Field(default=1_000_000, ge=1_000, le=10_000_000)
    session_id: str | None = None


class ContextCompressRequest(BaseModel):
    session_id: str
    target_tokens: int | None = Field(default=None, ge=500, le=200_000)


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


class AuthoredQuestion(BaseModel):
    type: Literal["multiple_choice", "short_answer", "cloze", "translation"] = "multiple_choice"
    prompt: str = Field(min_length=6)
    options: list[str] = Field(default_factory=list)
    answer: dict[str, Any]
    explanation: str = Field(min_length=6)
    knowledge_tags: list[str] = Field(default_factory=list)
    difficulty: float = Field(ge=0, le=1, default=0.5)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class AuthoredQuestionSet(BaseModel):
    opening_message: str = ""
    questions: list[AuthoredQuestion] = Field(default_factory=list)


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
    attachments: list[ChatAttachment] = Field(default_factory=list)


class InitRequest(BaseModel):
    provider_id: str = "mimo"
    model: str = "mimo-v2.5-pro"
    base_url: str = "https://api.xiaomimimo.com/anthropic"
    api_key: str = ""
    display_name: str = "boss"
    target_language: str = "英语"
    exam_id: str = "cet4"
    exam_name: str = "大学英语四级"
    deadline: str | None = None
    learning_goal: str = ""
    learning_background: str = ""
    search_years: int = Field(default=3, ge=1, le=10)


class BranchRequest(BaseModel):
    session_id: str
    selected_text: str = Field(min_length=1)
    message: str


class BranchMessageRequest(BaseModel):
    message: str = Field(min_length=1)


class ModelConfigRequest(BaseModel):
    provider_id: str = "mimo"
    model: str = "mimo-v2.5-pro"
    base_url: str = "https://api.xiaomimimo.com/anthropic"
    api_key: str = ""
    thinking_level: str = "enabled"
    thinking_level_options: list[dict[str, Any]] = Field(default_factory=list)
    api_format: str = ""
    vision: bool | None = None


class ModelListRefreshRequest(BaseModel):
    provider_id: str = "mimo"
    base_url: str = ""
    api_key: str = ""
    api_format: str = ""


class ModelVisibilityRequest(BaseModel):
    provider_id: str
    model: str
    visible: bool = True


class CustomModelRequest(BaseModel):
    provider_id: str
    model: str
    label: str = ""
    context_tokens: int = Field(default=0, ge=0)
    vision: bool = False


class MinerUConfigRequest(BaseModel):
    token: str = ""
    clear_token: bool = False


class AddCustomProviderRequest(BaseModel):
    name: str
    base_url: str
    default_model: str


class QuestionDatabaseFolderRequest(BaseModel):
    folder: str
    migrate: bool = True
    overwrite: bool = False


class QuestionDatabaseFolderSelectRequest(BaseModel):
    initial_folder: str = ""
    title: str = "选择题目数据库文件夹"


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    target_language: str | None = None
    exam_id: str | None = None
    exam_name: str | None = None
    deadline: str | None = None
    learning_goal: str | None = None
    learning_background: str | None = None
    persona: str | None = None
    global_user_prompt: str | None = None
    daily_minutes: int | None = None


class ScreenshotImportRequest(BaseModel):
    text: str
    session_id: str | None = None
    import_to_session: bool = False
    auto_start_drill: bool = False
    force_new_session: bool = False
    source_image_path: str = ""


class SyllabusCheckRequest(BaseModel):
    exam_id: str


class SyllabusSelectRequest(BaseModel):
    exam_id: str
    source_id: str


class PastPaperSelectRequest(BaseModel):
    exam_id: str
    paper_ids: list[str] = Field(default_factory=list)


class PastPaperImportRequest(BaseModel):
    exam_id: str
    title: str
    year: int | None = None
    source_url: str = ""
    local_path: str = ""
    summary: str = ""
    question_types: list[str] = Field(default_factory=list)
    raw_text: str = ""
    parse_now: bool = True


class PastPaperDraftRequest(BaseModel):
    exam_id: str
    title: str = ""
    year: int | None = None
    source_url: str = ""
    local_path: str = ""
    summary: str = ""
    question_types: list[str] = Field(default_factory=list)
    raw_text: str = ""
    filename: str = ""


class PastPaperSearchImportRequest(BaseModel):
    exam_id: str
    source_website: str = ""


class PastPaperParseRequest(BaseModel):
    exam_id: str
    paper_id: str


class QuestionTypeSelectRequest(BaseModel):
    exam_id: str
    enabled_type_ids: list[str] = Field(default_factory=list)


class AgentSettingsPermissionRequest(BaseModel):
    enabled_feature_ids: list[str] = Field(default_factory=list)


class SkillToggleRequest(BaseModel):
    skill_id: str
    enabled: bool = True


class PhoneMirrorStartRequest(BaseModel):
    device_id: str = ""
