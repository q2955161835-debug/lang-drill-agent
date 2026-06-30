from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from langdrill_agent.config import load_settings


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"

IMAGE_PATHS = [
    "D:/29551/QQ_Files/Tencent Files/2955161835/nt_qq/nt_data/Pic/2026-06/Ori/b305dcda304ff9d2744385d455cde101.png",
    "D:/29551/QQ_Files/Tencent Files/2955161835/nt_qq/nt_data/Pic/2026-06/Ori/edb688058b034b1561b9ee7159d48d38.png",
    "D:/29551/QQ_Files/Tencent Files/2955161835/nt_qq/nt_data/Pic/2026-06/Ori/65a03fb7c59367f9d718b38c3a590827.png",
]

VOCAB_TEXT = """
collision
n. 碰撞；冲突
snowstorm
n. 暴风雪
collection
n. 收藏，收藏品；集合
dry
adj. 干的，干旱的；v. 变干
apply
v. 申请；应用；适用
bull
n. 公牛；雄性的鲸、象等大动物
germ
n. 细菌（多指病菌）
fork
n. 叉，餐叉
mysterious
adj. 神秘的
pot
n. 锅
book
n. 书；v. 预订
chair
n. 椅子
meal
n. 一餐，一顿饭；膳食
steal
v. 偷盗，窃取
save
v. 节省，节约；救，救助
emerge
vi. 浮现；出现；兴起；显露
dish
n. 菜肴
aunt
n. 小姨，姑妈，伯母，舅妈
dull
adj. 枯燥的，沉闷的；愚笨的，迟钝的；v. 变得无光泽
state
n. 州，邦；状态，情况；国家，政府；v. 说明，陈述
champion
n. 冠军，优胜者
aware
adj. 意识到的；知道的
root
v. 生根；n. 根源
extreme
adj. 极端的；n. 极端
skin
n. 皮，皮肤，肤色；兽皮，毛皮
hence
adv. 因此
vigorous
adj. 强有力的，有活力的
waterfall
n. 瀑布
fierce
adj. 凶猛的，凶狠的；激烈的
contrary
adj. 对立的，相反的；叛逆的
discard
v. 丢掉
evident
adj. 显然的，明显的，明白的
fall
vi. 下降，减弱；落下；跌倒，突然倒下
class
n. 课，班级，等级制度
altogether
adv. 完全，总共
forever
adv. 永远
""".strip()


def _post(client: httpx.Client, path: str, payload: dict[str, Any], timeout: float = 180.0) -> tuple[int, dict[str, Any]]:
    response = client.post(f"{BASE_URL}{path}", json=payload, timeout=timeout)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:500]}
    return response.status_code, data


def _get(client: httpx.Client, path: str, timeout: float = 20.0) -> tuple[int, dict[str, Any]]:
    response = client.get(f"{BASE_URL}{path}", timeout=timeout)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:500]}
    return response.status_code, data


def _query_db(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def main() -> int:
    started = time.perf_counter()
    settings = load_settings()
    db_path = settings.db_path
    report: dict[str, Any] = {
        "base_url": BASE_URL,
        "db_path": str(db_path),
        "image_paths_exist": {path: Path(path).exists() for path in IMAGE_PATHS},
        "checks": {},
        "issues": [],
    }

    with httpx.Client() as client:
        status, bootstrap = _get(client, "/api/bootstrap")
        report["checks"]["bootstrap_status"] = status
        report["checks"]["provider"] = {
            "provider_id": bootstrap.get("model_config", {}).get("provider_id"),
            "model": bootstrap.get("model_config", {}).get("model"),
            "has_api_key": bootstrap.get("model_config", {}).get("has_api_key"),
            "visible_in_picker": bootstrap.get("model_config", {}).get("visible_in_picker"),
        }
        if status != 200:
            report["issues"].append("bootstrap endpoint failed")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        if not bootstrap.get("model_config", {}).get("has_api_key"):
            report["issues"].append("current model provider has no API key")

        chat_content = (
            "真实联调：请根据以下 CET-4 词汇生成一组选择题，先完整出题入库，再展示第一题。\n\n"
            f"{VOCAB_TEXT}"
        )
        status, chat = _post(
            client,
            "/api/chat",
            {"content": chat_content, "force_new_session": True},
            timeout=240.0,
        )
        session_id = chat.get("session_id", "")
        active_question = chat.get("active_question")
        report["session_id"] = session_id
        report["checks"]["initial_chat_status"] = status
        report["checks"]["initial_chat_message"] = chat.get("message", {}).get("content", "")[:500]
        report["checks"]["active_question_created"] = bool(active_question)
        if status != 200 or not session_id:
            report["issues"].append("initial chat did not create a session")
        if chat.get("message", {}).get("content", "").startswith("⚠️"):
            report["issues"].append("initial real model question generation failed")
        if not active_question:
            report["issues"].append("initial chat did not return an active question")

        if session_id:
            status, parsed = _post(
                client,
                "/api/screenshot/parse",
                {
                    "text": VOCAB_TEXT,
                    "session_id": session_id,
                    "import_to_session": True,
                    "auto_start_drill": True,
                    "force_new_session": True,
                    "source_image_path": ";".join(IMAGE_PATHS),
                },
                timeout=240.0,
            )
            report["checks"]["screenshot_parse_status"] = status
            report["checks"]["parsed_word_count"] = len(parsed.get("words", []))
            report["checks"]["imported_count"] = parsed.get("imported_count")
            report["checks"]["screenshot_auto_started"] = parsed.get("auto_started")
            if status != 200 or parsed.get("imported_count", 0) < 30:
                report["issues"].append("screenshot vocabulary import did not import expected word count")
            if parsed.get("auto_started"):
                session_id = parsed.get("session_id", session_id)
                active_question = parsed.get("active_question") or active_question
                report["screenshot_session_id"] = session_id
                report["checks"]["screenshot_active_question"] = bool(active_question)
                report["checks"]["screenshot_question_prompt"] = (active_question or {}).get("prompt", "")[:500]
                prompt = (active_question or {}).get("prompt", "")
                if "Choose the best word to complete the sentence" not in prompt and "______" not in prompt:
                    report["issues"].append("screenshot auto question did not use exam-style cloze context")
                if "最合适的理解" in prompt or "中文释义" in prompt:
                    report["issues"].append("screenshot auto question still looks like a vocabulary-card meaning match")
            else:
                report["issues"].append("screenshot import did not auto-start a drill")

        if session_id and active_question:
            status, explanation = _post(
                client,
                "/api/chat",
                {
                    "content": "请给我一点提示，不要直接告诉正确答案。",
                    "session_id": session_id,
                    "question_id": active_question.get("id"),
                },
                timeout=180.0,
            )
            report["checks"]["explanation_status"] = status
            report["checks"]["explanation_message"] = explanation.get("message", {}).get("content", "")[:500]
            if status != 200 or explanation.get("message", {}).get("content", "").startswith("⚠️"):
                report["issues"].append("real model explanation failed")
            if "当前题组仍在进行中" in explanation.get("message", {}).get("content", ""):
                report["issues"].append("hint/explanation request was routed as continue drill")

            answer_letter = (active_question.get("answer") or {}).get("letter") or "A"
            status, answer = _post(
                client,
                "/api/chat",
                {
                    "content": answer_letter,
                    "session_id": session_id,
                    "question_id": active_question.get("id"),
                    "selected_option": answer_letter,
                    "extra_prompt": "请补充一个短例句，帮助我记住这个词。",
                },
                timeout=180.0,
            )
            report["checks"]["answer_status"] = status
            report["checks"]["answer_message"] = answer.get("message", {}).get("content", "")[:500]
            report["checks"]["next_question_after_answer"] = bool(answer.get("active_question"))
            if status != 200 or answer.get("message", {}).get("content", "").startswith("⚠️"):
                report["issues"].append("real model answer extra feedback failed")

            status, continued = _post(
                client,
                "/api/chat",
                {"content": "下一题", "session_id": session_id},
                timeout=60.0,
            )
            report["checks"]["continue_status"] = status
            report["checks"]["continue_message"] = continued.get("message", {}).get("content", "")[:300]
            if status != 200 or "不重新" not in continued.get("message", {}).get("content", ""):
                report["issues"].append("continue drill did not preserve current question set")

            status, branch = _post(
                client,
                "/api/branch",
                {
                    "session_id": session_id,
                    "selected_text": "collision",
                    "message": "围绕 collision 开一个分支解释。",
                },
                timeout=60.0,
            )
            branch_id = branch.get("branch_id", "")
            report["branch_id"] = branch_id
            report["checks"]["branch_create_status"] = status
            if status != 200 or not branch_id:
                report["issues"].append("branch creation failed")

            if branch_id:
                status, branch_reply = _post(
                    client,
                    f"/api/branch/{branch_id}/messages",
                    {"message": "请给一个 CET-4 难度例句和记忆提示。"},
                    timeout=180.0,
                )
                report["checks"]["branch_reply_status"] = status
                report["checks"]["branch_reply_message"] = branch_reply.get("message", "")[:500]
                if status != 200 or "当前模型无法回复" in branch_reply.get("message", ""):
                    report["issues"].append("real model branch reply failed")

        status, summary = _post(client, "/api/chat", {"content": "总结", "session_id": session_id}, timeout=60.0)
        report["checks"]["summary_status"] = status
        report["checks"]["summary_message"] = summary.get("message", {}).get("content", "")[:300]
        if status != 200 or "今日学习总结" not in summary.get("message", {}).get("content", ""):
            report["issues"].append("summary flow failed")

        status, mirror = _get(client, "/api/phone-mirror/status")
        report["checks"]["phone_mirror_status"] = status
        report["checks"]["phone_mirror_payload"] = {
            "adb_available": mirror.get("adb_available"),
            "scrcpy_available": mirror.get("scrcpy_available"),
            "devices_count": len(mirror.get("devices", []) or []),
        }
        if status != 200:
            report["issues"].append("phone mirror status endpoint failed")

    if session_id:
        question_rows = _query_db(
            db_path,
            "SELECT id, status, sequence, prompt FROM questions WHERE session_id=? ORDER BY sequence",
            (session_id,),
        )
        model_calls = _query_db(
            db_path,
            "SELECT agent_name, task_type, provider_id, model, input_tokens, output_tokens, validation_status FROM model_calls ORDER BY created_at DESC LIMIT 12",
        )
        imported_terms = _query_db(
            db_path,
            """
            SELECT term, meaning
            FROM knowledge_items
            WHERE source_scope='screenshot_import'
              AND term IN ('collision','snowstorm','collection','vigorous','waterfall','forever')
            ORDER BY term
            """,
        )
        report["db_checks"] = {
            "question_count_for_session": len(question_rows),
            "question_statuses": [row["status"] for row in question_rows],
            "imported_sample_terms": imported_terms,
            "recent_model_calls": model_calls,
        }
        if len(question_rows) < 2:
            report["issues"].append("question set did not persist multiple questions")
        if not any(row.get("provider_id") == "mimo" for row in model_calls):
            report["issues"].append("no recent model call recorded for mimo")
        recent_task_types = {row.get("task_type") for row in model_calls}
        for expected_task_type in {"explanation", "evaluation_extra_prompt", "branch_chat"}:
            if expected_task_type not in recent_task_types:
                report["issues"].append(f"model call was not recorded for {expected_task_type}")

    report["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
