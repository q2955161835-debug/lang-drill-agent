"""验证后端错误响应使用稳定代码和结构化参数信封。

错误信封格式：{ "code": string, "params": object, "detail": string | null }。
前端根据 code 选择本地化文案，detail 只用于日志和向后兼容。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from langdrill_agent.api import app
from langdrill_agent.db import init_db


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "test-error-codes.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(tmp_path))
    init_db(db_path)
    return TestClient(app)


def _error_payload(response) -> dict:
    """提取错误响应中的 detail 载荷。"""
    data = response.json()
    if isinstance(data.get("detail"), dict):
        return data["detail"]
    return data


class TestCreativeErrorCodes:
    """创造模式路由的错误响应必须使用稳定代码。"""

    def test_enable_creative_when_runtime_unavailable_returns_stable_code(
        self, client: TestClient
    ) -> None:
        """运行时未就绪时启用创造模式必须返回 CREATIVE_RUNTIME_UNAVAILABLE 稳定码。"""
        response = client.post(
            "/api/creative/settings",
            json={"enabled": True, "permission_profile": "request_approval"},
        )
        assert response.status_code == 409
        payload = _error_payload(response)
        assert payload["code"] == "CREATIVE_RUNTIME_UNAVAILABLE"
        assert "reason" in payload["params"]

    def test_resolve_nonexistent_approval_returns_stable_code(
        self, client: TestClient
    ) -> None:
        """解析不存在的审批必须返回 CREATIVE_APPROVAL_NOT_FOUND 稳定码。"""
        response = client.post(
            "/api/creative/approvals/nonexistent-approval-id/resolve",
            json={"action": "approve"},
        )
        assert response.status_code == 404
        payload = _error_payload(response)
        assert payload["code"] == "CREATIVE_APPROVAL_NOT_FOUND"
        assert payload["params"]["approval_id"] == "nonexistent-approval-id"


class TestErrorEnvelopeFormat:
    """错误信封必须包含 code、params 和可选 detail 字段。"""

    def test_creative_error_envelope_has_code_and_params(
        self, client: TestClient
    ) -> None:
        """创造模式错误响应必须包含 code 和 params 字段。"""
        response = client.post(
            "/api/creative/settings",
            json={"enabled": True},
        )
        if response.status_code >= 400:
            payload = _error_payload(response)
            assert isinstance(payload.get("code"), str)
            assert isinstance(payload.get("params"), dict)
