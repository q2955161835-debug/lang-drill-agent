from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn
from .config import load_settings
from .db import init_db, transaction
from .services import ProfileService, SessionService, SourceService

app = typer.Typer(help="Lang Drill Agent CLI（命令行接口）")


@app.command()
def init(
    display_name: str = typer.Option("boss", help="用户称呼"),
    target_language: str = typer.Option("未设置", help="目标语言"),
    exam_id: str = typer.Option("unassigned", help="考试 ID（标识符）"),
    exam_name: str = typer.Option("未设置", help="考试名称"),
) -> None:
    """初始化数据库、用户档案和常见考纲来源。"""
    db_path = init_db()
    with transaction(db_path) as conn:
        profile = ProfileService(conn).get()
        ProfileService(conn).update(
            profile.model_copy(
                update={
                    "display_name": display_name,
                    "target_language": target_language,
                    "exam_id": exam_id,
                    "exam_name": exam_name,
                }
            )
        )
        SourceService(conn).seed_common_sources()
    typer.echo(f"已初始化：{db_path}")


@app.command()
def status() -> None:
    """查看学习状态概览。"""
    db_path = init_db()
    with transaction(db_path) as conn:
        profile = ProfileService(conn).get()
        sessions = SessionService(conn).list_sessions_by_date()
        typer.echo(json.dumps({"profile": profile.model_dump(), "sessions": sessions}, ensure_ascii=False, indent=2))


@app.command()
def import_skill(
    source: Path = typer.Option(None, help="源 skill 目录"),
) -> None:
    """登记源 skill 目录，V1 以索引方式接入，不复制私人学习数据。"""
    settings = load_settings()
    target = source or settings.skill_source
    if not target.exists():
        raise typer.BadParameter(f"目录不存在：{target}")
    init_db()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO audit_events (id, level, event_type, message, payload_json)
            VALUES ('audit_skill_source', 'info', 'skill_source', ?, ?)
            ON CONFLICT(id) DO UPDATE SET message=excluded.message, payload_json=excluded.payload_json
            """,
            (
                f"已登记源 skill：{target}",
                json.dumps({"source": str(target)}, ensure_ascii=False),
            ),
        )
    typer.echo(f"已登记源 skill：{target}")


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """启动 Web API（网页后端接口）。"""
    init_db()
    uvicorn.run("langdrill_agent.api:app", host=host, port=port, reload=reload)


@app.command()
def chat(message: str, session_id: str | None = None) -> None:
    """命令行发送一条学习消息。"""
    from .api import chat as api_chat
    from .models import ChatRequest

    result = api_chat(ChatRequest(content=message, session_id=session_id))
    typer.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
