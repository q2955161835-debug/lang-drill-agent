from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agents import EvaluatorTutorAgent, OrchestratorAgent, QuestionAuthorAgent, token_totals
from .config import load_settings
from .db import init_db, transaction
from .models import BranchRequest, ChatRequest, ChatResponse, InitRequest, ModelConfigRequest
from .providers import ModelProvider
from .services import ModelConfigService, ProfileService, QuestionService, SessionService, SourceService
from .task_router import TaskRouter
from .utils import new_id


app = FastAPI(title="Lang Drill Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
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
        config = ModelConfigService(conn).save(
            request.provider_id,
            request.base_url,
            request.model,
            request.api_key,
        )
        return {"model_config": config}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    init_db()
    settings = load_settings()
    with transaction() as conn:
        session_service = SessionService(conn)
        session_id = session_service.ensure_session(request.session_id, request.content)
        active = QuestionService(conn).active_question(session_id)
        task = TaskRouter().route(
            request.content,
            has_active_question=active is not None,
            selected_text=request.selected_text,
        )
        session_service.add_message(session_id, "user", request.content, {"task": task.value})

        model_config = ModelConfigService(conn).current_with_secret()
        provider = ModelProvider(
            model_config.get("provider_id") or settings.default_provider,
            model_config.get("model") or settings.default_model,
            model_config.get("base_url") or "",
            model_config.get("api_key") or "",
        )
        if task.value == "answer_question" and active:
            result = EvaluatorTutorAgent(conn, provider).evaluate(session_id, active, request.content)
            assistant_content = result.feedback
            active_question = QuestionService(conn).active_question(session_id)
        else:
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
