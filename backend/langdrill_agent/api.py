from __future__ import annotations

import logging
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agents import EvaluatorTutorAgent, OrchestratorAgent, QuestionAuthorAgent, token_totals
from .config import load_settings
from .context import ContextService
from .data_paths import DataPathService
from .db import init_db, transaction
from .logging_config import configure_logging
from .learning_stats import LearningStatsService
from .models import (
    AddCustomProviderRequest,
    AgentSettingsPermissionRequest,
    BranchMessageRequest,
    BranchRequest,
    ChatRequest,
    ChatResponse,
    ContextCompressRequest,
    ContextSettingsRequest,
    InitRequest,
    MinerUConfigRequest,
    ModelConfigRequest,
    ModelListRefreshRequest,
    ModelVisibilityRequest,
    PastPaperDraftRequest,
    PastPaperImportRequest,
    PastPaperParseRequest,
    PastPaperSearchImportRequest,
    PastPaperSelectRequest,
    PhoneMirrorStartRequest,
    ProfileUpdateRequest,
    PromptPack,
    QuestionDatabaseFolderSelectRequest,
    QuestionDatabaseFolderRequest,
    QuestionTypeSelectRequest,
    ScreenshotImportRequest,
    SkillToggleRequest,
    SyllabusCheckRequest,
    SyllabusSelectRequest,
    TaskType,
    UserProfile,
)
from .paper_assets import extract_text_from_file, safe_path_part
from .providers import ModelProvider
from .phone_mirror import PhoneMirrorService
from .screenshot_import import ScreenshotImportService
from .services import (
    AgentSettingsPermissionService,
    MinerUConfigService,
    ModelConfigService,
    PastPaperDraftService,
    PastPaperService,
    ProfileService,
    QuestionService,
    SessionService,
    SkillRegistryService,
    SourceService,
    SyllabusService,
)
from .task_router import TaskRouter
from .utils import dumps, loads, new_id


app = FastAPI(title="Lang Drill Agent API")
logger = logging.getLogger(__name__)


def _missing_agent_permissions(conn, feature_ids: list[str]) -> list[str]:
    permission_service = AgentSettingsPermissionService(conn)
    return [feature_id for feature_id in feature_ids if not permission_service.is_enabled(feature_id)]


def _require_agent_permissions(conn, feature_ids: list[str], detail: str) -> None:
    if _missing_agent_permissions(conn, feature_ids):
        raise HTTPException(status_code=403, detail=detail)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("unhandled api exception", extra={"path": str(request.url.path)})
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request failed before response", extra={"path": request.url.path})
        raise
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "api request",
        extra={"method": request.method, "path": request.url.path, "status": response.status_code, "elapsed_ms": elapsed_ms},
    )
    return response


@app.on_event("startup")
def startup() -> None:
    configure_logging()
    init_db()


def _current_model_provider(conn) -> ModelProvider:
    settings = load_settings()
    model_config = ModelConfigService(conn).current_with_secret()
    return ModelProvider(
        model_config.get("provider_id") or settings.default_provider,
        model_config.get("model") or settings.default_model,
        model_config.get("base_url") or "",
        model_config.get("api_key") or "",
        model_config.get("thinking_level") or "auto",
        api_format=model_config.get("api_format") or "openai-chat-completions",
        reasoning_parameter=model_config.get("reasoning_parameter") or "",
        thinking_api_value=model_config.get("thinking_api_value") or "",
    )


def _question_progress_message(
    progress: dict[str, int],
    active_question: dict | None,
    *,
    created: int = 0,
    opening_message: str = "",
    prefix: str = "",
) -> str:
    total = progress.get("total", 0)
    done = progress.get("done", 0)
    if active_question:
        sequence = int(active_question.get("sequence") or done + 1)
        lead = opening_message.strip() or prefix.strip()
        if not lead:
            lead = f"已准备好第 {sequence} 题 / 共 {total or sequence} 题。"
        if created:
            lead = f"{lead}\n\n本轮已先生成并入库 {created} 道题。"
        return f"{lead}\n\n当前进度：第 {sequence} 题 / 共 {total or sequence} 题。"
    if total and done >= total:
        return f"本轮题目已完成：{done}/{total}。可以输入新的学习内容生成下一轮题组，或输入“总结”查看今日复盘。"
    return prefix or "还没有可展示的题目。请输入今日学习内容，我会先生成完整题组再开始。"


def _answered_question_snapshot(question_payload: dict, selected_option: str, is_correct: bool) -> dict:
    selected_text = selected_option.strip()
    selected_letter = ""
    match = re.search(r"[A-D]", selected_text.upper())
    if match:
        selected_letter = match.group(0)
    options = question_payload.get("options") or []
    selected_answer = selected_text
    if selected_letter:
        index = ord(selected_letter) - ord("A")
        if 0 <= index < len(options):
            selected_answer = str(options[index])
    return {
        **question_payload,
        "status": "answered",
        "selected_option": selected_letter or selected_text,
        "selected_answer": selected_answer,
        "is_correct": is_correct,
    }


def _model_request_error_message(exc: RuntimeError) -> str:
    return (
        f"⚠️ 当前模型请求失败：{exc}\n\n"
        "本次输入已保存在当前会话中；请检查 API Key、Base URL（基础网址）和网络后继续发送。"
    )


_SIMPLE_GREETING_PATTERN = re.compile(
    r"^(?:你?好|您好|hello|hi|hey|早上好|中午好|晚上好|在吗|在不在)[!！。.\s]*$",
    re.IGNORECASE,
)


def _coerce_plain_model_text(content: str, fallback: str) -> str:
    text = content.strip()
    parsed = loads(text, None)
    if isinstance(parsed, dict):
        for key in ("message", "response", "content", "answer", "text"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return fallback
    return text or fallback


def _safe_upload_filename(filename: str) -> str:
    raw_name = Path((filename or "uploaded-file").replace("\\", "/")).name
    suffix = Path(raw_name).suffix.lower()
    stem = safe_path_part(Path(raw_name).stem)
    if not suffix or not re.match(r"^\.[A-Za-z0-9]{1,8}$", suffix):
        suffix = ".txt"
    return f"{stem or 'uploaded-file'}{suffix}"


async def _uploaded_file_to_temp(request: Request, *, filename: str) -> tuple[tempfile.TemporaryDirectory, Path, int]:
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空。")
    max_bytes = 25 * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="上传文件不能超过 25MB。")
    temp_dir = tempfile.TemporaryDirectory(prefix="langdrill-upload-")
    path = Path(temp_dir.name) / _safe_upload_filename(filename)
    path.write_bytes(data)
    return temp_dir, path, len(data)


async def _extract_uploaded_file_text(
    request: Request,
    *,
    filename: str,
    language: str = "ch",
) -> dict:
    temp_dir, path, size = await _uploaded_file_to_temp(request, filename=filename)
    try:
        init_db()
        with transaction() as conn:
            mineru_token = MinerUConfigService(conn).token_for_runtime()
        try:
            text, parser = extract_text_from_file(path, language=language, mineru_token=mineru_token)
        except (OSError, RuntimeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "filename": filename or path.name,
            "text": text,
            "parser": parser,
            "size": size,
        }
    finally:
        temp_dir.cleanup()


def _general_chat_response(
    conn,
    provider: ModelProvider,
    *,
    session_id: str,
    content: str,
    active_question: dict | None,
    attachments: list | None = None,
) -> str:
    text = content.strip()
    image_attachments = [item for item in attachments or [] if getattr(item, "type", "") == "image" and getattr(item, "data_url", "")]
    if _SIMPLE_GREETING_PATTERN.match(text) and not image_attachments:
        if active_question:
            return "你好，boss。我在。当前题组还保留着；你可以继续答题，也可以问我这道题的提示或讲解。"
        return "你好，boss。我在。你可以发词表、说“继续当前题组”，或者先问我学习计划和题目思路。"

    pack = PromptPack(
        system_modules=[
            {
                "id": "general.chat",
                "content": (
                    "你是 Lang Drill Agent 的语言学习聊天助手，了解本程序能力：普通学习聊天、题组练习、答题讲解、"
                    "右侧截图导入、主聊天粘贴词表或拖入文件/图片、分支对话、模型设置、上下文压缩、MinerU 配置、"
                    "历年真题导入、联网功能、本地 Skills 和本地数据库目录设置。普通寒暄、学习建议、澄清问题只自然回复；"
                    "不要生成正式题组，不要声称已经入库题目，不要输出 JSON。如果用户问你是否能导入单词、截图或题目，"
                    "不要说没有后台题库权限；应说明可以在权限开启时通过右侧截图导入、主聊天粘贴词表、"
                    "拖入 TXT/Markdown/PDF/DOCX/图片，或打开联网来源辅助用户手动导入。"
                    "你不能直接读取或填写 API Key、MinerU token、cookie，也不能自行保存模型配置、迁移数据库或导入试卷；"
                    "敏感设置权限开启时也只能生成可确认草稿，最终保存必须由用户确认。"
                    "如果用户想练题，应提醒他明确发送词表、截图导入，或使用“出题/练习/刷题”等请求。"
                ),
            }
        ],
        context_pack={
            "task_type": TaskType.general_chat.value,
            "session_id": session_id,
            "active_question": {
                "id": active_question.get("id"),
                "sequence": active_question.get("sequence"),
                "prompt": active_question.get("prompt"),
            } if active_question else None,
            "attachments": [
                {
                    "type": item.type,
                    "filename": item.filename,
                    "mime_type": item.mime_type,
                }
                for item in image_attachments
            ],
        },
        user_content=text or "请识别并说明这些图片内容。",
        attachments=image_attachments,
    )
    try:
        result = provider.complete(pack)
        _record_model_call(
            conn,
            agent_name="general_chat",
            task_type=TaskType.general_chat.value,
            provider=provider,
            result=result,
            prompt_modules=[module["id"] for module in pack.system_modules],
        )
        return _coerce_plain_model_text(
            result.content,
            "我收到了。你可以继续说明想聊学习计划、题目讲解，还是要开始一组练习。",
        )
    except RuntimeError as exc:
        logger.warning("model request failed during general chat", exc_info=True)
        return _model_request_error_message(exc)


def _screenshot_session_title(parsed: dict) -> str:
    words = parsed.get("words") or []
    if words:
        first = str(words[0].get("term", "")).strip()
        return f"截图词表练习：{first}" if first else "截图词表练习"
    return "截图导入练习"


def _screenshot_drill_content(parsed: dict, exam_name: str) -> str:
    words = parsed.get("words") or []
    lines = [
        f"{str(item.get('term', '')).strip()}: {str(item.get('meaning', '')).strip()}"
        for item in words
        if str(item.get("term", "")).strip()
    ]
    if not lines:
        return str(parsed.get("raw_text") or parsed.get("prompt") or "截图导入内容")
    return (
        f"截图导入词表，已自动开始 {exam_name} 考试式练习。"
        "请基于以下词汇生成语境选择题、完形空格题或阅读式词汇题，"
        "不要生成中文释义匹配题：\n\n"
        + "\n".join(lines)
    )


def _screenshot_target_count(parsed: dict) -> int:
    word_count = len(parsed.get("words") or [])
    if not word_count:
        return 6
    return max(6, min(12, word_count))


def _looks_like_inline_screenshot_words(parsed: dict) -> bool:
    words = parsed.get("words") or []
    options = parsed.get("options") or []
    return parsed.get("confidence") == "vocabulary_list" and len(words) >= 3 and not options


def _screenshot_import_response(
    conn,
    *,
    parsed: dict,
    session_id: str | None,
    source_image_path: str = "",
    force_new_session: bool = False,
    auto_start_drill: bool = False,
) -> dict:
    _require_agent_permissions(
        conn,
        ["screenshot_import", "learning_database"],
        "截图导入或学习数据库权限未开启。请在设置里的「权限」页开启后再导入词表。",
    )
    service = ScreenshotImportService()
    profile = ProfileService(conn).get()
    session_service = SessionService(conn)
    if force_new_session or auto_start_drill or not session_id:
        session_id = session_service.ensure_session(None, _screenshot_session_title(parsed), force_new=True)
    imported_count = service.import_words(
        conn,
        session_id=session_id,
        parsed=parsed,
        exam_id=profile.exam_id,
        source_image_path=source_image_path,
    )
    user_content = f"截图导入文本：\n{parsed['raw_text']}"
    user_msg_id = session_service.add_message(
        session_id,
        "user",
        user_content,
        {
            "source": "screenshot_import",
            "parsed": parsed,
            "imported_count": imported_count,
            "source_image_path": source_image_path,
        },
    )
    response = {
        **parsed,
        "imported": True,
        "imported_count": imported_count,
        "session_id": session_id,
        "message_id": user_msg_id,
        "messages": [{"id": user_msg_id, "role": "user", "content": user_content}],
        "daily_panel": session_service.daily_panel(session_id),
        "learning_stats": LearningStatsService(conn).overview(),
        "token_usage": token_totals(conn, session_id),
        "sessions": session_service.list_sessions_by_date(),
    }
    if not auto_start_drill or not imported_count:
        return response
    try:
        provider = _current_model_provider(conn)
        author_result = QuestionAuthorAgent(conn, provider).ensure_question_set(
            session_id,
            _screenshot_drill_content(parsed, profile.exam_name),
            target_count=_screenshot_target_count(parsed),
        )
        active_question = QuestionService(conn).active_question(session_id)
        progress = QuestionService(conn).question_progress(session_id)
        assistant_content = _question_progress_message(
            progress,
            active_question,
            created=int(author_result.get("created", 0)),
            opening_message=str(author_result.get("opening_message") or ""),
            prefix=f"已导入 {imported_count} 个截图词汇，并自动生成考试式题组。",
        )
        assistant_msg_id = session_service.add_message(
            session_id,
            "assistant",
            assistant_content,
            {"active_question": active_question, "source": "screenshot_auto_drill"},
        )
        response.update(
            {
                "auto_started": True,
                "active_question": active_question,
                "message": {"id": assistant_msg_id, "role": "assistant", "content": assistant_content},
                "messages": [
                    *response["messages"],
                    {"id": assistant_msg_id, "role": "assistant", "content": assistant_content},
                ],
                "daily_panel": session_service.daily_panel(session_id),
                "learning_stats": LearningStatsService(conn).overview(),
                "token_usage": token_totals(conn, session_id),
                "sessions": session_service.list_sessions_by_date(),
            }
        )
    except RuntimeError as exc:
        logger.warning("model request failed during screenshot auto drill", exc_info=True)
        assistant_content = _model_request_error_message(exc)
        assistant_msg_id = session_service.add_message(
            session_id,
            "assistant",
            assistant_content,
            {"source": "screenshot_auto_drill_error"},
        )
        response.update(
            {
                "auto_started": False,
                "generation_error": str(exc),
                "message": {"id": assistant_msg_id, "role": "assistant", "content": assistant_content},
                "messages": [
                    *response["messages"],
                    {"id": assistant_msg_id, "role": "assistant", "content": assistant_content},
                ],
                "sessions": session_service.list_sessions_by_date(),
                "token_usage": token_totals(conn, session_id),
            }
        )
    return response


def _record_model_call(
    conn,
    *,
    agent_name: str,
    task_type: str,
    provider: ModelProvider,
    result,
    prompt_modules: list[str],
    validation_status: str = "not_required",
) -> None:
    conn.execute(
        """
        INSERT INTO model_calls
        (id, agent_name, task_type, provider_id, model, prompt_modules_json,
         input_tokens, output_tokens, latency_ms, validation_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("call"),
            agent_name,
            task_type,
            provider.provider_id,
            result.model,
            dumps(prompt_modules),
            result.input_tokens,
            result.output_tokens,
            result.latency_ms,
            validation_status,
        ),
    )


def _json_object_from_model_text(text: str) -> dict[str, Any]:
    parsed = loads(text.strip(), None)
    if isinstance(parsed, dict):
        return parsed
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    parsed = loads(match.group(0), None)
    return parsed if isinstance(parsed, dict) else {}


def _past_paper_model_hint(
    conn,
    *,
    exam_id: str,
    title: str,
    year: int | None,
    source_url: str,
    local_path: str,
    summary: str,
    question_types: list[str],
    raw_text: str,
    filename: str,
) -> dict[str, Any]:
    provider = _current_model_provider(conn)
    if provider.provider_id == "mock":
        return {}
    bounded_text = raw_text.strip()[:12000]
    pack = PromptPack(
        system_modules=[
            {
                "id": "settings.past_paper_draft",
                "content": (
                    "你是 Lang Drill Agent 的设置页导入助手。"
                    "从用户提供的试卷文件名、文本和已有字段中抽取可编辑的试卷导入草稿。"
                    "只返回 JSON 对象，不要解释；不要长段复制试卷原文。"
                ),
            }
        ],
        context_pack={
            "task_type": "past_paper_draft",
            "exam_id": exam_id,
            "existing_fields": {
                "title": title,
                "year": year,
                "source_url": source_url,
                "local_path": local_path,
                "summary": summary,
                "question_types": question_types,
                "filename": filename,
            },
            "schema": {
                "title": "string",
                "year": "number|null",
                "source_url": "string",
                "local_path": "string",
                "summary": "string",
                "question_types": ["string"],
            },
        },
        user_content=(
            "请抽取并补全以下试卷导入表单字段。summary 只概括题型结构、题量、分值或注意事项，"
            "不要包含受版权限制的大段原文。\n\n"
            f"试卷文本前 12000 字符：\n{bounded_text}"
        ),
        output_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "year": {"type": ["integer", "null"]},
                "source_url": {"type": "string"},
                "local_path": {"type": "string"},
                "summary": {"type": "string"},
                "question_types": {"type": "array", "items": {"type": "string"}},
            },
        },
    )
    result = provider.complete(pack)
    _record_model_call(
        conn,
        agent_name="settings_agent",
        task_type="past_paper_draft",
        provider=provider,
        result=result,
        prompt_modules=[module["id"] for module in pack.system_modules],
        validation_status="model_draft",
    )
    return _json_object_from_model_text(result.content)


def _past_paper_draft_response(
    conn,
    *,
    exam_id: str,
    title: str = "",
    year: int | None = None,
    source_url: str = "",
    local_path: str = "",
    summary: str = "",
    question_types: list[str] | None = None,
    raw_text: str = "",
    filename: str = "",
    include_raw_text: bool = True,
) -> dict[str, Any]:
    draft_service = PastPaperDraftService()
    model_hint: dict[str, Any] = {}
    parser = "heuristic"
    message = "已使用本地规则解析并填入草稿。"
    try:
        model_hint = _past_paper_model_hint(
            conn,
            exam_id=exam_id,
            title=title,
            year=year,
            source_url=source_url,
            local_path=local_path,
            summary=summary,
            question_types=question_types or [],
            raw_text=raw_text,
            filename=filename,
        )
        if any(model_hint.get(key) for key in ("title", "year", "source_url", "local_path", "summary", "question_types")):
            parser = "model"
            message = "已由当前模型解析并填入草稿，保存前仍可修改。"
    except RuntimeError as exc:
        logger.info("past paper draft model fallback", exc_info=True)
        message = f"当前模型不可用，已用本地规则填入草稿：{exc}"
    draft = draft_service.draft(
        exam_id=exam_id,
        title=title,
        year=year,
        source_url=source_url,
        local_path=local_path,
        summary=summary,
        question_types=question_types or [],
        raw_text=raw_text,
        filename=filename,
        model_hint=model_hint,
        include_raw_text=include_raw_text,
    )
    return {"draft": draft, "parser": parser, "message": message}


def _looks_like_past_paper_settings_request(text: str) -> bool:
    lower = text.lower()
    paper_cue = any(token in lower for token in ("真题", "试卷", "样卷", "past paper", "paper", "cet", "ielts", "toefl"))
    action_cue = any(token in lower for token in ("导入", "填写", "填入", "填表", "解析", "设置", "加入", "保存"))
    return paper_cue and action_cue


@app.get("/api/bootstrap")
def bootstrap() -> dict:
    init_db()
    with transaction() as conn:
        profile = ProfileService(conn).get()
        sessions = SessionService(conn).list_sessions_by_date()
        model_config = ModelConfigService(conn)
        current_model_config = model_config.current_for_ui()
        return {
            "profile": profile.model_dump(),
            "sessions": sessions,
            "token_usage": token_totals(conn),
            "providers": model_config.providers(),
            "model_config": current_model_config,
            "exam_options": SyllabusService(conn).exam_options(),
            "syllabus_status": SyllabusService(conn).status(profile.exam_id),
            "past_paper_status": PastPaperService(conn).status(profile.exam_id),
            "learning_stats": LearningStatsService(conn).overview(),
            "data_paths": DataPathService().status(),
            "mineru_config": MinerUConfigService(conn).status(),
            "agent_permissions": AgentSettingsPermissionService(conn).status(),
            "skills_status": SkillRegistryService(conn=conn).status(),
        }


@app.post("/api/initialize")
def initialize(request: InitRequest) -> dict:
    init_db()
    with transaction() as conn:
        profile = ProfileService(conn).get()
        updated = profile.model_copy(
            update={
                "display_name": request.display_name,
                "target_language": request.target_language,
                "exam_id": request.exam_id,
                "exam_name": request.exam_name,
                "deadline": request.deadline,
                "learning_goal": request.learning_goal,
                "learning_background": request.learning_background,
            }
        )
        ProfileService(conn).update(updated)
        SourceService(conn).seed_common_sources()
        ModelConfigService(conn).save(
            request.provider_id,
            request.base_url,
            request.model,
            request.api_key,
        )
        return {
            "profile": updated.model_dump(),
            "next_step": "检查内置考纲；若不是最新版或缺失，再按官方来源下载或索引。",
        }


@app.post("/api/model-config")
def save_model_config(request: ModelConfigRequest) -> dict:
    init_db()
    with transaction() as conn:
        svc = ModelConfigService(conn)
        config = svc.save(
            request.provider_id,
            request.base_url,
            request.model,
            request.api_key,
            thinking_level=request.thinking_level,
            thinking_level_options=request.thinking_level_options,
            api_format=request.api_format,
            vision=request.vision,
        )
        return {"model_config": config, "providers": svc.providers()}


@app.post("/api/model-config/default")
def save_default_model_config(request: ModelConfigRequest) -> dict:
    return save_model_config(request)


@app.post("/api/model-config/models/refresh")
def refresh_provider_models(request: ModelListRefreshRequest) -> dict:
    init_db()
    with transaction() as conn:
        svc = ModelConfigService(conn)
        result = svc.refresh_provider_models(
            request.provider_id,
            request.base_url,
            request.api_key,
            api_format=request.api_format,
        )
        result["model_config"] = svc.current()
        return result


@app.post("/api/model-config/models/visibility")
def set_model_visibility(request: ModelVisibilityRequest) -> dict:
    init_db()
    with transaction() as conn:
        return ModelConfigService(conn).set_model_visibility(
            request.provider_id,
            request.model,
            request.visible,
        )


@app.get("/api/mineru-config")
def mineru_config() -> dict:
    init_db()
    with transaction() as conn:
        return {"mineru_config": MinerUConfigService(conn).status()}


@app.post("/api/mineru-config")
def save_mineru_config(request: MinerUConfigRequest) -> dict:
    init_db()
    with transaction() as conn:
        status = MinerUConfigService(conn).save(request.token, clear_token=request.clear_token)
        return {"mineru_config": status}


@app.get("/api/settings/agent-permissions")
def agent_settings_permissions() -> dict:
    init_db()
    with transaction() as conn:
        return {"agent_permissions": AgentSettingsPermissionService(conn).status()}


@app.post("/api/settings/agent-permissions")
def save_agent_settings_permissions(request: AgentSettingsPermissionRequest) -> dict:
    init_db()
    with transaction() as conn:
        return {"agent_permissions": AgentSettingsPermissionService(conn).save(request.enabled_feature_ids)}


@app.get("/api/skills")
def skills_status() -> dict:
    init_db()
    with transaction() as conn:
        return {"skills_status": SkillRegistryService(conn=conn).status()}


@app.post("/api/skills/enabled")
def set_skill_enabled(request: SkillToggleRequest) -> dict:
    init_db()
    with transaction() as conn:
        return {"skills_status": SkillRegistryService(conn=conn).save_enabled(request.skill_id, request.enabled)}


@app.post("/api/config/providers/custom")
def add_custom_provider(request: AddCustomProviderRequest) -> dict:
    init_db()
    with transaction() as conn:
        svc = ModelConfigService(conn)
        provider = svc.add_custom_provider(request.name, request.base_url, request.default_model)
        return {"status": "ok", "provider": provider, "providers": svc.providers()}


@app.get("/api/data-paths")
def data_paths_status() -> dict:
    return DataPathService().status()


@app.post("/api/data-paths/question-db-folder")
def configure_question_database_folder(request: QuestionDatabaseFolderRequest) -> dict:
    status = DataPathService().configure_question_database_folder(
        request.folder,
        migrate=request.migrate,
        overwrite=request.overwrite,
    )
    return {"data_paths": status, "message": status.get("message", "题目数据库目录已更新。")}


@app.post("/api/data-paths/select-folder")
def select_question_database_folder(request: QuestionDatabaseFolderSelectRequest) -> dict:
    return DataPathService().choose_question_database_folder(
        initial_folder=request.initial_folder,
        title=request.title,
    )


@app.post("/api/files/extract-text")
async def extract_uploaded_file_text(
    request: Request,
    filename: str = "",
    language: str = "ch",
) -> dict:
    return await _extract_uploaded_file_text(request, filename=filename, language=language)


@app.post("/api/settings/defaults")
def reset_settings_defaults() -> dict:
    init_db()
    with transaction() as conn:
        profile = UserProfile()
        ProfileService(conn).update(profile)
        model_config = ModelConfigService(conn)
        config = model_config.reset_defaults()
        return {
            "profile": profile.model_dump(),
            "model_config": config,
            "providers": model_config.providers(),
        }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    init_db()
    with transaction() as conn:
        image_attachments = [item for item in request.attachments if item.type == "image" and item.data_url]
        if image_attachments and not ModelConfigService(conn).current_for_ui().get("vision", False):
            raise HTTPException(status_code=422, detail="当前模型未声明支持图片输入，请先在设置中开启视觉能力，或让文件导入走 MinerU 解析。")
        if not image_attachments and not request.selected_option and not request.question_id and not request.selected_text:
            parsed = ScreenshotImportService().parse_text(request.content)
            if _looks_like_inline_screenshot_words(parsed):
                missing_permissions = _missing_agent_permissions(conn, ["screenshot_import", "learning_database"])
                if missing_permissions:
                    session_service = SessionService(conn)
                    session_id = session_service.ensure_session(
                        request.session_id,
                        request.content or "截图词表导入",
                        force_new=request.force_new_session,
                    )
                    session_service.add_message(
                        session_id,
                        "user",
                        request.content,
                        {"task": "screenshot_import", "blocked_permissions": missing_permissions},
                    )
                    assistant_content = (
                        "我识别到这是截图词表，但截图导入或学习数据库权限已关闭。\n\n"
                        "请在设置里的「权限」页开启「截图导入与词表入库」和「单词、题目与作答数据库」，"
                        "之后再发送词表，我会自动创建截图练习会话并生成考试式题组。"
                    )
                    assistant_msg_id = session_service.add_message(
                        session_id,
                        "assistant",
                        assistant_content,
                        {"source": "screenshot_import_permission_blocked", "blocked_permissions": missing_permissions},
                    )
                    return ChatResponse(
                        session_id=session_id,
                        message={"id": assistant_msg_id, "role": "assistant", "content": assistant_content},
                        daily_panel=session_service.daily_panel(session_id),
                        active_question=None,
                        token_usage=token_totals(conn, session_id),
                        learning_stats=LearningStatsService(conn).overview(),
                    )
                imported = _screenshot_import_response(
                    conn,
                    parsed=parsed,
                    session_id=None,
                    force_new_session=True,
                    auto_start_drill=True,
                )
                message = imported.get("message") or {
                    "id": imported.get("message_id", ""),
                    "role": "assistant",
                    "content": f"已导入 {imported.get('imported_count', 0)} 个截图词汇。",
                }
                session_id = str(imported["session_id"])
                return ChatResponse(
                    session_id=session_id,
                    message=message,
                    daily_panel=imported.get("daily_panel", {}),
                    active_question=imported.get("active_question"),
                    token_usage=token_totals(conn, session_id),
                    learning_stats=LearningStatsService(conn).overview(),
                )
        session_service = SessionService(conn)
        selected_option = (request.selected_option or "").strip().upper()
        extra_prompt = (request.extra_prompt or "").strip()
        visible_content = request.content.strip()
        attachment_names = [item.filename or "图片" for item in image_attachments]
        if image_attachments:
            attachment_line = f"[图片附件：{'、'.join(attachment_names)}]"
            visible_content = f"{visible_content}\n\n{attachment_line}".strip() if visible_content else attachment_line
        if selected_option:
            visible_content = selected_option
            if extra_prompt:
                visible_content = f"{selected_option}\n补充提问：{extra_prompt}"
        session_id = session_service.ensure_session(
            request.session_id,
            visible_content or "日常学习",
            force_new=request.force_new_session,
        )
        question_service = QuestionService(conn)
        selected_question = (
            question_service.question_by_id(request.question_id, session_id)
            if request.question_id
            else None
        )
        active = selected_question or question_service.active_question(session_id)
        if image_attachments:
            task = TaskType.general_chat
        else:
            task = TaskRouter().route(
                visible_content or request.content,
                has_active_question=active is not None,
                selected_text=request.selected_text,
                selected_option=selected_option,
            )
        user_payload = {"task": task.value}
        if image_attachments:
            user_payload["attachments"] = [
                {"type": item.type, "filename": item.filename, "mime_type": item.mime_type}
                for item in image_attachments
            ]
        session_service.add_message(session_id, "user", visible_content or request.content or "图片输入", user_payload)

        provider = _current_model_provider(conn)

        active_question = active  # 默认保持当前题
        answered_question: dict | None = None
        settings_action: dict[str, Any] | None = None

        if task.value == "answer_question" and active:
            # ── 答题：判题、回写，再自动推进到下一道库存题 ──
            answer_content = selected_option or request.content
            try:
                result = EvaluatorTutorAgent(conn, provider).evaluate(
                    session_id,
                    active,
                    answer_content,
                    extra_prompt=extra_prompt,
                )
                answered_question = _answered_question_snapshot(active, answer_content, result.is_correct)
                session_service.mark_completed_if_finished(session_id)
                active_question = QuestionService(conn).active_question(session_id)
                progress = QuestionService(conn).question_progress(session_id)
                if active_question:
                    assistant_content = (
                        f"{result.feedback}\n\n"
                        f"下一题已就绪：第 {active_question.get('sequence')} 题 / 共 {progress['total']} 题。"
                    )
                else:
                    assistant_content = (
                        f"{result.feedback}\n\n"
                        f"本轮题目已完成：{progress['done']}/{progress['total']}。"
                        "可以输入新的学习内容开启下一轮，或输入“总结”查看今日复盘。"
                    )
            except RuntimeError as exc:
                logger.warning("model request failed during answer evaluation", exc_info=True)
                active_question = QuestionService(conn).active_question(session_id)
                assistant_content = _model_request_error_message(exc)

        elif task.value == "explanation" and active:
            # ── 追问 / 讲解：围绕当前题进行解释，不消耗作答次数 ──
            explanation_prompt = (
                f"用户正在做这道题，并提出了追问。\n\n"
                f"题目：{active.get('prompt', '')}\n"
                f"选项：{active.get('options', [])}\n\n"
                f"用户追问：{request.content}\n\n"
                f"请给出讲解和提示，但不要直接告诉正确答案。"
            )
            from .prompt_engine import PromptAssembler, PromptRegistry
            assembler = PromptAssembler(PromptRegistry(conn))
            profile = ProfileService(conn).get()
            pack = assembler.assemble(
                task_type="evaluation",
                exam_id=profile.exam_id,
                persona=profile.persona if profile.persona != "custom" else "professional",
                context_pack={"task_type": "explanation", "question": active},
                user_content=explanation_prompt,
                allow_global_user_prompt=True,
            )
            try:
                model_result = provider.complete(pack)
                _record_model_call(
                    conn,
                    agent_name="evaluator_tutor",
                    task_type="explanation",
                    provider=provider,
                    result=model_result,
                    prompt_modules=[m["id"] for m in pack.system_modules],
                )
                assistant_content = model_result.content
            except RuntimeError as exc:
                logger.warning("model request failed during explanation", exc_info=True)
                assistant_content = _model_request_error_message(exc)

        elif task.value == "continue_drill":
            # ── 推进：只取数据库里的下一道题，不重新初始化今日面板 ──
            active_question = QuestionService(conn).active_question(session_id)
            progress = QuestionService(conn).question_progress(session_id)
            assistant_content = _question_progress_message(
                progress,
                active_question,
                prefix="我会继续当前题组，不重新开始。",
            )

        elif task.value == "settings":
            # ── 设置：有授权的功能可生成可确认设置动作；无授权只引导用户打开设置页 ──
            if _looks_like_past_paper_settings_request(request.content):
                permission_service = AgentSettingsPermissionService(conn)
                if not permission_service.is_enabled("past_paper_import"):
                    assistant_content = (
                        "我可以帮你解析试卷信息并填入「历年真题与题型」表单，但该功能还没有授权。\n\n"
                        "请在设置里的「权限」页开启「历年真题导入与题型」，之后把试卷文本、文件内容或关键信息发给我，"
                        "我会先整理标题、年份、来源、题型和摘要，再让你确认填入。"
                    )
                else:
                    profile = ProfileService(conn).get()
                    draft_result = _past_paper_draft_response(
                        conn,
                        exam_id=profile.exam_id,
                        raw_text=request.content,
                        filename="",
                        include_raw_text=True,
                    )
                    draft = draft_result["draft"]
                    settings_action = {
                        "type": "past_paper_import_draft",
                        "feature_id": "past_paper_import",
                        "label": "填入历年真题导入表单",
                        "draft": draft,
                        "parser": draft_result["parser"],
                        "confirmation_required": True,
                    }
                    assistant_content = (
                        "我已整理出一份试卷导入草稿，请确认后填入设置页再修改保存。\n\n"
                        f"- 标题：{draft.get('title') or '待补充'}\n"
                        f"- 年份：{draft.get('year') or '待补充'}\n"
                        f"- 题型：{'、'.join(draft.get('question_types') or []) or '待补充'}\n"
                        f"- 解析方式：{draft_result['parser']}"
                    )
            else:
                assistant_content = (
                    "请点击左侧栏底部的「设置」按钮来修改模型供应商、学习目标、"
                    "人格等配置。已授权的设置功能可以在会话中先让我整理草稿，再由你确认填入。"
                )

        elif task.value == "summary":
            # ── 总结：生成当日学习总结 ──
            panel = session_service.daily_panel(session_id)
            assistant_content = (
                f"📊 今日学习总结\n\n"
                f"日期：{panel.get('date', '未知')}\n"
                f"题目进度：{panel.get('questions_done', 0)}/{panel.get('questions_total', 0)}\n"
                f"正确率：{int(panel.get('accuracy', 0) * 100)}%\n"
                f"状态：{panel.get('status', '未知')}\n\n"
            )
            plan = panel.get("plan", {})
            new_content = plan.get("new_content", [])
            review_content = plan.get("review_content", [])
            if new_content:
                assistant_content += f"新学内容：{'、'.join(new_content)}\n"
            if review_content:
                assistant_content += f"复习内容：{'、'.join(review_content)}\n"
            if not panel.get("questions_total"):
                assistant_content += "\n今天还没有开始做题，输入学习内容开始吧！"

        elif task.value == "branch_chat" and request.selected_text:
            # ── 分支对话：转发到分支接口 ──
            assistant_content = f"已识别到分支对话请求。请使用选中文本功能或右侧分支面板继续。选中内容：{request.selected_text[:60]}"

        elif task.value == "general_chat":
            # ── 普通聊天：不触发组卷，不写 daily_plan，不新增题目 ──
            active_question = active
            assistant_content = _general_chat_response(
                conn,
                provider,
                session_id=session_id,
                content=request.content or visible_content,
                active_question=active_question,
                attachments=image_attachments,
            )

        else:
            # ── 默认：有库存题先继续；无库存时先生成完整题组入库，再展示第一题 ──
            progress_before = QuestionService(conn).question_progress(session_id)
            if active and progress_before["ready"]:
                active_question = active
                assistant_content = _question_progress_message(
                    progress_before,
                    active_question,
                    prefix="当前题组仍在进行中。",
                )
            else:
                try:
                    OrchestratorAgent(conn, provider).handle_daily_drill(session_id, request.content)
                    author_result = QuestionAuthorAgent(conn, provider).ensure_question_set(session_id, request.content)
                    active_question = QuestionService(conn).active_question(session_id)
                    progress = QuestionService(conn).question_progress(session_id)
                    assistant_content = _question_progress_message(
                        progress,
                        active_question,
                        created=int(author_result.get("created", 0)),
                        opening_message=str(author_result.get("opening_message") or ""),
                    )
                except RuntimeError as exc:
                    logger.warning("model request failed during question generation", exc_info=True)
                    active_question = QuestionService(conn).active_question(session_id)
                    assistant_content = _model_request_error_message(exc)

        assistant_payload = {"active_question": active_question}
        if answered_question:
            assistant_payload["answered_question"] = answered_question
        if settings_action:
            assistant_payload["settings_action"] = settings_action
        msg_id = session_service.add_message(
            session_id,
            "assistant",
            assistant_content,
            assistant_payload,
        )
        return ChatResponse(
            session_id=session_id,
            message={"id": msg_id, "role": "assistant", "content": assistant_content, "payload": assistant_payload},
            daily_panel=session_service.daily_panel(session_id),
            active_question=active_question,
            answered_question=answered_question,
            token_usage=token_totals(conn, session_id),
            learning_stats=LearningStatsService(conn).overview(),
        )


@app.post("/api/branch")
def branch_chat(request: BranchRequest) -> dict:
    init_db()
    with transaction() as conn:
        branch_id = new_id("br")
        conn.execute(
            """
            INSERT INTO branch_conversations (id, session_id, title, selected_text)
            VALUES (?, ?, ?, ?)
            """,
            (branch_id, request.session_id, request.selected_text[:24], request.selected_text),
        )
        conn.execute(
            """
            INSERT INTO branch_messages (id, branch_id, role, content)
            VALUES (?, ?, 'user', ?)
            """,
            (new_id("bmsg"), branch_id, request.message),
        )
        response = f"已开启分支对话。选中内容：{request.selected_text[:80]}"
        conn.execute(
            """
            INSERT INTO branch_messages (id, branch_id, role, content)
            VALUES (?, ?, 'assistant', ?)
            """,
            (new_id("bmsg"), branch_id, response),
        )
        return {"branch_id": branch_id, "message": response}


@app.post("/api/branch/{branch_id}/messages")
def branch_message(branch_id: str, request: BranchMessageRequest) -> dict:
    init_db()
    with transaction() as conn:
        branch = conn.execute(
            "SELECT id, selected_text FROM branch_conversations WHERE id=? AND status!='deleted'",
            (branch_id,),
        ).fetchone()
        if not branch:
            return {"error": "branch_not_found"}
        clean_message = request.message.strip()
        conn.execute(
            "INSERT INTO branch_messages (id, branch_id, role, content) VALUES (?, ?, 'user', ?)",
            (new_id("bmsg"), branch_id, clean_message),
        )
        try:
            provider = _current_model_provider(conn)
            pack = PromptPack(
                system_modules=[
                    {
                        "id": "branch.conversation",
                        "content": "你是语言学习分支对话助手。只围绕选中文本解释、改写、举例或整理复习卡片，默认不写回主会话。",
                    }
                ],
                context_pack={"selected_text": branch["selected_text"], "task_type": "branch_chat"},
                user_content=clean_message,
            )
            result = provider.complete(pack)
            _record_model_call(
                conn,
                agent_name="branch_assistant",
                task_type="branch_chat",
                provider=provider,
                result=result,
                prompt_modules=[m["id"] for m in pack.system_modules],
            )
            response = result.content.strip() or "已收到，请继续补充你想追问的点。"
        except Exception as exc:
            response = f"分支已记录，但当前模型无法回复：{exc}"
        conn.execute(
            "INSERT INTO branch_messages (id, branch_id, role, content) VALUES (?, ?, 'assistant', ?)",
            (new_id("bmsg"), branch_id, response),
        )
        return {"branch_id": branch_id, "message": response}


@app.get("/api/sessions")
def sessions() -> dict:
    init_db()
    with transaction() as conn:
        return {"sessions": SessionService(conn).list_sessions_by_date()}


@app.post("/api/sessions/new")
def new_session() -> dict:
    init_db()
    with transaction() as conn:
        return {
            "session_id": "",
            "draft": True,
            "sessions": SessionService(conn).list_sessions_by_date(),
            "learning_stats": LearningStatsService(conn).overview(),
        }


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    """加载历史会话的完整消息、daily panel 和当前题目。"""
    init_db()
    with transaction() as conn:
        detail = SessionService(conn).load_session_detail(session_id)
        if not detail:
            return {"error": "session_not_found"}
        detail["token_usage"] = token_totals(conn, session_id)
        detail["learning_stats"] = LearningStatsService(conn).overview()
        return detail


@app.get("/api/context")
def context_status(session_id: str | None = None) -> dict:
    init_db()
    with transaction() as conn:
        return {"token_usage": token_totals(conn, session_id), "settings": ContextService(conn).settings()}


@app.post("/api/context/settings")
def context_settings(request: ContextSettingsRequest) -> dict:
    init_db()
    with transaction() as conn:
        settings = ContextService(conn).save_settings(request.max_tokens)
        return {"settings": settings, "token_usage": token_totals(conn, request.session_id)}


@app.post("/api/context/compress")
def context_compress(request: ContextCompressRequest) -> dict:
    init_db()
    with transaction() as conn:
        result = ContextService(conn).compress_session(request.session_id, request.target_tokens)
        result["token_usage"] = {**token_totals(conn, request.session_id), **result["token_usage"]}
        return result


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    init_db()
    with transaction() as conn:
        session_service = SessionService(conn)
        deleted = session_service.delete_session(session_id)
        return {
            "deleted": deleted,
            "sessions": session_service.list_sessions_by_date(),
            "learning_stats": LearningStatsService(conn).overview(),
        }


@app.post("/api/profile")
def update_profile(request: ProfileUpdateRequest) -> dict:
    """持久化用户设置：学习目标、学习背景、人格、全局提示词等。"""
    init_db()
    with transaction() as conn:
        profile_service = ProfileService(conn)
        current = profile_service.get()
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            return {"profile": current.model_dump(), "learning_stats": LearningStatsService(conn).overview()}
        updated = current.model_copy(update=updates)
        profile_service.update(updated)
        return {
            "profile": updated.model_dump(),
            "sessions": SessionService(conn).list_sessions_by_date(),
            "syllabus_status": SyllabusService(conn).status(updated.exam_id),
            "past_paper_status": PastPaperService(conn).status(updated.exam_id),
            "learning_stats": LearningStatsService(conn).overview(),
        }


@app.get("/api/exams")
def exam_options() -> dict:
    init_db()
    with transaction() as conn:
        profile = ProfileService(conn).get()
        return {
            "current_exam_id": profile.exam_id,
            "options": SyllabusService(conn).exam_options(),
        }


@app.get("/api/syllabus/status")
def syllabus_status(exam_id: str | None = None) -> dict:
    init_db()
    with transaction() as conn:
        profile = ProfileService(conn).get()
        return SyllabusService(conn).status(exam_id or profile.exam_id)


@app.post("/api/syllabus/check")
def syllabus_check(request: SyllabusCheckRequest) -> dict:
    init_db()
    with transaction() as conn:
        return SyllabusService(conn).manual_check(request.exam_id)


@app.post("/api/syllabus/select")
def syllabus_select(request: SyllabusSelectRequest) -> dict:
    init_db()
    with transaction() as conn:
        return SyllabusService(conn).select_source(request.exam_id, request.source_id)


@app.get("/api/past-papers/status")
def past_paper_status(exam_id: str | None = None) -> dict:
    init_db()
    with transaction() as conn:
        profile = ProfileService(conn).get()
        return PastPaperService(conn).status(exam_id or profile.exam_id)


@app.post("/api/past-papers/select")
def past_paper_select(request: PastPaperSelectRequest) -> dict:
    init_db()
    with transaction() as conn:
        return PastPaperService(conn).select_papers(request.exam_id, request.paper_ids)


@app.post("/api/past-papers/draft")
def past_paper_draft(request: PastPaperDraftRequest) -> dict:
    init_db()
    with transaction() as conn:
        return _past_paper_draft_response(
            conn,
            exam_id=request.exam_id,
            title=request.title,
            year=request.year,
            source_url=request.source_url,
            local_path=request.local_path,
            summary=request.summary,
            question_types=request.question_types,
            raw_text=request.raw_text,
            filename=request.filename,
            include_raw_text=True,
        )


@app.post("/api/past-papers/import")
def past_paper_import(request: PastPaperImportRequest) -> dict:
    init_db()
    with transaction() as conn:
        return PastPaperService(conn).manual_import(
            exam_id=request.exam_id,
            title=request.title,
            year=request.year,
            source_url=request.source_url,
            local_path=request.local_path,
            summary=request.summary,
            question_types=request.question_types,
            raw_text=request.raw_text,
            parse_now=request.parse_now,
        )


@app.post("/api/past-papers/import-file")
async def past_paper_import_file(
    request: Request,
    exam_id: str,
    title: str,
    filename: str = "",
    year: int | None = None,
    source_url: str = "",
    summary: str = "",
    question_types: str = "",
    parse_now: bool = True,
) -> dict:
    temp_dir, path, _size = await _uploaded_file_to_temp(request, filename=filename)
    try:
        clean_types = [item.strip() for item in re.split(r"[，,\n]", question_types) if item.strip()]
        init_db()
        with transaction() as conn:
            return PastPaperService(conn).manual_import(
                exam_id=exam_id,
                title=title,
                year=year,
                source_url=source_url,
                local_path=str(path),
                summary=summary,
                question_types=clean_types,
                raw_text="",
                parse_now=parse_now,
            )
    finally:
        temp_dir.cleanup()


@app.post("/api/past-papers/draft-file")
async def past_paper_draft_file(
    request: Request,
    exam_id: str,
    filename: str = "",
    title: str = "",
    year: int | None = None,
    source_url: str = "",
    summary: str = "",
    question_types: str = "",
) -> dict:
    temp_dir, path, _size = await _uploaded_file_to_temp(request, filename=filename)
    try:
        init_db()
        with transaction() as conn:
            mineru_token = MinerUConfigService(conn).token_for_runtime()
        try:
            text, file_parser = extract_text_from_file(path, language="ch", mineru_token=mineru_token)
        except (OSError, RuntimeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        clean_types = [item.strip() for item in re.split(r"[，,\n]", question_types) if item.strip()]
        with transaction() as conn:
            result = _past_paper_draft_response(
                conn,
                exam_id=exam_id,
                title=title,
                year=year,
                source_url=source_url,
                local_path=filename or path.name,
                summary=summary,
                question_types=clean_types,
                raw_text=text,
                filename=filename or path.name,
                include_raw_text=False,
            )
            result["file_parser"] = file_parser
            return result
    finally:
        temp_dir.cleanup()


@app.post("/api/past-papers/parse")
def past_paper_parse(request: PastPaperParseRequest) -> dict:
    init_db()
    with transaction() as conn:
        return PastPaperService(conn).parse_existing(request.exam_id, request.paper_id)


@app.post("/api/past-papers/search-import")
def past_paper_search_import(request: PastPaperSearchImportRequest) -> dict:
    init_db()
    with transaction() as conn:
        _require_agent_permissions(
            conn,
            ["web_search_import"],
            "联网功能权限未开启。请在设置里的「权限」页开启「联网功能」。",
        )
        status = PastPaperService(conn).search_import(request.exam_id, request.source_website)
        return {
            **status,
            "skill": SkillRegistryService(conn=conn).status()["web_search_skill"],
        }


@app.post("/api/past-papers/question-types")
def past_paper_question_types(request: QuestionTypeSelectRequest) -> dict:
    init_db()
    with transaction() as conn:
        return PastPaperService(conn).save_question_types(request.exam_id, request.enabled_type_ids)


@app.get("/api/phone-mirror/status")
def phone_mirror_status() -> dict:
    return PhoneMirrorService().status()


@app.post("/api/phone-mirror/start")
def phone_mirror_start(request: PhoneMirrorStartRequest) -> dict:
    return PhoneMirrorService().start(request.device_id)


@app.post("/api/screenshot/parse")
def screenshot_parse(request: ScreenshotImportRequest) -> dict:
    service = ScreenshotImportService()
    parsed = service.parse_text(request.text, request.source_image_path)
    if not request.import_to_session:
        return parsed
    if not request.session_id and not request.auto_start_drill:
        return parsed
    init_db()
    with transaction() as conn:
        return _screenshot_import_response(
            conn,
            parsed=parsed,
            session_id=request.session_id,
            source_image_path=request.source_image_path,
            force_new_session=request.force_new_session,
            auto_start_drill=request.auto_start_drill,
        )
