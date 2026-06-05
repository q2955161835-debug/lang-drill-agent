from fastapi.testclient import TestClient
from langdrill_agent.api import app


def test_chat(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(tmp_path / "agent.db"))
    monkeypatch.setenv("LANGDRILL_DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("LANGDRILL_DEFAULT_MODEL", "mock-tutor-v1")
    monkeypatch.delenv("LANGDRILL_PROVIDER_API_KEY", raising=False)
    client = TestClient(app)
    response = client.post("/api/chat", json={
        "content": "今天学习まで、から和に的区别",
        "session_id": None
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["message"]["role"] == "assistant"
    assert payload["active_question"]["prompt"]
