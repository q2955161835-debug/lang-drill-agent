from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.agents import OrchestratorAgent
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
    assert answered["answered_question"]["id"] == first_question["id"]
    assert answered["answered_question"]["status"] == "answered"

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


def test_natural_drill_request_generates_question_set(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "natural_drill.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    _use_mock_provider(db_path)

    client = TestClient(app)
    response = client.post("/api/chat", json={"content": "再来点题", "force_new_session": True})

    assert response.status_code == 200
    payload = response.json()
    assert "先生成并入库" in payload["message"]["content"]
    assert payload["active_question"]["sequence"] == 1
    assert payload["daily_panel"]["questions_total"] >= 4

    with transaction(db_path) as conn:
        question_count = conn.execute(
            "SELECT COUNT(*) AS total FROM questions WHERE session_id=?",
            (payload["session_id"],),
        ).fetchone()["total"]

    assert question_count >= 4


def test_vague_extra_drill_request_does_not_generate_questions(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "extra_drill_setup.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    _use_mock_provider(db_path)

    client = TestClient(app)
    response = client.post("/api/chat", json={"content": "再来几题", "force_new_session": True})

    assert response.status_code == 200
    payload = response.json()
    assert "先定一下方向和数量" in payload["message"]["content"]
    assert payload["active_question"] is None
    assert payload["daily_panel"]["questions_total"] == 0

    with transaction(db_path) as conn:
        question_count = conn.execute("SELECT COUNT(*) AS total FROM questions").fetchone()["total"]

    assert question_count == 0


def test_numbered_extra_drill_continues_when_planning_times_out(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "extra_drill_timeout.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    _use_mock_provider(db_path)

    def raise_timeout(self, session_id: str, content: str) -> dict:
        raise RuntimeError("The read operation timed out.")

    monkeypatch.setattr(OrchestratorAgent, "handle_daily_drill", raise_timeout)

    client = TestClient(app)
    response = client.post("/api/chat", json={"content": "再来2题吧", "force_new_session": True})

    assert response.status_code == 200
    payload = response.json()
    assert "先生成并入库 2 道题" in payload["message"]["content"]
    assert payload["active_question"]["sequence"] == 1
    assert payload["daily_panel"]["questions_total"] == 2

    with transaction(db_path) as conn:
        question_count = conn.execute(
            "SELECT COUNT(*) AS total FROM questions WHERE session_id=?",
            (payload["session_id"],),
        ).fetchone()["total"]

    assert question_count == 2


def test_chinese_colon_preface_is_not_used_as_english_option(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "colon_preface.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    init_db(db_path)
    _use_mock_provider(db_path)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={
            "content": "\n".join(
                [
                    "真实联调：请根据以下 CET-4 词汇生成一组选择题",
                    "laser: n. 激光",
                    "robe: n. 长袍",
                    "loyalty: n. 忠诚",
                    "context: n. 语境",
                ]
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    options = payload["active_question"]["options"]
    assert "真实联调" not in options
    assert all(not any("\u4e00" <= char <= "\u9fff" for char in option) for option in options)
    with transaction(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM knowledge_items WHERE term='真实联调' AND exam_id='cet4'"
        ).fetchone()

    assert row is None


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
