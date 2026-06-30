from __future__ import annotations

import os

import httpx
import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("LANGDRILL_RUN_LIVE") != "1",
    reason="live backend probe is opt-in; set LANGDRILL_RUN_LIVE=1",
)


def test_live_initialize_endpoint() -> None:
    response = httpx.post(
        "http://127.0.0.1:8000/api/initialize",
        json={
            "provider_id": "mimo",
            "base_url": "https://api.xiaomimimo.com/anthropic",
            "api_key": "",
            "model": "mimo-v2.5",
            "display_name": "大哥",
            "target_language": "日语",
            "exam_id": "cjt4",
            "exam_name": "大学日语四级",
            "learning_goal": "通过考试",
            "learning_background": "高中日语",
            "search_years": 3,
        },
        timeout=5,
    )

    assert response.status_code == 200
