from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from langdrill_agent.data_paths import DataPathService  # noqa: E402
from langdrill_agent.db import init_db, transaction  # noqa: E402
from langdrill_agent.paper_assets import BUILTIN_PAPER_EXAM_IDS  # noqa: E402
from langdrill_agent.services import PastPaperService, SourceService  # noqa: E402
from langdrill_agent.utils import dumps  # noqa: E402


OLD_JAPANESE_DB = Path("D:/0文件夹/日语四级/data/study.db")
WORD_SCREENSHOT_DIR = REPO_ROOT / "单词"
DEFAULT_DEMO_ROOT = REPO_ROOT / "测试数据" / "演示数据库" / "产品网站演示-20260703"
SCREENSHOT_CHOICES = [
    "65a03fb7c59367f9d718b38c3a590827.png",
    "b305dcda304ff9d2744385d455cde101.png",
]


BASE_ENGLISH_WORDS = [
    ("skin", "n.", "皮；皮肤；肤色"),
    ("hence", "adv.", "因此"),
    ("vigorous", "adj.", "强有力的；有活力的"),
    ("waterfall", "n.", "瀑布"),
    ("fierce", "adj.", "凶猛的；激烈的"),
    ("contrary", "adj.", "相反的；对立的"),
    ("discard", "v.", "丢弃；抛弃"),
    ("evident", "adj.", "显然的；明显的"),
    ("collision", "n.", "碰撞；冲突"),
    ("snowstorm", "n.", "暴风雪"),
    ("collection", "n.", "收藏；集合"),
    ("apply", "v.", "申请；应用；适用"),
    ("vehicle", "n.", "车辆；交通工具"),
    ("mysterious", "adj.", "神秘的"),
    ("cotton", "n.", "棉花；棉布"),
    ("guide", "n./v.", "指南；引导"),
    ("disguise", "n./v.", "伪装；掩饰"),
    ("beast", "n.", "野兽"),
    ("dirt", "n.", "灰尘；污垢"),
    ("germ", "n.", "细菌；萌芽"),
    ("fork", "n.", "叉；餐叉"),
    ("pot", "n.", "锅；罐"),
    ("chair", "n.", "椅子；主持"),
    ("forever", "adv.", "永远"),
    ("altogether", "adv.", "完全；总共"),
    ("class", "n.", "班级；类别"),
    ("bull", "n.", "公牛"),
    ("dry", "adj./v.", "干的；变干"),
    ("book", "n./v.", "书；预订"),
]


SUPPLEMENTAL_ENGLISH_WORDS = [
    ("research", "n./v.", "研究；调查"),
    ("course", "n.", "课程；过程；一道菜"),
    ("blood", "n.", "血液；血统"),
    ("executive", "n./adj.", "经理；行政人员；执行的"),
    ("adequate", "adj.", "足够的；充分的"),
    ("process", "n./v.", "过程；加工；处理"),
    ("bow", "v./n.", "鞠躬；弓"),
    ("laser", "n.", "激光"),
    ("robe", "n.", "长袍；礼服"),
    ("loyalty", "n.", "忠诚"),
    ("velocity", "n.", "速度"),
    ("excessive", "adj.", "过多的；过度的"),
    ("support", "n./v.", "支持；鼓励"),
    ("pill", "n.", "药丸"),
    ("dog", "n.", "狗；犬科动物"),
    ("indifferent", "adj.", "不感兴趣的；漠不关心的"),
    ("mountain", "n.", "山；山脉"),
    ("switch", "v./n.", "改变；开关"),
    ("numerous", "adj.", "许多的"),
    ("north", "adj./n.", "北方的；北方"),
    ("brief", "adj.", "简短的"),
    ("mild", "adj.", "温和的；清淡的"),
    ("influence", "n./v.", "影响"),
    ("consume", "v.", "消费；消耗"),
    ("capture", "v.", "捕获；夺取"),
    ("release", "v./n.", "释放；发布"),
    ("efficient", "adj.", "高效的"),
    ("accurate", "adj.", "准确的"),
    ("benefit", "n./v.", "好处；受益"),
    ("community", "n.", "社区；群体"),
    ("convenient", "adj.", "方便的"),
    ("creative", "adj.", "有创造力的"),
    ("decline", "v./n.", "下降；拒绝"),
    ("demand", "n./v.", "需求；要求"),
    ("economy", "n.", "经济"),
    ("environment", "n.", "环境"),
    ("essential", "adj.", "必要的；本质的"),
    ("evidence", "n.", "证据"),
    ("expand", "v.", "扩大；扩展"),
    ("experience", "n./v.", "经验；经历"),
    ("factor", "n.", "因素"),
    ("financial", "adj.", "金融的；财务的"),
    ("function", "n./v.", "功能；运转"),
    ("generation", "n.", "一代；产生"),
    ("increase", "v./n.", "增加"),
    ("indicate", "v.", "表明；指出"),
    ("industry", "n.", "工业；行业"),
    ("journal", "n.", "期刊；日志"),
    ("knowledge", "n.", "知识"),
    ("maintain", "v.", "维持；保养"),
    ("measure", "v./n.", "测量；措施"),
    ("method", "n.", "方法"),
    ("obvious", "adj.", "明显的"),
    ("policy", "n.", "政策"),
    ("positive", "adj.", "积极的；正面的"),
    ("previous", "adj.", "以前的"),
    ("produce", "v.", "生产；产生"),
    ("quality", "n.", "质量"),
    ("resource", "n.", "资源"),
    ("responsible", "adj.", "负责的"),
    ("schedule", "n./v.", "时间表；安排"),
    ("significant", "adj.", "重要的；显著的"),
    ("similar", "adj.", "相似的"),
    ("society", "n.", "社会"),
    ("strategy", "n.", "策略"),
    ("structure", "n.", "结构"),
    ("suggest", "v.", "建议；暗示"),
    ("technology", "n.", "技术"),
    ("traditional", "adj.", "传统的"),
    ("transport", "n./v.", "运输"),
    ("valuable", "adj.", "有价值的"),
    ("various", "adj.", "各种各样的"),
    ("wealth", "n.", "财富"),
]


ENGLISH_WORDS = list(BASE_ENGLISH_WORDS)


ENGLISH_QUESTIONS = [
    {
        "prompt": "【词汇语境】The result was so ______ that even the least experienced student could see the pattern.",
        "options": ["evident", "fierce", "mysterious", "contrary"],
        "letter": "A",
        "correct": "evident",
        "explanation": "evident 表示“明显的”，符合后半句 everyone could see the pattern 的语义线索。",
        "tags": ["vocabulary:evident"],
        "type": "multiple_choice",
        "difficulty": 0.35,
    },
    {
        "prompt": "【完形填空】The lab had to ______ the samples because they were stored at the wrong temperature.",
        "options": ["discard", "apply", "guide", "collect"],
        "letter": "A",
        "correct": "discard",
        "explanation": "discard 表示“丢弃”，样本保存温度错误后不能继续使用。",
        "tags": ["vocabulary:discard"],
        "type": "cloze",
        "difficulty": 0.45,
    },
    {
        "prompt": "【同义改写】Which sentence best keeps the meaning of “The new rule is contrary to the old policy”?",
        "options": [
            "The new rule is opposite to the old policy.",
            "The new rule is copied from the old policy.",
            "The new rule is hidden in the old policy.",
            "The new rule is weaker than the old policy.",
        ],
        "letter": "A",
        "correct": "The new rule is opposite to the old policy.",
        "explanation": "contrary to 表示“与……相反”，opposite to 是最接近的同义表达。",
        "tags": ["vocabulary:contrary"],
        "type": "multiple_choice",
        "difficulty": 0.5,
    },
    {
        "prompt": "【阅读理解】A snowstorm delayed all vehicles on the mountain road. The rescue team waited until the wind became less fierce. What happened first?",
        "options": [
            "The storm delayed traffic on the road.",
            "The rescue team reached the town immediately.",
            "The wind became stronger at once.",
            "The vehicles were discarded by the team.",
        ],
        "letter": "A",
        "correct": "The storm delayed traffic on the road.",
        "explanation": "原文先说暴风雪延误了车辆，随后才说救援队等待风势减弱。",
        "tags": ["vocabulary:snowstorm", "vocabulary:vehicle", "vocabulary:fierce"],
        "type": "multiple_choice",
        "difficulty": 0.55,
    },
    {
        "prompt": "【词汇搭配】You must ______ for the scholarship before Friday if you want to be considered.",
        "options": ["apply", "collide", "skin", "dry"],
        "letter": "A",
        "correct": "apply",
        "explanation": "apply for 表示“申请”，scholarship 奖学金通常与 apply for 搭配。",
        "tags": ["vocabulary:apply"],
        "type": "multiple_choice",
        "difficulty": 0.4,
    },
    {
        "prompt": "【当前演示题】The museum has a large ______ of local paintings and old photographs.",
        "options": ["collection", "collision", "waterfall", "germ"],
        "letter": "A",
        "correct": "collection",
        "explanation": "collection 表示“收藏品；集合”，与 museum、paintings、photographs 搭配自然。",
        "tags": ["vocabulary:collection"],
        "type": "multiple_choice",
        "difficulty": 0.38,
    },
    {
        "prompt": "【翻译判断】“这辆车可以作为移动图书馆使用。” Which translation is best?",
        "options": [
            "The vehicle can be used as a mobile library.",
            "The collection can be used as a mobile library.",
            "The skin can be used as a mobile library.",
            "The snowstorm can be used as a mobile library.",
        ],
        "letter": "A",
        "correct": "The vehicle can be used as a mobile library.",
        "explanation": "vehicle 是“车辆；交通工具”，can be used as 表示“可以作为……使用”。",
        "tags": ["vocabulary:vehicle"],
        "type": "translation",
        "difficulty": 0.52,
    },
    {
        "prompt": "【阅读细节】The guide asked visitors not to touch the cotton cloth because dirt on the skin could damage it. What should visitors avoid?",
        "options": [
            "Touching the cloth with dirty hands.",
            "Reading the guide before entering.",
            "Taking photos of the waterfall.",
            "Applying for a museum card.",
        ],
        "letter": "A",
        "correct": "Touching the cloth with dirty hands.",
        "explanation": "句子说明皮肤上的污垢可能损坏棉布，所以应避免用脏手触摸。",
        "tags": ["vocabulary:guide", "vocabulary:cotton", "vocabulary:dirt", "vocabulary:skin"],
        "type": "multiple_choice",
        "difficulty": 0.6,
    },
    {
        "prompt": "【词义辨析】The actor wore a disguise so that nobody would recognize him in the station.",
        "options": ["something used to hide identity", "a public announcement", "a violent animal", "a traffic accident"],
        "letter": "A",
        "correct": "something used to hide identity",
        "explanation": "disguise 是“伪装；伪装物”，这里是为了不被认出。",
        "tags": ["vocabulary:disguise"],
        "type": "multiple_choice",
        "difficulty": 0.45,
    },
    {
        "prompt": "【短答选择】Which word can describe a strong, energetic training plan?",
        "options": ["vigorous", "dry", "contrary", "mysterious"],
        "letter": "A",
        "correct": "vigorous",
        "explanation": "vigorous 表示“强有力的；有活力的”，可形容训练计划强度足。",
        "tags": ["vocabulary:vigorous"],
        "type": "short_answer",
        "difficulty": 0.42,
    },
    {
        "prompt": "【完形填空】The cause of the strange noise remained ______ until the engineer opened the machine.",
        "options": ["mysterious", "evident", "dry", "fierce"],
        "letter": "A",
        "correct": "mysterious",
        "explanation": "mysterious 表示“神秘的；难以解释的”，符合 unknown cause 的语义。",
        "tags": ["vocabulary:mysterious"],
        "type": "cloze",
        "difficulty": 0.48,
    },
    {
        "prompt": "【阅读推断】A bull ran into the fence, and the sudden collision frightened the children. What can be inferred?",
        "options": [
            "The children were scared by an unexpected impact.",
            "The children collected old photographs.",
            "The bull guided visitors safely.",
            "The fence became completely dry.",
        ],
        "letter": "A",
        "correct": "The children were scared by an unexpected impact.",
        "explanation": "collision 是“碰撞”，frightened 表示受惊；正确项对原文进行了概括改写。",
        "tags": ["vocabulary:bull", "vocabulary:collision"],
        "type": "multiple_choice",
        "difficulty": 0.55,
    },
]


@dataclass
class QuestionRecord:
    prompt: str
    options: list[str]
    letter: str
    correct: str
    explanation: str
    tags: list[str]
    type: str = "multiple_choice"
    difficulty: float = 0.5
    source_title: str = "演示题组"


OCR_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z-]{2,18}$")
OCR_POS_RE = re.compile(r"^(n|v|vi|vt|adj|adv|prep|conj|pron|num|excl)\.", re.IGNORECASE)
OCR_UI_NOISE = {
    "abc",
    "word",
    "words",
    "list",
    "speed",
    "spelling",
    "demo",
}
OCR_BAD_TERMS = {"abe", "bop", "inp", "ing", "signifi", "strang", "strans"}
OCR_MEANING_NOISE = ["速听", "速刷", "单词选义", "拼写", "听写", "单透义"]
OCR_TERM_FIXES = {
    "aunt": ("n.", "姑妈；姨母"),
    "aware": ("adj.", "意识到的"),
    "brood": ("n./v.", "一窝；沉思"),
    "exaggerate": ("v.", "夸大；夸张"),
    "fancy": ("adj./v.", "精美的；想象"),
    "fall": ("v./n.", "落下；下降"),
    "glimpse": ("n./v.", "一瞥；瞥见"),
    "hesitate": ("v.", "犹豫；顾虑"),
    "nasty": ("adj.", "令人不快的；恶劣的"),
    "project": ("n./v.", "项目；预计；投射"),
    "publish": ("v.", "出版；发表"),
    "tablet": ("n.", "药片；碑"),
}


def clean_ocr_text(text: str) -> str:
    cleaned = text.strip().replace("：", ";").replace("；", ";")
    for noise in OCR_MEANING_NOISE:
        cleaned = cleaned.replace(noise, "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r";\s*;", ";", cleaned)
    cleaned = cleaned.replace("V.", "v.").replace("adi.", "adj.").replace("ad].", "adj.")
    return cleaned.strip(" ,;")


def is_english_word_candidate(text: str) -> bool:
    term = text.lower().strip()
    if term in OCR_UI_NOISE or term in OCR_BAD_TERMS or len(term) < 4:
        return False
    return bool(OCR_WORD_RE.fullmatch(term))


def split_pos_and_meaning(raw_meaning: str) -> tuple[str, str]:
    raw_meaning = clean_ocr_text(raw_meaning)
    match = OCR_POS_RE.match(raw_meaning)
    if not match:
        return "", raw_meaning
    pos = match.group(0).lower()
    meaning = raw_meaning[len(pos):].strip(" ,;")
    return pos, meaning or raw_meaning


def merge_word_records(groups: list[list[tuple[str, str, str]]]) -> list[tuple[str, str, str]]:
    merged: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for group in groups:
        for term, pos, meaning in group:
            normalized = re.sub(r"[^a-z-]", "", term.lower())
            if not normalized or normalized in seen:
                continue
            clean_meaning = clean_ocr_text(meaning)
            if not clean_meaning:
                continue
            if normalized in OCR_TERM_FIXES:
                pos, clean_meaning = OCR_TERM_FIXES[normalized]
            seen.add(normalized)
            merged.append((normalized, pos.strip(), clean_meaning))
    return merged


def extract_words_from_screenshots() -> list[tuple[str, str, str]]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return []

    extracted: list[tuple[str, str, str]] = []
    if not WORD_SCREENSHOT_DIR.exists():
        return extracted

    ocr = RapidOCR()
    for path in sorted(WORD_SCREENSHOT_DIR.glob("*.png")):
        result, _ = ocr(str(path))
        pending_term = ""
        pending_meaning: list[str] = []

        def flush_pending() -> None:
            nonlocal pending_term, pending_meaning
            if pending_term and pending_meaning:
                raw_meaning = "; ".join(pending_meaning)
                pos, meaning = split_pos_and_meaning(raw_meaning)
                extracted.append((pending_term, pos, meaning))
            pending_term = ""
            pending_meaning = []

        for item in result or []:
            text = clean_ocr_text(str(item[1]))
            if not text:
                continue
            if is_english_word_candidate(text):
                flush_pending()
                pending_term = text.lower()
                continue
            has_chinese = bool(re.search(r"[\u4e00-\u9fff]", text))
            if pending_term and (has_chinese or OCR_POS_RE.match(text)):
                pending_meaning.append(text)
        flush_pending()
    return extracted


def build_english_words() -> list[tuple[str, str, str]]:
    extracted = extract_words_from_screenshots()
    return merge_word_records([BASE_ENGLISH_WORDS, SUPPLEMENTAL_ENGLISH_WORDS, extracted])


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def ts(day: str, hour: int, minute: int = 0) -> str:
    return f"{day} {hour:02d}:{minute:02d}:00"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成产品网站演示数据库和截图导入素材。")
    parser.add_argument("--root", default=str(DEFAULT_DEMO_ROOT), help="演示根目录，默认写入测试数据。")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的演示目录。")
    return parser.parse_args()


def ensure_demo_root(root: Path, overwrite: bool) -> None:
    resolved = root.resolve()
    test_root = (REPO_ROOT / "测试数据").resolve()
    if test_root not in resolved.parents and resolved != test_root:
        raise SystemExit(f"演示目录必须位于测试数据下：{resolved}")
    if resolved.exists():
        if not overwrite:
            raise SystemExit(f"演示目录已存在，请加 --overwrite 或换目录：{resolved}")
        shutil.rmtree(resolved)
    (resolved / "data").mkdir(parents=True, exist_ok=True)
    (resolved / "logs").mkdir(parents=True, exist_ok=True)
    (resolved / "input-screenshots").mkdir(parents=True, exist_ok=True)
    (resolved / "product-screenshots").mkdir(parents=True, exist_ok=True)
    (resolved / "papers").mkdir(parents=True, exist_ok=True)


def seed_reference_data(db_path: Path) -> None:
    init_db(db_path)
    with transaction(db_path) as conn:
        SourceService(conn).seed_common_sources()
        service = PastPaperService(conn)
        for exam_id in BUILTIN_PAPER_EXAM_IDS:
            service.seed_default_papers(exam_id)
            selected = [f"paper_{exam_id}_{year}" for year in PastPaperService.DEFAULT_RECENT_YEARS]
            conn.execute(
                """
                INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (f"past_papers.selected.{exam_id}", dumps({"paper_ids": selected})),
            )


def insert_profile(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE user_profiles
        SET display_name=?, target_language=?, exam_id=?, exam_name=?, deadline=?,
            daily_minutes=?, learning_goal=?, learning_background=?, persona=?,
            global_user_prompt=?, updated_at=?
        WHERE id=1
        """,
        (
            "boss",
            "英语",
            "cet4",
            "大学英语四级",
            "2026-12-12T09:00",
            45,
            "英语四级目标 600 分，重点提升阅读速度、词汇辨析和完形稳定性。",
            "高中英语基础扎实，但长难句和近义词辨析容易丢分；希望通过截图词表和考试式题组滚动复习。",
            "professional",
            "讲解先给结论，再用 2-3 个要点拆原因；错题优先指出干扰项陷阱。",
            "2026-07-03 13:20:00",
        ),
    )


def insert_app_settings(conn: sqlite3.Connection) -> None:
    settings = {
        "context.settings": {
            "max_tokens": 1_000_000,
            "compression_project": "Microsoft LLMLingua",
            "compression_project_url": "https://github.com/microsoft/LLMLingua",
            "compression_optional_extra": "context-compression",
        },
        "model.default": {
            "provider_id": "mimo",
            "base_url": "https://api.xiaomimimo.com/anthropic",
            "model": "mimo-v2.5-pro",
            "thinking_level": "enabled",
            "api_format": "anthropic-messages",
            "vision": False,
        },
        "model.provider_overrides": {
            "deepseek": {
                "base_url": "https://api.deepseek.com",
                "api_format": "openai-chat-completions",
                "added_models": [
                    {
                        "id": "deepseek-chat-demo",
                        "label": "DeepSeek Chat 演示模型",
                        "context_tokens": 1_000_000,
                        "vision": False,
                        "visible": True,
                        "custom": True,
                        "reasoning": {
                            "default_level": "",
                            "parameter": "deepseek_thinking",
                            "levels": [],
                        },
                    }
                ],
                "model_capability_overrides": {"deepseek-chat-demo": {"vision": False}},
                "model_visibility_overrides": {"deepseek-v4-flash": False},
            }
        },
        "past_papers.question_types.cet4": {
            "enabled_type_ids": ["vocabulary", "cloze", "reading", "translation", "writing"],
        },
        "past_papers.question_types.cjt4": {
            "enabled_type_ids": ["vocabulary", "grammar", "reading", "translation", "writing"],
        },
        "skills.enabled": {"enabled_skill_ids": ["multi-search-engine"]},
    }
    for key, value in settings.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (key, dumps(value)),
        )


def insert_knowledge(
    conn: sqlite3.Connection,
    *,
    exam_id: str,
    term: str,
    meaning: str,
    kind: str = "word",
    reading: str = "",
    source_scope: str = "demo_seed",
    mastery: float = 0.3,
    created_at: str,
) -> None:
    knowledge_id = stable_id("ki", exam_id, kind, term)
    conn.execute(
        """
        INSERT OR REPLACE INTO knowledge_items
        (id, kind, term, reading, meaning, notes, exam_id, source_scope, mastery_score, due_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            knowledge_id,
            kind,
            term,
            reading,
            meaning,
            "产品网站演示数据",
            exam_id,
            source_scope,
            mastery,
            (datetime.fromisoformat(created_at.replace(" ", "T")) + timedelta(days=5)).isoformat(timespec="seconds"),
            created_at,
            created_at,
        ),
    )


def insert_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    title: str,
    folder_date: str,
    exam_id: str,
    status: str,
    plan: dict[str, Any],
    summary: str,
    created_at: str,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO study_sessions
        (id, title, folder_date, exam_id, status, daily_plan_json, summary, token_input, token_output, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            title,
            folder_date,
            exam_id,
            status,
            dumps(plan),
            summary,
            0,
            0,
            created_at,
            updated_at,
        ),
    )


def insert_message(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    role: str,
    content: str,
    created_at: str,
    payload: dict[str, Any] | None = None,
) -> str:
    message_id = stable_id("msg", session_id, role, created_at, content[:60])
    conn.execute(
        """
        INSERT OR REPLACE INTO messages (id, session_id, role, content, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (message_id, session_id, role, content, dumps(payload or {}), created_at),
    )
    return message_id


def answer_payload(question: dict[str, Any], selected_letter: str, is_correct: bool) -> dict[str, Any]:
    selected_letter = selected_letter.upper()
    options = question["options"]
    selected_index = ord(selected_letter) - ord("A")
    selected_answer = options[selected_index] if 0 <= selected_index < len(options) else selected_letter
    return {
        **question,
        "status": "answered",
        "selected_option": selected_letter,
        "selected_answer": selected_answer,
        "is_correct": is_correct,
    }


def insert_question(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    sequence: int,
    record: QuestionRecord,
    status: str,
    created_at: str,
) -> dict[str, Any]:
    question_id = stable_id("q", session_id, sequence, record.prompt)
    answer = {"letter": record.letter.upper(), "correct": record.correct}
    source_refs = [{"title": record.source_title, "boundary": "demo_seed", "created_for": "product_website"}]
    conn.execute(
        """
        INSERT OR REPLACE INTO questions
        (id, session_id, sequence, type, prompt, options_json, answer_json, explanation,
         knowledge_tags_json, difficulty, status, source_refs_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_id,
            session_id,
            sequence,
            record.type,
            record.prompt,
            dumps(record.options),
            dumps(answer),
            record.explanation,
            dumps(record.tags),
            record.difficulty,
            status,
            dumps(source_refs),
            created_at,
        ),
    )
    return {
        "id": question_id,
        "session_id": session_id,
        "sequence": sequence,
        "type": record.type,
        "prompt": record.prompt,
        "options": record.options,
        "answer": answer,
        "explanation": record.explanation,
        "knowledge_tags": record.tags,
        "difficulty": record.difficulty,
        "source_refs": source_refs,
        "set_total": 0,
        "set_done": 0,
    }


def insert_attempt(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    question: dict[str, Any],
    selected_letter: str,
    is_correct: bool,
    feedback: str,
    created_at: str,
) -> None:
    attempt_id = stable_id("att", question["id"], selected_letter, created_at)
    conn.execute(
        """
        INSERT OR REPLACE INTO attempts
        (id, question_id, session_id, user_answer, is_correct, used_hint, feedback, mastery_delta, created_at)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
        """,
        (
            attempt_id,
            question["id"],
            session_id,
            selected_letter.upper(),
            1 if is_correct else 0,
            feedback,
            0.22 if is_correct else -0.18,
            created_at,
        ),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO mastery_events (id, knowledge_id, question_id, attempt_id, event_json, created_at)
        VALUES (?, '', ?, ?, ?, ?)
        """,
        (
            stable_id("mev", attempt_id),
            question["id"],
            attempt_id,
            dumps({"score_after": 0.82 if is_correct else 0.46, "created_from": "demo_seed"}),
            created_at,
        ),
    )


def insert_model_call(
    conn: sqlite3.Connection,
    *,
    task_type: str,
    provider_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    created_at: str,
    agent_name: str = "demo_seed",
    validation_status: str = "not_required",
) -> None:
    call_id = stable_id("call", task_type, provider_id, model, created_at, input_tokens, output_tokens)
    conn.execute(
        """
        INSERT OR REPLACE INTO model_calls
        (id, agent_name, task_type, provider_id, model, prompt_modules_json, input_tokens, output_tokens,
         latency_ms, validation_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            call_id,
            agent_name,
            task_type,
            provider_id,
            model,
            dumps(["core.safety", f"task.{task_type}"]),
            input_tokens,
            output_tokens,
            latency_ms,
            validation_status,
            created_at,
        ),
    )


def complete_question_totals(conn: sqlite3.Connection, session_id: str) -> None:
    rows = conn.execute("SELECT id FROM questions WHERE session_id=? ORDER BY sequence", (session_id,)).fetchall()
    total = len(rows)
    done = conn.execute(
        "SELECT COUNT(*) AS done FROM questions WHERE session_id=? AND status='answered'",
        (session_id,),
    ).fetchone()["done"]
    # Message payloads store their own set totals. They are populated during message insertion.
    _ = (total, done)


def question_record_from_dict(item: dict[str, Any], source_title: str) -> QuestionRecord:
    return QuestionRecord(
        prompt=item["prompt"],
        options=list(item["options"]),
        letter=item["letter"],
        correct=item["correct"],
        explanation=item["explanation"],
        tags=list(item["tags"]),
        type=item.get("type", "multiple_choice"),
        difficulty=float(item.get("difficulty", 0.5)),
        source_title=source_title,
    )


def create_english_sessions(conn: sqlite3.Connection) -> None:
    word_dates = ["2026-06-22", "2026-06-26", "2026-06-30", "2026-07-02"]
    for index, (term, pos, meaning) in enumerate(ENGLISH_WORDS):
        day = word_dates[index % len(word_dates)]
        insert_knowledge(
            conn,
            exam_id="cet4",
            term=term,
            meaning=f"{pos} {meaning}",
            source_scope="screenshot_import",
            mastery=0.82 if index % 3 == 0 else 0.52,
            created_at=ts(day, 9 + index % 8, 10 + index % 40),
        )

    completed_specs = [
        ("ses_demo_cet4_0622", "截图词表练习：skin", "2026-06-22", 0, 8, 12),
        ("ses_demo_cet4_0626", "四级完形与同义改写", "2026-06-26", 2, 9, 10),
        ("ses_demo_cet4_0630", "阅读语境综合训练", "2026-06-30", 4, 10, 12),
    ]
    for session_id, title, day, offset, correct_count, total_count in completed_specs:
        records = [question_record_from_dict(ENGLISH_QUESTIONS[(offset + i) % len(ENGLISH_QUESTIONS)], title) for i in range(total_count)]
        insert_session(
            conn,
            session_id=session_id,
            title=title,
            folder_date=day,
            exam_id="cet4",
            status="completed",
            plan={
                "new_content": [term for term, _, _ in ENGLISH_WORDS[offset : offset + 8]],
                "review_content": ["错题回流", "近三年四级阅读题型"],
                "target_minutes": 45,
                "status": "completed",
                "algorithm": "截图词表优先 + 真题题型配比",
            },
            summary=f"{day} 完成 {total_count} 题，正确 {correct_count} 题；重点复盘词汇语境和干扰项。",
            created_at=ts(day, 19, 5),
            updated_at=ts(day, 20, 10),
        )
        insert_message(
            conn,
            session_id=session_id,
            role="user",
            content="导入今天的截图词表，并生成四级考试式题组。",
            created_at=ts(day, 19, 5),
            payload={"task": "screenshot_import"},
        )
        insert_message(
            conn,
            session_id=session_id,
            role="assistant",
            content=f"已先生成并入库 {total_count} 道题。本轮按词汇语境、完形、阅读和翻译判断混合推进。",
            created_at=ts(day, 19, 6),
            payload={"source": "demo_seed"},
        )
        for seq, record in enumerate(records, start=1):
            question = insert_question(conn, session_id=session_id, sequence=seq, record=record, status="answered", created_at=ts(day, 19, 6 + seq))
            question["set_total"] = total_count
            question["set_done"] = seq
            is_correct = seq <= correct_count
            selected = record.letter if is_correct else "B"
            if selected == record.letter:
                selected = record.letter
            elif record.letter == "B":
                selected = "C"
            feedback = (
                f"判断：{'正确' if is_correct else '不正确'}。\n\n"
                f"正确答案：{record.letter} {record.correct}\n\n"
                f"讲解：{record.explanation}"
            )
            insert_attempt(
                conn,
                session_id=session_id,
                question=question,
                selected_letter=selected,
                is_correct=is_correct,
                feedback=feedback,
                created_at=ts(day, 19, 20 + seq),
            )
        for call_index in range(4):
            insert_model_call(
                conn,
                task_type="question_authoring" if call_index == 0 else "evaluation",
                provider_id="mimo",
                model="mimo-v2.5-pro",
                input_tokens=1800 + call_index * 180,
                output_tokens=740 + call_index * 90,
                latency_ms=5200 + call_index * 700,
                created_at=ts(day, 19, 8 + call_index * 10),
                agent_name="question_author" if call_index == 0 else "evaluator_tutor",
                validation_status="passed" if call_index == 0 else "not_required",
            )

    create_active_english_session(conn)


def create_active_english_session(conn: sqlite3.Connection) -> None:
    day = "2026-07-02"
    session_id = "ses_demo_cet4_active"
    records = [question_record_from_dict(item, "2026-07-02 截图词表综合练习") for item in ENGLISH_QUESTIONS]
    insert_session(
        conn,
        session_id=session_id,
        title="截图词表练习：collection",
        folder_date=day,
        exam_id="cet4",
        status="active",
        plan={
            "new_content": ["collection", "discard", "evident", "vehicle", "mysterious", "cotton"],
            "review_content": ["错题回流：contrary / fierce", "四级阅读同义改写"],
            "target_minutes": 45,
            "status": "in_progress",
            "algorithm": "截图词表优先；近三年真题题型约束；错题回流补强",
        },
        summary="已完成前 5 题，collection / discard / contrary 仍需重点复盘。当前题停在第 6 题，适合演示答题讲解和分支追问。",
        created_at=ts(day, 20, 2),
        updated_at=ts(day, 20, 42),
    )
    insert_message(
        conn,
        session_id=session_id,
        role="user",
        content="把今天截图里的词表导入，按英语四级题型生成一组练习。",
        created_at=ts(day, 20, 2),
        payload={"task": "screenshot_import"},
    )
    insert_message(
        conn,
        session_id=session_id,
        role="assistant",
        content="截图词表已解析为 12 个高频词，并已先生成完整题组入库。\n\n本轮覆盖：词汇语境、完形填空、阅读理解、同义改写和翻译判断。先从易混词开始。",
        created_at=ts(day, 20, 3),
        payload={"active_question": {"source": "demo_seed"}},
    )
    for seq, record in enumerate(records, start=1):
        status = "answered" if seq <= 5 else "ready"
        question = insert_question(conn, session_id=session_id, sequence=seq, record=record, status=status, created_at=ts(day, 20, 3 + seq))
        question["set_total"] = len(records)
        question["set_done"] = min(seq, 5)
        if seq <= 5:
            selected = record.letter if seq in {1, 3, 5} else ("B" if record.letter != "B" else "C")
            is_correct = selected == record.letter
            feedback = (
                f"判断：{'正确' if is_correct else '不正确'}。\n\n"
                f"正确答案：{record.letter} {record.correct}\n\n"
                f"讲解：{record.explanation}\n\n"
                "补充：你问到干扰项时，优先看句子里的语义触发词，而不是只看中文释义相近。"
            )
            insert_message(
                conn,
                session_id=session_id,
                role="user",
                content=f"{selected}\n补充提问：为什么这里不能选另一个看起来也合理的词？",
                created_at=ts(day, 20, 5 + seq * 3),
                payload={"task": "answer_question"},
            )
            insert_attempt(
                conn,
                session_id=session_id,
                question=question,
                selected_letter=selected,
                is_correct=is_correct,
                feedback=feedback,
                created_at=ts(day, 20, 6 + seq * 3),
            )
            insert_message(
                conn,
                session_id=session_id,
                role="assistant",
                content=f"{feedback}\n\n下一题已就绪：第 {seq + 1} 题 / 共 {len(records)} 题。",
                created_at=ts(day, 20, 7 + seq * 3),
                payload={"answered_question": answer_payload(question, selected, is_correct)},
            )
    insert_message(
        conn,
        session_id=session_id,
        role="user",
        content="请帮我添加一个 DeepSeek 自定义模型，模型名 deepseek-chat-demo，上下文 100 万，文本模型。",
        created_at=ts(day, 20, 39),
        payload={"task": "settings"},
    )
    insert_message(
        conn,
        session_id=session_id,
        role="assistant",
        content="我已整理成可确认的自定义模型草稿。你可以点击下方按钮填入设置页，保存前仍可修改模型名、上下文容量和视觉能力。",
        created_at=ts(day, 20, 40),
        payload={
            "settings_action": {
                "type": "custom_model_draft",
                "label": "自定义模型草稿：DeepSeek",
                "draft": {
                    "provider_id": "deepseek",
                    "model": "deepseek-chat-demo",
                    "label": "DeepSeek Chat 演示模型",
                    "context_tokens": 1_000_000,
                    "vision": False,
                },
            }
        },
    )
    for call_index, task_type in enumerate(["question_authoring", "evaluation", "evaluation", "settings", "branch_chat"]):
        insert_model_call(
            conn,
            task_type=task_type,
            provider_id="mimo" if task_type != "settings" else "deepseek",
            model="mimo-v2.5-pro" if task_type != "settings" else "deepseek-chat-demo",
            input_tokens=2400 + call_index * 260,
            output_tokens=980 + call_index * 120,
            latency_ms=6100 + call_index * 850,
            created_at=ts(day, 20, 4 + call_index * 8),
            agent_name="question_author" if task_type == "question_authoring" else "evaluator_tutor",
            validation_status="passed" if task_type == "question_authoring" else "not_required",
        )


def extract_old_japanese_questions(limit: int = 36) -> list[QuestionRecord]:
    if not OLD_JAPANESE_DB.exists():
        return fallback_japanese_questions()
    conn = sqlite3.connect(OLD_JAPANESE_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT q.section_name, q.question_type, q.difficulty, q.prompt, q.answer, q.explanation, q.knowledge_tags
        FROM questions q
        WHERE q.session_id IN ('eef924fc46a4', 'b98ce3eb0ac5')
          AND q.answer IN ('A', 'B', 'C', 'D')
        ORDER BY q.session_id DESC, q.ordinal ASC
        LIMIT ?
        """,
        (limit * 2,),
    ).fetchall()
    conn.close()
    records: list[QuestionRecord] = []
    for row in rows:
        parsed = split_prompt_options(str(row["prompt"]))
        if not parsed:
            continue
        prompt, options = parsed
        tags = japanese_tag_strings(str(row["knowledge_tags"]))
        records.append(
            QuestionRecord(
                prompt=prompt,
                options=options,
                letter=str(row["answer"]),
                correct=options[ord(str(row["answer"])) - ord("A")],
                explanation=str(row["explanation"]),
                tags=tags,
                type="multiple_choice",
                difficulty=min(max(float(row["difficulty"] or 2) / 5, 0.2), 0.9),
                source_title=f"旧日语四级真实训练：{row['section_name']} / {row['question_type']}",
            )
        )
        if len(records) >= limit:
            break
    return records or fallback_japanese_questions()


def split_prompt_options(prompt: str) -> tuple[str, list[str]] | None:
    pattern = re.compile(
        r"\sA[\.\．]\s*(.*?)\s+B[\.\．]\s*(.*?)\s+C[\.\．]\s*(.*?)\s+D[\.\．]\s*(.*)$",
        re.DOTALL,
    )
    match = pattern.search(prompt)
    if not match:
        return None
    stem = prompt[: match.start()].strip()
    options = [re.sub(r"\s+", " ", match.group(i)).strip() for i in range(1, 5)]
    if len([item for item in options if item]) != 4:
        return None
    return stem, options


def japanese_tag_strings(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except Exception:
        return []
    tags: list[str] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "grammar":
            value = item.get("pattern") or item.get("term")
            if value:
                tags.append(f"grammar:{value}")
        else:
            value = item.get("term") or item.get("pattern")
            if value:
                tags.append(f"vocabulary:{value}")
    return tags


def fallback_japanese_questions() -> list[QuestionRecord]:
    return [
        QuestionRecord(
            prompt="【文字と語彙】次の文の［様子］の読み方を選びなさい。病院から戻った祖母の［様子］を見て、両親は安心した。",
            options=["ようす", "よすう", "ようし", "よしす"],
            letter="A",
            correct="ようす",
            explanation="「様子」は「ようす」と読み、状態や見た感じを表す。",
            tags=["vocabulary:様子"],
            source_title="日语四级演示题",
        )
    ]


def seed_japanese_knowledge(conn: sqlite3.Connection, records: list[QuestionRecord]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records):
        for tag in record.tags:
            prefix, _, value = tag.partition(":")
            if not value or tag in seen:
                continue
            seen.add(tag)
            kind = "grammar" if prefix == "grammar" else "word"
            insert_knowledge(
                conn,
                exam_id="cjt4",
                term=value,
                meaning="旧日语四级真实训练迁移词法点",
                kind=kind,
                source_scope="legacy_cjt4_import",
                mastery=0.8 if index % 4 == 0 else 0.55,
                created_at=ts("2026-04-23" if index % 2 else "2026-04-21", 16 + index % 5, index % 50),
            )


def create_japanese_sessions(conn: sqlite3.Connection) -> None:
    records = extract_old_japanese_questions(36)
    seed_japanese_knowledge(conn, records)
    completed = [
        ("ses_demo_cjt4_0421", "日语四级正式题单：4.21", "2026-04-21", 0, 14, 18),
        ("ses_demo_cjt4_0423", "日语四级阅读与语法：4.23", "2026-04-23", 12, 13, 18),
    ]
    for session_id, title, day, offset, correct_count, total_count in completed:
        insert_session(
            conn,
            session_id=session_id,
            title=title,
            folder_date=day,
            exam_id="cjt4",
            status="completed",
            plan={
                "new_content": ["共に", "縫う", "一般", "刺激", "確か", "きちんと"],
                "review_content": ["文字と語彙", "文法", "阅读同义改写"],
                "target_minutes": 45,
                "status": "completed",
                "algorithm": "旧日语项目真实题单迁移 + 题块连排",
            },
            summary=f"旧日语训练迁移演示：{total_count} 题，正确 {correct_count} 题；覆盖读音、词义、语法和阅读。",
            created_at=ts(day, 19, 10),
            updated_at=ts(day, 21, 0),
        )
        insert_message(
            conn,
            session_id=session_id,
            role="user",
            content="继续今天的日语四级正式题单。",
            created_at=ts(day, 19, 10),
            payload={"task": "daily_drill"},
        )
        insert_message(
            conn,
            session_id=session_id,
            role="assistant",
            content=f"已从旧日语学习库迁移 {total_count} 道题作为演示题组，保持一题一讲和错题回流记录。",
            created_at=ts(day, 19, 11),
            payload={"source": "legacy_cjt4_import"},
        )
        for seq in range(1, total_count + 1):
            record = records[(offset + seq - 1) % len(records)]
            question = insert_question(conn, session_id=session_id, sequence=seq, record=record, status="answered", created_at=ts(day, 19, 11 + seq))
            question["set_total"] = total_count
            question["set_done"] = seq
            is_correct = seq <= correct_count
            selected = record.letter if is_correct else ("B" if record.letter != "B" else "C")
            feedback = (
                f"判断：{'正确' if is_correct else '不正确'}。\n\n"
                f"正确答案：{record.letter} {record.correct}\n\n"
                f"讲解：{record.explanation}"
            )
            insert_attempt(
                conn,
                session_id=session_id,
                question=question,
                selected_letter=selected,
                is_correct=is_correct,
                feedback=feedback,
                created_at=ts(day, 19, 20 + seq),
            )
        for call_index in range(5):
            insert_model_call(
                conn,
                task_type="evaluation" if call_index else "question_authoring",
                provider_id="mimo",
                model="mimo-v2.5-pro",
                input_tokens=2100 + call_index * 220,
                output_tokens=880 + call_index * 110,
                latency_ms=5600 + call_index * 650,
                created_at=ts(day, 19, 12 + call_index * 12),
                agent_name="evaluator_tutor",
                validation_status="passed" if call_index == 0 else "not_required",
            )
    create_active_japanese_session(conn, records)


def create_active_japanese_session(conn: sqlite3.Connection, records: list[QuestionRecord]) -> None:
    day = "2026-07-01"
    session_id = "ses_demo_cjt4_active"
    total_count = 12
    insert_session(
        conn,
        session_id=session_id,
        title="日语四级错题回流",
        folder_date=day,
        exam_id="cjt4",
        status="active",
        plan={
            "new_content": ["片仮名", "何となく", "挑戦", "激しい"],
            "review_content": ["4.23 错题回流", "语法：ために / てしまう / ておく"],
            "target_minutes": 40,
            "status": "in_progress",
            "algorithm": "旧库真实错题 + 新题块补强",
        },
        summary="日语四级演示当前会话：已完成 4 题，下一题展示文字与语汇读音辨析。",
        created_at=ts(day, 18, 45),
        updated_at=ts(day, 19, 25),
    )
    insert_message(
        conn,
        session_id=session_id,
        role="user",
        content="把旧日语四级错题拿出来做一轮回流训练。",
        created_at=ts(day, 18, 45),
        payload={"task": "daily_drill"},
    )
    insert_message(
        conn,
        session_id=session_id,
        role="assistant",
        content="已读取旧日语四级学习痕迹，并生成错题回流题组。题型覆盖文字と語彙、文法、阅读改写和翻译判断。",
        created_at=ts(day, 18, 46),
        payload={"source": "legacy_cjt4_import"},
    )
    for seq in range(1, total_count + 1):
        record = records[(seq + 4) % len(records)]
        status = "answered" if seq <= 4 else "ready"
        question = insert_question(conn, session_id=session_id, sequence=seq, record=record, status=status, created_at=ts(day, 18, 46 + seq))
        question["set_total"] = total_count
        question["set_done"] = min(seq, 4)
        if seq <= 4:
            selected = record.letter if seq in {1, 2, 4} else ("B" if record.letter != "B" else "C")
            is_correct = selected == record.letter
            feedback = (
                f"判断：{'正确' if is_correct else '不正确'}。\n\n"
                f"正确答案：{record.letter} {record.correct}\n\n"
                f"讲解：{record.explanation}\n\n"
                "复习建议：把读音、搭配和句中语气一起记，别只背中文释义。"
            )
            insert_message(
                conn,
                session_id=session_id,
                role="user",
                content=f"{selected}\n补充提问：这个词在考纲里常用哪种写法？",
                created_at=ts(day, 18, 49 + seq * 4),
                payload={"task": "answer_question"},
            )
            insert_attempt(
                conn,
                session_id=session_id,
                question=question,
                selected_letter=selected,
                is_correct=is_correct,
                feedback=feedback,
                created_at=ts(day, 18, 50 + seq * 4),
            )
            insert_message(
                conn,
                session_id=session_id,
                role="assistant",
                content=f"{feedback}\n\n下一题已就绪：第 {seq + 1} 题 / 共 {total_count} 题。",
                created_at=ts(day, 18, 51 + seq * 4),
                payload={"answered_question": answer_payload(question, selected, is_correct)},
            )
    insert_model_call(
        conn,
        task_type="branch_chat",
        provider_id="mimo",
        model="mimo-v2.5-pro",
        input_tokens=1640,
        output_tokens=620,
        latency_ms=4300,
        created_at=ts(day, 19, 20),
        agent_name="branch_assistant",
    )


def copy_demo_screenshots(root: Path) -> list[Path]:
    copied: list[Path] = []
    for name in SCREENSHOT_CHOICES:
        source = WORD_SCREENSHOT_DIR / name
        if not source.exists():
            continue
        target = root / "input-screenshots" / name
        shutil.copy2(source, target)
        copied.append(target)
    ocr_text = "\n".join(f"{term}: {meaning}" for term, _, meaning in ENGLISH_WORDS[:16])
    (root / "input-screenshots" / "english-vocab-ocr-text.txt").write_text(ocr_text, encoding="utf-8")
    extracted_json = [
        {"term": term, "part_of_speech": pos, "meaning": meaning}
        for term, pos, meaning in ENGLISH_WORDS
    ]
    (root / "input-screenshots" / "english-vocab-extracted.json").write_text(
        json.dumps(extracted_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return copied


def write_manifest(root: Path, db_path: Path, screenshots: list[Path]) -> None:
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "user_data_dir": str(root),
        "paper_root": str(root / "papers"),
        "product_screenshot_dir": str(root / "product-screenshots"),
        "english_word_count": len(ENGLISH_WORDS),
        "input_screenshots": [str(path) for path in screenshots],
        "ocr_text": str(root / "input-screenshots" / "english-vocab-ocr-text.txt"),
        "launch_env": {
            "LANGDRILL_USER_DATA_DIR": str(root),
            "LANGDRILL_DB_PATH": str(db_path),
            "LANGDRILL_PAPER_ROOT": str(root / "papers"),
            "LANGDRILL_DEFAULT_PROVIDER": "mimo",
            "LANGDRILL_DEFAULT_MODEL": "mimo-v2.5-pro",
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def summarize_database(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    tables = [
        "study_sessions",
        "messages",
        "questions",
        "attempts",
        "knowledge_items",
        "model_calls",
        "syllabus_sources",
        "exam_assets",
    ]
    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
    conn.close()
    return counts


def main() -> None:
    global ENGLISH_WORDS
    args = parse_args()
    root = Path(args.root)
    ensure_demo_root(root, args.overwrite)
    ENGLISH_WORDS = build_english_words()
    db_path = root / "data" / DataPathService.DB_FILENAME
    seed_reference_data(db_path)
    with transaction(db_path) as conn:
        insert_profile(conn)
        insert_app_settings(conn)
        create_english_sessions(conn)
        create_japanese_sessions(conn)
    screenshots = copy_demo_screenshots(root)
    write_manifest(root, db_path, screenshots)
    counts = summarize_database(db_path)
    print(json.dumps({"root": str(root), "db_path": str(db_path), "counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
