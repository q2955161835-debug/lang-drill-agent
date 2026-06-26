from __future__ import annotations

import logging
import time

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agents import EvaluatorTutorAgent, OrchestratorAgent, QuestionAuthorAgent, token_totals
from .config import load_settings
from .db import init_db, transaction
from .logging_config import configure_logging
from .models import (
    AddCustomProviderRequest,
    BranchRequest,
    ChatRequest,
    ChatResponse,
    InitRequest,
    ModelConfigRequest,
    PhoneMirrorStartRequest,
    ProfileUpdateRequest,
    ScreenshotImportRequest,
    SyllabusCheckRequest,
    SyllabusSelectRequest,
    UserProfile,
)
from .providers import ModelProvider
from .phone_mirror import PhoneMirrorService
from .screenshot_import import ScreenshotImportService
from .services import (
    ModelConfigService,
    ProfileService,
    QuestionService,
    SessionService,
    SourceService,
    SyllabusService,
)
from .task_router import TaskRouter
from .utils import new_id


app = FastAPI(title="Lang Drill Agent API")
logger = logging.getLogger(__name__)

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


@app.get("/api/bootstrap")
def bootstrap() -> dict:
    init_db()
    with transaction() as conn:
        profile = ProfileService(conn).get()
        sessions = SessionService(conn).list_sessions_by_date()
        model_config = ModelConfigService(conn)
        return {
            "profile": profile.model_dump(),
            "sessions": sessions,
            "token_usage": token_totals(conn),
            "providers": model_config.providers(),
            "model_config": model_config.current(),
            "exam_options": SyllabusService(conn).exam_options(),
            "syllabus_status": SyllabusService(conn).status(profile.exam_id),
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
        )
        return {"model_config": config, "providers": svc.providers()}

@app.post("/api/config/providers/custom")
def add_custom_provider(request: AddCustomProviderRequest) -> dict:
    init_db()
    with transaction() as conn:
        svc = ModelConfigService(conn)
        svc.add_custom_provider(request.name, request.base_url, request.default_model)
        return {"status": "ok"}


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
    settings = load_settings()
    with transaction() as conn:
        session_service = SessionService(conn)
        selected_option = (request.selected_option or "").strip().upper()
        extra_prompt = (request.extra_prompt or "").strip()
        visible_content = request.content.strip()
        if selected_option:
            visible_content = selected_option
            if extra_prompt:
                visible_content = f"{selected_option}\n补充提问：{extra_prompt}"
        session_id = session_service.ensure_session(request.session_id, visible_content or "日常学习")
        question_service = QuestionService(conn)
        selected_question = (
            question_service.question_by_id(request.question_id, session_id)
            if request.question_id
            else None
        )
        active = selected_question or question_service.active_question(session_id)
        task = TaskRouter().route(
            visible_content or request.content,
            has_active_question=active is not None,
            selected_text=request.selected_text,
            selected_option=selected_option,
        )
        session_service.add_message(session_id, "user", visible_content or request.content, {"task": task.value})

        model_config = ModelConfigService(conn).current_with_secret()
        provider = ModelProvider(
            model_config.get("provider_id") or settings.default_provider,
            model_config.get("model") or settings.default_model,
            model_config.get("base_url") or "",
            model_config.get("api_key") or "",
        )

        active_question = active  # 默认保持当前题

        if task.value == "answer_question" and active:
            # ── 答题 ──
            answer_content = selected_option or request.content
            result = EvaluatorTutorAgent(conn, provider).evaluate(
                session_id,
                active,
                answer_content,
                extra_prompt=extra_prompt,
            )
            assistant_content = result.feedback
            active_question = QuestionService(conn).active_question(session_id)

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
            model_result = provider.complete(pack)
            assistant_content = model_result.content

        elif task.value == "settings":
            # ── 设置：引导用户去设置面板 ──
            assistant_content = (
                "请点击左侧栏底部的「设置」按钮来修改模型供应商、学习目标、"
                "人格等配置。设置修改后会自动持久化到后端。"
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

        else:
            # ── 默认：日常训练 + 出题 ──
            OrchestratorAgent(conn, provider).handle_daily_drill(session_id, request.content)
            question = QuestionAuthorAgent(conn, provider).ensure_first_question(session_id)
            assistant_content = "已初始化今日学习面板，并准备好第一题。"
            active_question = question.model_dump()
            active_question["status"] = "ready"

        msg_id = session_service.add_message(
            session_id,
            "assistant",
            assistant_content,
            {"active_question": active_question},
        )
        return ChatResponse(
            session_id=session_id,
            message={"id": msg_id, "role": "assistant", "content": assistant_content},
            daily_panel=session_service.daily_panel(session_id),
            active_question=active_question,
            token_usage=token_totals(conn),
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
        response = f"已基于选中文本创建分支。当前分支默认不写回主会话：{request.selected_text[:60]}"
        conn.execute(
            """
            INSERT INTO branch_messages (id, branch_id, role, content)
            VALUES (?, ?, 'assistant', ?)
            """,
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
        session_service = SessionService(conn)
        session_id = session_service.ensure_session(None, "新聊天", force_new=True)
        return {
            "session_id": session_id,
            "sessions": session_service.list_sessions_by_date(),
            "daily_panel": session_service.daily_panel(session_id),
        }


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    """加载历史会话的完整消息、daily panel 和当前题目。"""
    init_db()
    with transaction() as conn:
        detail = SessionService(conn).load_session_detail(session_id)
        if not detail:
            return {"error": "session_not_found"}
        detail["token_usage"] = token_totals(conn)
        return detail


@app.post("/api/profile")
def update_profile(request: ProfileUpdateRequest) -> dict:
    """持久化用户设置：学习目标、学习背景、人格、全局提示词等。"""
    init_db()
    with transaction() as conn:
        profile_service = ProfileService(conn)
        current = profile_service.get()
        updates = request.model_dump(exclude_none=True)
        if not updates:
            return {"profile": current.model_dump()}
        updated = current.model_copy(update=updates)
        profile_service.update(updated)
        return {
            "profile": updated.model_dump(),
            "sessions": SessionService(conn).list_sessions_by_date(),
            "syllabus_status": SyllabusService(conn).status(updated.exam_id),
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
    if not request.import_to_session or not request.session_id:
        return parsed
    init_db()
    with transaction() as conn:
        profile = ProfileService(conn).get()
        imported_count = service.import_words(
            conn,
            session_id=request.session_id,
            parsed=parsed,
            exam_id=profile.exam_id,
            source_image_path=request.source_image_path,
        )
        msg_id = SessionService(conn).add_message(
            request.session_id,
            "user",
            f"截图导入文本：\n{parsed['raw_text']}",
            {
                "source": "screenshot_import",
                "parsed": parsed,
                "imported_count": imported_count,
                "source_image_path": request.source_image_path,
            },
        )
        return {
            **parsed,
            "imported": True,
            "imported_count": imported_count,
            "message_id": msg_id,
            "daily_panel": SessionService(conn).daily_panel(request.session_id),
        }
