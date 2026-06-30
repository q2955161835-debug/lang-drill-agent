from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import init_db, transaction
from langdrill_agent.utils import dumps


def _use_mock_provider(db_path: Path) -> None:
    with transaction(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
            VALUES ('model.default', ?, CURRENT_TIMESTAMP)
            """,
            (
                dumps(
                    {
                        "provider_id": "mock",
                        "base_url": "",
                        "model": "mock-tutor-v1",
                        "has_api_key": False,
                    }
                ),
            ),
        )


def test_chat_generates_formal_question_set_and_auto_advances(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "formal_drill.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    _use_mock_provider(db_path)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={
            "content": "blood: n. 血液；血统\ncontext: n. 语境\nevidence: n. 证据\ninfer: v. 推断",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "已初始化今日学习面板，并准备好第一题" not in payload["message"]["content"]
    assert "先生成并入库" in payload["message"]["content"]
    assert payload["daily_panel"]["questions_total"] >= 4
    assert payload["active_question"]["sequence"] == 1

    session_id = payload["session_id"]
    first_question = payload["active_question"]
    answer = first_question["answer"].get("letter") or first_question["answer"].get("correct")
    answer_response = client.post(
        "/api/chat",
        json={
            "content": "",
            "session_id": session_id,
            "selected_option": answer,
            "question_id": first_question["id"],
        },
    )

    assert answer_response.status_code == 200
    answered = answer_response.json()
    assert "判断：" in answered["message"]["content"]
    assert "下一题已就绪" in answered["message"]["content"]
    assert answered["active_question"]["sequence"] == 2

    with transaction(db_path) as conn:
        question_rows = conn.execute(
            "SELECT sequence, status FROM questions WHERE session_id=? ORDER BY sequence ASC",
            (session_id,),
        ).fetchall()
        attempts = conn.execute("SELECT COUNT(*) AS count FROM attempts WHERE session_id=?", (session_id,)).fetchone()

    assert len(question_rows) >= 4
    assert question_rows[0]["status"] == "answered"
    assert question_rows[1]["status"] == "ready"
    assert attempts["count"] == 1

    continue_response = client.post(
        "/api/chat",
        json={"content": "下一题", "session_id": session_id},
    )

    assert continue_response.status_code == 200
    continued = continue_response.json()
    assert "不重新开始" in continued["message"]["content"]
    assert "已初始化今日学习面板" not in continued["message"]["content"]
    assert continued["active_question"]["id"] == answered["active_question"]["id"]


def test_start_bat_uses_hidden_background_processes() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "start.bat").read_text(encoding="utf-8")
    launcher = (root / "scripts" / "dev" / "start-dev.ps1").read_text(encoding="utf-8")

    assert "cmd /k" not in script
    assert "scripts\\dev\\start-dev.ps1" in script
    assert "WindowStyle Hidden" in launcher
    assert "langdrill-backend.out.log" in launcher
    assert "langdrill-frontend.out.log" in launcher
    assert "Wait-LangDrillHttp" in launcher
