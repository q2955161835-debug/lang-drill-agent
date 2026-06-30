from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from langdrill_agent.agents import EvaluatorTutorAgent, QuestionAuthorAgent, token_totals
from langdrill_agent.api import app
from langdrill_agent.config import load_settings
from langdrill_agent.db import init_db, transaction
from langdrill_agent.logging_config import configure_logging
from langdrill_agent.models import UserProfile
from langdrill_agent.providers import ModelProvider
from langdrill_agent.services import (
    ModelConfigService,
    ProfileService,
    QuestionService,
    SessionService,
    SourceService,
    SyllabusService,
)


REAL_SCREENSHOT_PATH = (
    "D:/29551/QQ_Files/Tencent Files/2955161835/nt_qq/nt_data/Pic/2026-06/"
    "Ori/1f9a9f2e2274ac8f269ad438356fb1c5.png"
)

REAL_SCREENSHOT_TEXT = """
单词列表
cultivate
v. 培养，发展；耕作，种植，栽培
material
n. 材料，原料； adj. 物质的，客观存在的
research
n. 研究，调查； v. 研究，调查
course
n. 课程；过程；一道菜；进程； adv. 当然
blood
n. 血（液）；血统
executive
n. 经理；行政人员； adj. 执行的
adequate
adj. 足够的，充分的
process
n. 步骤，过程； v. 加工；处理
bow
vi. 鞠躬，弯腰
laser
n. 激光
robe
n. 长袍，礼服
loyalty
n. 忠诚，忠心
"""


def main() -> None:
    logging_paths = configure_logging(force=True)
    settings = load_settings()
    db_path = init_db()
    report: dict[str, object] = {
        "db_path": str(db_path),
        "user_data_dir": str(settings.user_data_dir),
        "log_file": str(logging_paths["log_file"]),
        "source_image_exists": Path(REAL_SCREENSHOT_PATH).exists(),
        "checks": {},
        "issues": [],
    }

    with transaction(db_path) as conn:
        ProfileService(conn).update(
            UserProfile(
                display_name="boss",
                target_language="英语",
                exam_id="cet4",
                exam_name="大学英语四级",
                learning_goal="CET-4 vocabulary and grammar practice",
                learning_background="手机背词截图导入后生成练习题。",
            )
        )
        SourceService(conn).seed_common_sources()
        syllabus_result = SyllabusService(conn).manual_check("cet4")
        model_config = ModelConfigService(conn).save(
            "mimo",
            "https://api.xiaomimimo.com/anthropic",
            "mimo-v2.5-pro",
            "",
        )
        session_id = SessionService(conn).ensure_session(None, "smoke screenshot import", force_new=True)
        report["session_id"] = session_id
        report["model_config"] = {
            "provider_id": model_config["provider_id"],
            "model": model_config["model"],
            "base_url": model_config["base_url"],
            "has_api_key": model_config["has_api_key"],
        }
        report["syllabus"] = {
            "changed": syllabus_result["changed"],
            "message": syllabus_result["message"],
            "year": syllabus_result["status"]["current_year"],
        }

    client = TestClient(app)
    import_response = client.post(
        "/api/screenshot/parse",
        json={
            "text": REAL_SCREENSHOT_TEXT,
            "session_id": report["session_id"],
            "import_to_session": True,
            "source_image_path": REAL_SCREENSHOT_PATH,
        },
    )
    report["checks"]["screenshot_import_status"] = import_response.status_code
    import_payload = import_response.json()
    report["checks"]["imported_count"] = import_payload.get("imported_count", 0)
    imported_terms = [item.get("term") for item in import_payload.get("words", [])]
    if import_response.status_code != 200 or import_payload.get("imported_count", 0) < 10:
        report["issues"].append("screenshot import did not persist expected vocabulary count")

    with transaction(db_path) as conn:
        provider = ModelProvider("mock", "mock-tutor-v1")
        question = QuestionAuthorAgent(conn, provider).ensure_first_question(str(report["session_id"]))
        question_term = ""
        if question.knowledge_tags:
            question_term = question.knowledge_tags[0].split(":", 1)[-1]
        evaluation = EvaluatorTutorAgent(conn, provider).evaluate(
            str(report["session_id"]),
            question.model_dump(),
            "A",
        )
        active = QuestionService(conn).active_question(str(report["session_id"]))
        knowledge_row = conn.execute(
            """
            SELECT term, mastery_score, due_at
            FROM knowledge_items
            WHERE term=? AND exam_id='cet4'
            """,
            (question_term,),
        ).fetchone()
        attempt_count = conn.execute(
            "SELECT COUNT(*) AS total FROM attempts WHERE session_id=?",
            (str(report["session_id"]),),
        ).fetchone()["total"]
        panel = SessionService(conn).daily_panel(str(report["session_id"]))
        report["checks"].update(
            {
                "question_term": question_term,
                "question_uses_imported_term": question_term in imported_terms,
                "evaluation_correct": evaluation.is_correct,
                "active_question_after_answer": active,
                "attempt_count": attempt_count,
                "knowledge_term": knowledge_row["term"] if knowledge_row else "",
                "knowledge_mastery_score": knowledge_row["mastery_score"] if knowledge_row else 0,
                "knowledge_due_at_present": bool(knowledge_row and knowledge_row["due_at"]),
                "daily_panel_knowledge_total": panel.get("knowledge_total", 0),
                "token_usage": token_totals(conn),
            }
        )

    if not report["checks"]["question_uses_imported_term"]:
        report["issues"].append("generated fallback question did not use imported vocabulary")
    if not report["checks"]["evaluation_correct"]:
        report["issues"].append("evaluation algorithm did not mark option A correct")
    if not report["checks"]["knowledge_due_at_present"]:
        report["issues"].append("knowledge mastery update did not set next review time")
    if not os.getenv("LANGDRILL_PROVIDER_API_KEY"):
        report["live_model_call"] = "skipped_missing_LANGDRILL_PROVIDER_API_KEY"
    else:
        report["live_model_call"] = "configured_but_not_spent_by_default"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["issues"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
