from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import typer
import uvicorn
from .config import load_settings
from .db import init_db, transaction
from .logging_config import configure_logging
from .services import ProfileService, SessionService, SourceService

app = typer.Typer(help="Lang Drill Agent CLI（命令行接口）")


@app.command()
def init(
    display_name: str = typer.Option("boss", help="用户称呼"),
    target_language: str = typer.Option("英语", help="目标语言"),
    exam_id: str = typer.Option("cet4", help="考试 ID（标识符）"),
    exam_name: str = typer.Option("大学英语四级", help="考试名称"),
) -> None:
    """初始化数据库、用户档案和常见考纲来源。"""
    configure_logging()
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
    configure_logging()
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
    configure_logging()
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
    configure_logging()
    init_db()
    uvicorn.run("langdrill_agent.api:app", host=host, port=port, reload=reload)


@app.command()
def chat(message: str, session_id: str | None = None) -> None:
    """命令行发送一条学习消息。"""
    configure_logging()
    from .api import chat as api_chat
    from .models import ChatRequest

    result = api_chat(ChatRequest(content=message, session_id=session_id))
    typer.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


@app.command("data-paths")
def data_paths() -> None:
    """查看用户状态目录、数据库和日志位置。"""
    settings = load_settings()
    typer.echo(
        json.dumps(
            {
                "user_data_dir": str(settings.user_data_dir),
                "db_path": str(settings.db_path),
                "log_dir": str(settings.log_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("backup-user-data")
def backup_user_data(
    target_root: Path = typer.Option(Path("data_backups"), help="备份输出目录"),
) -> None:
    """把当前用户点目录数据备份到项目内目录，便于清空重测前保留现场。"""
    settings = load_settings()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = target_root / f"langdrill-user-data-{stamp}"
    if settings.user_data_dir.exists():
        shutil.copytree(settings.user_data_dir, target)
        typer.echo(f"已备份用户数据：{target}")
        return
    typer.echo(f"用户数据目录不存在，无需备份：{settings.user_data_dir}")


if __name__ == "__main__":
    app()
