from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.agents import QuestionAuthorAgent
from langdrill_agent.db import init_db, transaction
from langdrill_agent.models import UserProfile
from langdrill_agent.paper_assets import parse_paper_text
from langdrill_agent.providers import ModelResult
from langdrill_agent.services import PastPaperService, ProfileService, QuestionService, SessionService
from langdrill_agent.utils import dumps


def _api_app():
    return __import__("langdrill_agent.api", fromlist=["app"]).app


class CapturingProvider:
    provider_id = "capture"
    model = "capture-model"

    def __init__(self) -> None:
        self.last_pack = None

    def complete(self, pack):
        self.last_pack = pack
        paper = pack.context_pack["past_paper_context"]["selected_papers"][0]
        payload = {
            "opening_message": "已按真题风格生成题组。",
            "questions": [
                {
                    "type": "cloze",
                    "prompt": "Choose the best word to complete the sentence.\n\nThe research team used a careful ______ to compare the two results.",
                    "options": ["method", "habit", "ticket", "weather"],
                    "answer": {"letter": "A", "correct": "method"},
                    "explanation": "Method fits the academic context.",
                    "knowledge_tags": ["vocabulary:method"],
                    "difficulty": 0.4,
                    "source_refs": [
                        {
                            "type": "past_paper_style",
                            "id": paper["id"],
                            "year": paper["year"],
                            "title": paper["title"],
                            "source_url": paper["source_url"],
                            "boundary": "style_reference_only",
                        }
                    ],
                },
                {
                    "type": "multiple_choice",
                    "prompt": "Which sentence best matches the passage evidence?",
                    "options": ["It lists prices.", "It compares methods.", "It names a city.", "It gives a date."],
                    "answer": {"letter": "B", "correct": "It compares methods."},
                    "explanation": "The sentence asks about evidence and comparison.",
                    "knowledge_tags": ["reading:evidence"],
                    "difficulty": 0.45,
                    "source_refs": [
                        {
                            "type": "past_paper_style",
                            "id": paper["id"],
                            "year": paper["year"],
                            "title": paper["title"],
                            "source_url": paper["source_url"],
                            "boundary": "style_reference_only",
                        }
                    ],
                },
                {
                    "type": "cloze",
                    "prompt": "Choose the best word to complete the sentence.\n\nThe article gives clear ______ for its conclusion.",
                    "options": ["season", "window", "evidence", "ticket"],
                    "answer": {"letter": "C", "correct": "evidence"},
                    "explanation": "Evidence supports a conclusion.",
                    "knowledge_tags": ["reading:evidence"],
                    "difficulty": 0.42,
                    "source_refs": [
                        {
                            "type": "past_paper_style",
                            "id": paper["id"],
                            "year": paper["year"],
                            "title": paper["title"],
                            "source_url": paper["source_url"],
                            "boundary": "style_reference_only",
                        }
                    ],
                },
                {
                    "type": "multiple_choice",
                    "prompt": "Which option best identifies the writer's purpose in the passage?",
                    "options": ["To advertise a product.", "To invite a guest.", "To list addresses.", "To explain a process."],
                    "answer": {"letter": "D", "correct": "To explain a process."},
                    "explanation": "The passage presents steps in a process.",
                    "knowledge_tags": ["reading:purpose"],
                    "difficulty": 0.48,
                    "source_refs": [
                        {
                            "type": "past_paper_style",
                            "id": paper["id"],
                            "year": paper["year"],
                            "title": paper["title"],
                            "source_url": paper["source_url"],
                            "boundary": "style_reference_only",
                        }
                    ],
                },
            ],
        }
        content = dumps(payload)
        return ModelResult(content=content, input_tokens=10, output_tokens=10, latency_ms=1, model=self.model)


def test_past_papers_default_selects_recent_three_and_creates_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(tmp_path / "paper-assets"))
    db_path = tmp_path / "papers.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        status = PastPaperService(conn).status("cet4")

    assert status["selected_paper_ids"] == ["paper_cet4_2025", "paper_cet4_2024", "paper_cet4_2023"]
    assert status["source_website"] == "https://www.guojiya.cn/#exams"
    assert [paper["year"] for paper in status["current_papers"]] == [2025, 2024, 2023]
    assert all(paper["source_url"] == "https://www.guojiya.cn/#exams" for paper in status["current_papers"])
    assert {item["id"] for item in status["question_types"]} >= {"listening", "reading", "translation", "writing"}
    listening = next(item for item in status["question_types"] if item["id"] == "listening")
    assert listening["disabled"] is True
    assert listening["locked"] is True
    assert "语音模型" in listening["disabled_reason"]
    assert "listening" not in status["enabled_question_type_ids"]
    first = status["current_papers"][0]["metadata"]
    assert Path(first["raw_path"]).exists()
    assert Path(first["parsed_path"]).exists()
    assert first["parse_status"] == "source_manifest_only"


def test_listening_question_type_is_reserved_for_all_builtin_exams(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(tmp_path / "paper-assets"))
    db_path = tmp_path / "reserved-listening.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        service = PastPaperService(conn)
        for exam_id in ["cet4", "cet6", "cft4", "cjt4", "cjt6", "ielts", "toefl", "gaokao-english"]:
            status = service.status(exam_id)
            listening = next(item for item in status["question_types"] if item["id"] == "listening")

            assert listening["available"] is False
            assert listening["disabled"] is True
            assert listening["locked"] is True
            assert "listening" not in status["enabled_question_type_ids"]

            first_available = next(item["id"] for item in status["question_types"] if not item["disabled"])
            updated = service.save_question_types(exam_id, ["listening", first_available])

            assert "listening" not in updated["enabled_question_type_ids"]
            assert updated["enabled_question_type_ids"] == [first_available]


def test_manual_import_adds_paper_and_question_type(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(tmp_path / "paper-assets"))
    db_path = tmp_path / "manual-paper.db"
    init_db(db_path)

    with transaction(db_path) as conn:
        service = PastPaperService(conn)
        status = service.manual_import(
            exam_id="custom",
            title="自定义考试 2025 样卷",
            year=2025,
            source_url="https://example.test/paper",
            local_path="D:/papers/custom-2025.pdf",
            summary="包含口译和情景写作。",
            question_types=["口译", "情景写作"],
            raw_text=(
                "# 自定义考试 2025 样卷\n\n"
                "## 口译\n"
                "1. Translate this short announcement into Chinese.\n\n"
                "## 情景写作\n"
                "2. Write an email to explain the schedule change."
            ),
        )
        type_ids = {item["id"] for item in status["question_types"]}
        service.save_question_types("custom", ["口译", "情景写作"])
        updated = service.status("custom")

    imported_paper = next(
        paper for paper in status["current_papers"] if paper["title"] == "自定义考试 2025 样卷"
    )
    assert imported_paper["title"] == "自定义考试 2025 样卷"
    assert {"口译", "情景写作"} <= type_ids
    assert updated["enabled_question_type_ids"] == ["口译", "情景写作"]
    metadata = imported_paper["metadata"]
    assert Path(metadata["raw_path"]).exists()
    assert Path(metadata["parsed_path"]).exists()
    assert metadata["parse_status"] == "parsed"
    assert metadata["parsed"]["stats"]["sections"] >= 2
    assert metadata["parsed"]["usable_excerpts"]


def test_extract_text_endpoint_reads_uploaded_text_file() -> None:
    client = TestClient(_api_app())
    response = client.post(
        "/api/files/extract-text",
        params={"filename": "words.txt"},
        content="collision: 碰撞；冲突\nemerge: 出现".encode("utf-8"),
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "words.txt"
    assert payload["parser"] == "text"
    assert "collision" in payload["text"]


def test_extract_text_endpoint_rejects_empty_upload() -> None:
    client = TestClient(_api_app())
    response = client.post(
        "/api/files/extract-text",
        params={"filename": "empty.txt"},
        content=b"",
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "上传文件为空。"


def test_extract_text_endpoint_reports_parser_error_without_500(monkeypatch) -> None:
    import langdrill_agent.api as api_module

    def fail_extract(path: Path, *, language: str = "ch", mineru_token: str = "") -> tuple[str, str]:
        raise RuntimeError("MinerU 解析失败：download markdown EOF")

    monkeypatch.setattr(api_module, "extract_text_from_file", fail_extract)

    client = TestClient(_api_app())
    response = client.post(
        "/api/files/extract-text",
        params={"filename": "words.png"},
        content=b"not-a-real-image",
        headers={"content-type": "image/png"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "MinerU 解析失败：download markdown EOF"


def test_mineru_flash_retries_transient_download_errors(tmp_path: Path, monkeypatch) -> None:
    import langdrill_agent.paper_assets as paper_assets

    class MineruResult:
        def __init__(self, returncode: int, stderr: str = "", stdout: str = "") -> None:
            self.returncode = returncode
            self.stderr = stderr
            self.stdout = stdout

    calls = {"count": 0}

    def fake_run(*args, **kwargs) -> MineruResult:
        calls["count"] += 1
        if calls["count"] == 1:
            return MineruResult(1, stderr='Error: download markdown: Get "full.md": EOF')
        return MineruResult(0, stdout="collision: 碰撞；冲突")

    monkeypatch.setattr(paper_assets.shutil, "which", lambda name: "mineru-open-api")
    monkeypatch.setattr(paper_assets.subprocess, "run", fake_run)
    monkeypatch.setattr(paper_assets.time, "sleep", lambda seconds: None)
    image_path = tmp_path / "words.png"
    image_path.write_bytes(b"fake-image")

    text, parser = paper_assets._extract_with_mineru(image_path, language="ch")

    assert calls["count"] == 2
    assert parser == "mineru-open-api flash-extract"
    assert "collision" in text


def test_image_text_extract_falls_back_to_rapidocr(tmp_path: Path, monkeypatch) -> None:
    import langdrill_agent.paper_assets as paper_assets

    def fail_mineru(path: Path, *, language: str, mineru_token: str = "") -> tuple[str, str]:
        raise RuntimeError("MinerU 解析失败：download markdown EOF")

    monkeypatch.setattr(paper_assets, "_extract_with_mineru", fail_mineru)
    monkeypatch.setattr(
        paper_assets,
        "_extract_with_rapidocr_image",
        lambda path: ("collision: 碰撞；冲突", "rapidocr-onnxruntime"),
    )
    image_path = tmp_path / "words.png"
    image_path.write_bytes(b"fake-image")

    text, parser = paper_assets.extract_text_from_file(image_path)

    assert parser == "rapidocr-onnxruntime"
    assert "collision" in text


def test_mineru_extract_uses_token_mode_when_configured(tmp_path: Path, monkeypatch) -> None:
    import langdrill_agent.paper_assets as paper_assets

    class MineruResult:
        returncode = 0
        stderr = ""
        stdout = "parsed by token"

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs) -> MineruResult:
        captured["command"] = command
        captured["env"] = kwargs.get("env")
        return MineruResult()

    monkeypatch.setattr(paper_assets.shutil, "which", lambda name: "mineru-open-api")
    monkeypatch.setattr(paper_assets.subprocess, "run", fake_run)
    file_path = tmp_path / "paper.pdf"
    file_path.write_bytes(b"%PDF")

    text, parser = paper_assets._extract_with_mineru(file_path, language="ch", mineru_token="token-123")

    assert text == "parsed by token"
    assert parser == "mineru-open-api extract"
    assert captured["command"][1] == "extract"
    assert captured["env"]["MINERU_TOKEN"] == "token-123"


def test_past_paper_file_upload_imports_and_parses_text_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(tmp_path / "paper-assets"))
    db_path = tmp_path / "uploaded-paper.db"
    monkeypatch.setenv("LANGDRILL_DB_PATH", str(db_path))
    init_db(db_path)

    client = TestClient(_api_app())
    response = client.post(
        "/api/past-papers/import-file",
        params={
            "exam_id": "custom",
            "title": "拖拽导入样卷",
            "filename": "drag-paper.md",
            "year": "2026",
            "question_types": "reading,writing",
        },
        content=(
            "# 拖拽导入样卷\n\n"
            "Part I Writing\n"
            "1. Write an essay about learning tools.\n\n"
            "Part II Reading\n"
            "2. Which statement best summarizes the passage?"
        ).encode("utf-8"),
        headers={"content-type": "text/markdown"},
    )

    assert response.status_code == 200
    status = response.json()
    imported = next(paper for paper in status["current_papers"] if paper["title"] == "拖拽导入样卷")
    metadata = imported["metadata"]
    assert Path(metadata["raw_path"]).exists()
    assert Path(metadata["parsed_path"]).exists()
    assert metadata["parser"] == "text"
    assert {"reading", "writing"} <= set(metadata["question_types"])


def test_parse_paper_text_extracts_needed_parts() -> None:
    parsed = parse_paper_text(
        """
# CET-4 2025 Sample

Part I Writing
1. Write an essay about online learning.

Part II Reading Comprehension
2. Which statement best summarizes the passage?
3. Choose the best word to fill in the blank: The plan is ______.
""",
        exam_id="cet4",
        title="CET-4 2025 Sample",
        year=2025,
        source_url="https://example.test",
        raw_path="papers/cet4/raw/sample.md",
        parser="test",
    )

    assert {"writing", "reading", "cloze"} <= set(parsed["question_types"])
    assert parsed["stats"]["sections"] == 3
    assert parsed["sections"][1]["heading"] == "Part I Writing"
    assert parsed["usable_excerpts"][0]["text"].startswith("1. Write")


def test_question_author_receives_selected_papers_and_question_types(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LANGDRILL_PAPER_ROOT", str(tmp_path / "paper-assets"))
    db_path = tmp_path / "author-paper.db"
    init_db(db_path)

    provider = CapturingProvider()
    with transaction(db_path) as conn:
        ProfileService(conn).update(UserProfile(exam_id="cet4", exam_name="大学英语四级"))
        paper_service = PastPaperService(conn)
        paper_service.select_papers("cet4", ["paper_cet4_2024"])
        paper_service.save_question_types("cet4", ["reading"])
        session_id = SessionService(conn).ensure_session(None, "真题参考测试", force_new=True)

        QuestionAuthorAgent(conn, provider).ensure_question_set(session_id, "method: 方法", target_count=2)
        active = QuestionService(conn).active_question(session_id)
        context = provider.last_pack.context_pack["past_paper_context"]

    assert context["selected_papers"][0]["id"] == "paper_cet4_2024"
    assert context["selected_papers"][0]["sections"]
    assert [item["id"] for item in context["enabled_question_types"]] == ["reading"]
    assert active is not None
    assert active["source_refs"][0]["id"] == "paper_cet4_2024"
