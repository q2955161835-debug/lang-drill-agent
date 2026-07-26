"""批次 B 回归测试：模型/子进程失败不得绕过兜底，也不得丢失作答记录。

对应改动：
- `providers.py`：httpx 超时、连接错误和响应解析错误统一归一化成
  `ModelProviderError(RuntimeError)`；原先 `httpx.post` 在 try 之外，只有
  `HTTPStatusError` 被转成 RuntimeError，因此超时会绕过全部 12 处
  `except RuntimeError` 兜底。
- `agents.py`：`EvaluatorTutorAgent.evaluate` 的 attempts / mark_answered /
  mastery_events / 掌握度更新移到模型调用之前（AGENTS.md:37 不得丢失作答记录）。
- `paper_assets.py`：`subprocess.TimeoutExpired` 归一化成 RuntimeError，否则
  MinerU 超时会跳过 RapidOCR 本地 OCR 兜底（AGENTS.md:69）。
- `api.py` / `routers/*.py`：阻塞的上传解析与导入移出事件循环。
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from langdrill_agent import paper_assets
from langdrill_agent.agents import EvaluatorTutorAgent
from langdrill_agent.db import connect, init_db
from langdrill_agent.models import PromptPack, Question
from langdrill_agent.providers import ModelProvider, ModelProviderError
from langdrill_agent.services import QuestionService, SessionService

ENDPOINT = "https://example.invalid/v1/chat/completions"


def _pack() -> PromptPack:
    return PromptPack(
        system_modules=[{"id": "core.safety", "content": "safety"}],
        context_pack={"task_type": "general_chat"},
        user_content="hello",
    )


def _provider() -> ModelProvider:
    return ModelProvider("openai", "gpt-test", base_url="https://example.invalid/v1", api_key="sk-test")


def _response(**kwargs) -> httpx.Response:
    return httpx.Response(request=httpx.Request("POST", ENDPOINT), **kwargs)


# --------------------------------------------------------------------------
# providers.py：归一化
# --------------------------------------------------------------------------

def test_raw_httpx_errors_are_not_runtime_errors() -> None:
    """记录这批 bug 的根因：httpx 的传输层异常都不继承 RuntimeError。"""
    assert not isinstance(httpx.ReadTimeout("x"), RuntimeError)
    assert not isinstance(httpx.ConnectError("x"), RuntimeError)
    assert not isinstance(subprocess.TimeoutExpired("cmd", 1), RuntimeError)


@pytest.mark.parametrize(
    "raised",
    [
        httpx.ReadTimeout("read timed out"),
        httpx.ConnectTimeout("connect timed out"),
        httpx.ConnectError("connection refused"),
        httpx.RemoteProtocolError("peer closed connection"),
    ],
)
def test_transport_errors_become_model_provider_error(
    monkeypatch: pytest.MonkeyPatch, raised: Exception
) -> None:
    def fake_post(*_args, **_kwargs):
        raise raised

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ModelProviderError) as info:
        _provider().complete(_pack())

    # 关键：兜底处理器全部写作 `except RuntimeError`，所以必须是 RuntimeError 子类。
    assert isinstance(info.value, RuntimeError)


def test_html_error_page_with_http_200_becomes_model_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """代理常在 HTTP 200 下返回 HTML 错误页，原先 response.json() 会抛 ValueError。"""
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: _response(status_code=200, text="<html><body>502 Bad Gateway</body></html>"),
    )

    with pytest.raises(ModelProviderError, match="不是合法 JSON"):
        _provider().complete(_pack())


def test_unexpected_json_shape_becomes_model_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """原先 data["choices"][0]["message"]["content"] 会抛 KeyError/IndexError。"""
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: _response(status_code=200, json={"error": {"message": "quota exceeded"}}),
    )

    with pytest.raises(ModelProviderError, match="响应结构"):
        _provider().complete(_pack())


def test_null_content_becomes_model_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: _response(
            status_code=200, json={"choices": [{"message": {"content": None}}]}
        ),
    )

    with pytest.raises(ModelProviderError, match="未返回文本内容"):
        _provider().complete(_pack())


def test_401_message_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """既有行为不变：401 仍给出可读的密钥提示。"""
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _response(status_code=401, text="unauthorized")
    )

    with pytest.raises(ModelProviderError, match="401"):
        _provider().complete(_pack())


# --------------------------------------------------------------------------
# agents.py：作答记录不得丢失
# --------------------------------------------------------------------------

class FailingProvider:
    provider_id = "failing"
    model = "failing-model"

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def complete(self, pack):  # noqa: ARG002
        raise self.exc


def _seed_question(conn) -> tuple[str, dict]:
    session_id = SessionService(conn).ensure_session(None, "作答记录回归")
    question = Question(
        id="q-resilience",
        session_id=session_id,
        sequence=1,
        type="multiple_choice",
        prompt="Choose the correct option.",
        options=["A", "B"],
        answer={"correct": "A", "letter": "A"},
        explanation="A is correct.",
        knowledge_tags=["vocabulary:skin"],
    )
    QuestionService(conn).save_questions([question])
    return session_id, question.model_dump()


def test_model_timeout_keeps_attempt_and_marks_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "evaluator-timeout.db"
    init_db(db_path)

    with connect(db_path) as conn:
        session_id, question = _seed_question(conn)
        provider = FailingProvider(ModelProviderError("模型 API 请求超时（60 秒未返回）。"))

        result = EvaluatorTutorAgent(conn, provider).evaluate(session_id, question, "A")

        assert result.feedback_source == "program_fallback"
        assert result.is_correct is True
        # AGENTS.md:37 —— 回退必须显式标注，不得静默伪装成正常讲解。
        assert "模型讲解未成功" in result.feedback

        attempts = conn.execute(
            "SELECT question_id, user_answer, is_correct FROM attempts WHERE session_id=?",
            (session_id,),
        ).fetchall()
        assert len(attempts) == 1
        assert attempts[0]["question_id"] == "q-resilience"
        assert attempts[0]["user_answer"] == "A"
        assert attempts[0]["is_correct"] == 1

        status = conn.execute(
            "SELECT status FROM questions WHERE id='q-resilience'"
        ).fetchone()["status"]
        assert status == "answered"

        assert conn.execute(
            "SELECT COUNT(*) FROM mastery_events WHERE question_id='q-resilience'"
        ).fetchone()[0] == 1

        # 兜底来源必须进入审计台账。
        statuses = [
            row["validation_status"]
            for row in conn.execute(
                "SELECT validation_status FROM model_calls WHERE task_type='answer_evaluation'"
            )
        ]
        assert "provider_error_fallback" in statuses


def test_attempt_survives_even_when_error_type_bypasses_fallback(tmp_path: Path) -> None:
    """核心不变式：无论异常类型是什么，作答记录都必须已经落库。

    这是这批 bug 造成的最严重后果——写入原先排在模型调用之后，一次未归一化的
    超时会同时丢掉 attempts、mark_answered、mastery_events 和掌握度更新，
    而用户消息因为 autocommit 已经持久化，聊天记录里就会出现“答了但没有作答记录”。
    """
    db_path = tmp_path / "evaluator-raw.db"
    init_db(db_path)

    with connect(db_path) as conn:
        session_id, question = _seed_question(conn)
        provider = FailingProvider(httpx.ReadTimeout("read timed out"))

        # 未归一化的异常不被 `except RuntimeError` 捕获，会向上抛出——这是期望行为，
        # 内部缺陷不应被伪装成“模型不可用”。但记录必须已经保住。
        with pytest.raises(httpx.ReadTimeout):
            EvaluatorTutorAgent(conn, provider).evaluate(session_id, question, "A")

        assert conn.execute(
            "SELECT COUNT(*) FROM attempts WHERE session_id=?", (session_id,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT status FROM questions WHERE id='q-resilience'"
        ).fetchone()["status"] == "answered"


def test_successful_model_feedback_is_written_back(tmp_path: Path) -> None:
    """成功路径的落库结果必须与调整写入顺序之前完全一致。"""
    from langdrill_agent.providers import ModelResult

    class OkProvider:
        provider_id = "ok"
        model = "ok-model"

        def complete(self, pack):  # noqa: ARG002
            return ModelResult(
                content="模型讲解正文",
                input_tokens=1,
                output_tokens=1,
                latency_ms=1,
                model="ok-model",
            )

    db_path = tmp_path / "evaluator-ok.db"
    init_db(db_path)

    with connect(db_path) as conn:
        session_id, question = _seed_question(conn)

        result = EvaluatorTutorAgent(conn, OkProvider()).evaluate(session_id, question, "A")

        assert result.feedback_source == "model"
        stored = conn.execute(
            "SELECT feedback FROM attempts WHERE session_id=?", (session_id,)
        ).fetchone()["feedback"]
        assert stored == result.feedback
        assert "模型讲解正文" in stored


# --------------------------------------------------------------------------
# paper_assets.py：MinerU 超时必须能回退本地 OCR
# --------------------------------------------------------------------------

def test_mineru_timeout_becomes_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paper_assets.shutil, "which", lambda _name: "/fake/mineru-open-api")
    monkeypatch.setattr(paper_assets.time, "sleep", lambda _s: None)

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="mineru-open-api", timeout=900)

    monkeypatch.setattr(paper_assets.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="超时"):
        paper_assets._extract_with_mineru(Path("paper.pdf"), language="ch")


def test_image_extraction_falls_back_to_rapidocr_on_mineru_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """原先 TimeoutExpired 会穿过 `except RuntimeError`，RapidOCR 兜底完全不执行。"""
    monkeypatch.setattr(paper_assets.shutil, "which", lambda _name: "/fake/mineru-open-api")
    monkeypatch.setattr(paper_assets.time, "sleep", lambda _s: None)

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="mineru-open-api", timeout=900)

    monkeypatch.setattr(paper_assets.subprocess, "run", fake_run)
    monkeypatch.setattr(
        paper_assets, "_extract_with_rapidocr_image", lambda _p: ("本地识别文本", "rapidocr")
    )

    text, parser = paper_assets._extract_image_text(
        Path("shot.png"), language="ch", mineru_token=""
    )

    assert text == "本地识别文本"
    assert parser == "rapidocr"


# --------------------------------------------------------------------------
# api.py：阻塞解析必须离开事件循环
# --------------------------------------------------------------------------

def test_file_extraction_runs_off_the_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """线程池里没有运行中的事件循环；若解析仍在 async 处理函数内联执行则会有。"""
    from langdrill_agent import api as api_module

    db_path = tmp_path / "offload.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    init_db(db_path)

    observed: dict[str, bool] = {}

    def fake_extract(_path, *, language, mineru_token):  # noqa: ARG001
        try:
            asyncio.get_running_loop()
            observed["on_event_loop"] = True
        except RuntimeError:
            observed["on_event_loop"] = False
        return "抽取文本", "fake-parser"

    monkeypatch.setattr(api_module, "extract_text_from_file", fake_extract)

    client = TestClient(api_module.app)
    response = client.post("/api/files/extract-text?filename=note.txt", content=b"hello")

    assert response.status_code == 200
    assert response.json()["text"] == "抽取文本"
    assert observed["on_event_loop"] is False
