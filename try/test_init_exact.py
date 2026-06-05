from fastapi.testclient import TestClient
from langdrill_agent.api import app


def test_init(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(tmp_path / "agent.db"))
    client = TestClient(app)
    response = client.post("/api/initialize", json={
        'provider_id': 'mock',
        'base_url': '',
        'api_key': '',
        'model': 'mock-tutor-v1',
        'display_name': '大哥',
        'target_language': '日语',
        'exam_id': 'cjt4',
        'exam_name': '大学日语四级',
        'learning_goal': '通过考试',
        'learning_background': '高中日语',
        'search_years': 3
    })
    assert response.status_code == 200
    assert response.json()["profile"]["display_name"] == "大哥"
