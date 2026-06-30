from __future__ import annotations

import sqlite3
import logging
import re
from typing import Any

from .algorithm import MasteryInputs, mastery_score, next_review_at
from .context import ContextService
from .models import AuthoredQuestionSet, EvaluationResult, Question, TaskType
from .prompt_engine import PromptAssembler, PromptRegistry
from .providers import ModelProvider
from .services import ProfileService, QuestionService, SessionService
from .utils import dumps, loads, new_id
from .validator import QuestionValidator


logger = logging.getLogger(__name__)


class OrchestratorAgent:
    name = "orchestrator"

    def __init__(self, conn: sqlite3.Connection, provider: ModelProvider):
        self.conn = conn
        self.provider = provider
        self.profile_service = ProfileService(conn)
        self.session_service = SessionService(conn)
        self.question_service = QuestionService(conn)
        self.assembler = PromptAssembler(PromptRegistry(conn))

    def handle_daily_drill(self, session_id: str, content: str) -> dict:
        profile = self.profile_service.get()
        imported_terms = self._import_inline_content(profile.exam_id, content)
        new_content = [content.strip()] if content.strip() else []
        for item in imported_terms:
            summary = f"{item['term']}: {item['meaning']}" if item.get("meaning") else item["term"]
            if summary not in new_content:
                new_content.append(summary)
        plan = {
            "new_content": new_content,
            "review_content": self._select_review_stub(profile.exam_id),
            "target_minutes": profile.daily_minutes,
            "status": "formal_question_set_ready",
            "algorithm": "formal_question_set_v1_mastery_score",
        }
        self.conn.execute(
            """
            UPDATE study_sessions
            SET daily_plan_json=?, status='active', title=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (dumps(plan), (content.strip() or "日常学习")[:18], session_id),
        )

        pack = self.assembler.assemble(
            task_type="daily_drill",
            exam_id=profile.exam_id,
            persona=profile.persona if profile.persona != "custom" else "professional",
            context_pack={
                "task_type": TaskType.daily_drill.value,
                "profile": profile.model_dump(exclude={"global_user_prompt"}),
                "daily_plan": plan,
            },
            user_content=content,
            allow_global_user_prompt=False,
        )
        result = self.provider.complete(pack)
        self._record_model_call("daily_drill", result, [m["id"] for m in pack.system_modules])
        return plan

    def _import_inline_content(self, exam_id: str, content: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or len(line) > 120:
                continue
            term = ""
            reading = ""
            meaning = ""
            notes = ""
            if "|" in line:
                parts = [part.strip() for part in line.split("|")]
                term = parts[0] if parts else ""
                reading = parts[1] if len(parts) > 1 else ""
                meaning = parts[2] if len(parts) > 2 else ""
                notes = parts[4] if len(parts) > 4 else ""
            elif ":" in line or "：" in line:
                pieces = re.split(r"[:：]", line, maxsplit=1)
                term = pieces[0].strip()
                meaning = pieces[1].strip() if len(pieces) > 1 else ""
            if not term or not meaning:
                continue
            existing = self.conn.execute(
                """
                SELECT id FROM knowledge_items
                WHERE term=? AND exam_id=? AND source_scope='chat_input'
                LIMIT 1
                """,
                (term, exam_id),
            ).fetchone()
            if existing:
                self.conn.execute(
                    """
                    UPDATE knowledge_items
                    SET reading=?, meaning=?, notes=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (reading, meaning, notes, existing["id"]),
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO knowledge_items
                    (id, kind, term, reading, meaning, notes, exam_id, source_scope, mastery_score)
                    VALUES (?, 'word', ?, ?, ?, ?, ?, 'chat_input', 0.2)
                    """,
                    (new_id("kn"), term, reading, meaning, notes, exam_id),
                )
            entries.append({"term": term, "meaning": meaning})
        return entries

    def _select_review_stub(self, exam_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT term FROM knowledge_items
            WHERE exam_id IN (?, 'unassigned') AND mastery_score < 0.75
            ORDER BY COALESCE(due_at, created_at) ASC
            LIMIT 5
            """,
            (exam_id,),
        ).fetchall()
        return [row["term"] for row in rows] or ["昨日错题", "低掌握度知识点", "考纲兜底知识点"]

    def _record_model_call(self, task_type: str, result, prompt_modules: list[str]) -> None:
        self.conn.execute(
            """
            INSERT INTO model_calls
            (id, agent_name, task_type, provider_id, model, prompt_modules_json,
             input_tokens, output_tokens, latency_ms, validation_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("call"),
                self.name,
                task_type,
                self.provider.provider_id,
                result.model,
                dumps(prompt_modules),
                result.input_tokens,
                result.output_tokens,
                result.latency_ms,
                "not_required",
            ),
        )


class QuestionAuthorAgent:
    name = "question_author"

    def __init__(self, conn: sqlite3.Connection, provider: ModelProvider):
        self.conn = conn
        self.provider = provider
        self.profile_service = ProfileService(conn)
        self.validator = QuestionValidator()
        self.assembler = PromptAssembler(PromptRegistry(conn))

    def ensure_first_question(self, session_id: str) -> Question:
        active = QuestionService(self.conn).active_question(session_id)
        if active:
            return Question(**active)
        self.ensure_question_set(session_id, "")
        active = QuestionService(self.conn).active_question(session_id)
        if active:
            return Question(**active)
        profile = self.profile_service.get()
        question = self._fallback_question(session_id, profile.exam_name, 1, profile.exam_id)
        self._save_question(question)
        return question

    def ensure_question_set(
        self,
        session_id: str,
        requested_content: str,
        *,
        target_count: int = 8,
    ) -> dict[str, object]:
        question_service = QuestionService(self.conn)
        progress = question_service.question_progress(session_id)
        if progress["ready"]:
            return {"created": 0, "opening_message": "", "progress": progress}

        profile = self.profile_service.get()
        plan_row = self.conn.execute(
            "SELECT daily_plan_json FROM study_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        plan = loads(plan_row["daily_plan_json"], {}) if plan_row else {}
        start_sequence = question_service.next_sequence(session_id)
        content_pool = self._content_pool(profile.exam_id, requested_content, target_count * 3)
        count = self._target_count(profile.daily_minutes, len(content_pool), target_count)
        pack = self.assembler.assemble(
            task_type="question_authoring",
            exam_id=profile.exam_id,
            persona="none",
            context_pack={
                "session_id": session_id,
                "daily_plan": plan,
                "exam_id": profile.exam_id,
                "exam_name": profile.exam_name,
                "start_sequence": start_sequence,
                "target_count": count,
                "content_pool": content_pool,
                "question_flow": "先生成完整题组并持久化，再逐题取出展示。",
                "quality_rules": [
                    "优先覆盖用户输入、截图导入、到期复习和低掌握度知识点。",
                    "题型必须贴近真实考试：题干使用英文完整句、短段落、完形空格或阅读语境问题。",
                    "选择题选项优先使用英文单词、短语、句子或同义改写，禁止只出“选择中文释义 / 最合适理解”的词卡题。",
                    "每题必须考语境理解、搭配、语法或阅读推断，不能只靠中英文同形或裸释义猜答案。",
                    "每题必须有准确答案、讲解和 knowledge_tags。",
                    "选择题选项顺序要分散，不要全是 A。",
                ],
                "output_contract": "AuthoredQuestionSet JSON Schema",
            },
            user_content=(
                f"请一次生成 {count} 道正式刷题题目，题目先入库后再展示。"
                "如果内容池来自截图词表，请自动把这些词改写成考试式语境选择题，"
                "不要要求用户再次确认或再次发送“请出题”。"
                f"用户本轮输入：{requested_content or '继续今日学习'}"
            ),
            output_schema=AuthoredQuestionSet.model_json_schema(),
            allow_global_user_prompt=False,
        )
        result = self.provider.complete(pack)
        authored = self._try_parse_question_set(result.content, session_id, start_sequence, count)
        questions = authored["questions"]
        validation_status = "passed"
        try:
            self._validate_questions(questions)
        except Exception:
            questions = self._fallback_question_set(
                session_id=session_id,
                exam_name=profile.exam_name,
                exam_id=profile.exam_id,
                start_sequence=start_sequence,
                target_count=count,
                content_pool=content_pool,
            )
            validation_status = "fallback_after_validation_failure"
        if len(questions) < max(2, min(count, 4)):
            questions = self._fallback_question_set(
                session_id=session_id,
                exam_name=profile.exam_name,
                exam_id=profile.exam_id,
                start_sequence=start_sequence,
                target_count=count,
                content_pool=content_pool,
            )
            validation_status = "fallback_after_short_set"
        question_service.save_questions(questions)
        self._record_model_call(result, [m["id"] for m in pack.system_modules], validation_status)
        return {
            "created": len(questions),
            "opening_message": authored["opening_message"],
            "progress": question_service.question_progress(session_id),
        }

    def _target_count(self, daily_minutes: int, pool_size: int, default_count: int) -> int:
        minute_based = max(6, min(16, daily_minutes // 4 or default_count))
        pressure_based = max(default_count, min(18, pool_size // 2 if pool_size else default_count))
        return max(4, min(24, max(minute_based, pressure_based)))

    def _content_pool(self, exam_id: str, requested_content: str, limit: int) -> list[dict[str, object]]:
        explicit_pool = self._explicit_content_pool(requested_content)
        if explicit_pool and "截图导入词表" in requested_content:
            return explicit_pool[:limit]
        rows = self.conn.execute(
            """
            SELECT id, kind, term, reading, meaning, notes, source_scope, mastery_score, due_at
            FROM knowledge_items
            WHERE exam_id IN (?, 'unassigned')
            ORDER BY
              CASE WHEN due_at IS NOT NULL AND due_at<>'' AND due_at<=CURRENT_TIMESTAMP THEN 0 ELSE 1 END,
              mastery_score ASC,
              updated_at ASC
            LIMIT ?
            """,
            (exam_id, limit),
        ).fetchall()
        seen_terms = {str(item.get("term") or "").lower() for item in explicit_pool}
        pool = [*explicit_pool]
        pool.extend(dict(row) for row in rows if str(row["term"] or "").lower() not in seen_terms)
        pool = pool[:limit]
        text = requested_content.strip()
        if text and not pool:
            pool.append(
                {
                    "id": "user_content",
                    "kind": "text",
                    "term": text[:80],
                    "reading": "",
                    "meaning": text[:160],
                    "notes": "来自用户本轮输入",
                    "source_scope": "chat_input",
                    "mastery_score": 0.2,
                    "due_at": "",
                }
            )
        return pool

    def _explicit_content_pool(self, requested_content: str) -> list[dict[str, object]]:
        pool: list[dict[str, object]] = []
        seen: set[str] = set()
        for line in requested_content.splitlines():
            if ":" not in line:
                continue
            term, meaning = line.split(":", 1)
            clean_term = term.strip().lower()
            clean_meaning = meaning.strip()
            if not re.fullmatch(r"[a-z][a-z'-]{1,40}", clean_term):
                continue
            if clean_term in seen or not clean_meaning:
                continue
            seen.add(clean_term)
            pool.append(
                {
                    "id": f"explicit:{clean_term}",
                    "kind": "word",
                    "term": clean_term,
                    "reading": "",
                    "meaning": clean_meaning,
                    "notes": "来自本轮显式词表",
                    "source_scope": "screenshot_import" if "截图导入词表" in requested_content else "chat_input",
                    "mastery_score": 0.2,
                    "due_at": "",
                }
            )
        return pool

    def _try_parse_question_set(
        self,
        content: str,
        session_id: str,
        start_sequence: int,
        target_count: int,
    ) -> dict[str, object]:
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        raw_json = json_match.group(1) if json_match else content
        parsed = loads(raw_json.strip(), {})
        if isinstance(parsed, list):
            parsed = {"questions": parsed}
        if not isinstance(parsed, dict):
            return {"opening_message": "", "questions": []}
        questions: list[Question] = []
        for offset, item in enumerate(parsed.get("questions", [])[:target_count]):
            if not isinstance(item, dict):
                continue
            question = self._question_from_authored(item, session_id, start_sequence + offset)
            if question:
                questions.append(question)
        return {
            "opening_message": str(parsed.get("opening_message", "") or ""),
            "questions": questions,
        }

    def _question_from_authored(
        self,
        item: dict[str, object],
        session_id: str,
        sequence: int,
    ) -> Question | None:
        options = [str(option).strip() for option in item.get("options", []) or [] if str(option).strip()]
        answer = item.get("answer") if isinstance(item.get("answer"), dict) else {}
        normalized_answer = self._normalize_answer(answer, options)
        if not normalized_answer:
            return None
        try:
            return Question(
                id=new_id("q"),
                session_id=session_id,
                sequence=sequence,
                type=str(item.get("type") or "multiple_choice"),
                prompt=str(item.get("prompt") or "").strip(),
                options=options,
                answer=normalized_answer,
                explanation=str(item.get("explanation") or "").strip(),
                knowledge_tags=[str(tag) for tag in item.get("knowledge_tags", []) or [] if str(tag).strip()],
                difficulty=float(item.get("difficulty") or 0.5),
                source_refs=[ref for ref in item.get("source_refs", []) or [] if isinstance(ref, dict)],
            )
        except Exception:
            return None

    def _authored_from_question(self, question: Question):
        from .models import AuthoredQuestion

        return AuthoredQuestion(
            type=question.type,
            prompt=question.prompt,
            options=question.options,
            answer=question.answer,
            explanation=question.explanation,
            knowledge_tags=question.knowledge_tags,
            difficulty=question.difficulty,
            source_refs=question.source_refs,
        )

    def _normalize_answer(self, answer: dict[str, object], options: list[str]) -> dict[str, str] | None:
        letter = str(answer.get("letter") or "").strip().upper()
        correct = str(answer.get("correct") or "").strip()
        if letter in {"A", "B", "C", "D"} and options:
            index = ord(letter) - ord("A")
            if index < len(options):
                return {"letter": letter, "correct": options[index]}
        if correct in {"A", "B", "C", "D"} and options:
            index = ord(correct) - ord("A")
            if index < len(options):
                return {"letter": correct, "correct": options[index]}
        if correct and options and correct in options:
            return {"letter": chr(ord("A") + options.index(correct)), "correct": correct}
        if correct and not options:
            return {"correct": correct}
        return None

    def _validate_questions(self, questions: list[Question]) -> None:
        if not questions:
            raise ValueError("题组为空")
        letters: list[str] = []
        for question in questions:
            self.validator.validate(question)
            self._validate_exam_style(question)
            letter = str(question.answer.get("letter", "")).upper()
            if letter:
                letters.append(letter)
        if len(letters) >= 4 and len(set(letters)) == 1:
            raise ValueError("整套题答案选项过度集中")

    def _validate_exam_style(self, question: Question) -> None:
        if question.type not in {"multiple_choice", "cloze"}:
            return
        prompt = question.prompt.strip()
        prompt_lower = prompt.lower()
        card_patterns = [
            "最合适的理解",
            "最贴近的中文释义",
            "选择中文释义",
            "根据导入的单词列表",
        ]
        if any(pattern in prompt for pattern in card_patterns):
            raise ValueError("题目像词卡释义题，不符合考试式语境题")
        has_exam_context = (
            "____" in prompt
            or "blank" in prompt_lower
            or "sentence" in prompt_lower
            or "passage" in prompt_lower
            or "which" in prompt_lower
        )
        if not has_exam_context:
            raise ValueError("题干缺少明确语境或空缺")

    def _fallback_question_set(
        self,
        *,
        session_id: str,
        exam_name: str,
        exam_id: str,
        start_sequence: int,
        target_count: int,
        content_pool: list[dict[str, object]],
    ) -> list[Question]:
        terms = [item for item in content_pool if str(item.get("term") or "").strip()]
        if not terms:
            terms = [
                {"term": "affect", "meaning": "影响", "source_scope": "generated"},
                {"term": "effect", "meaning": "结果；效果", "source_scope": "generated"},
                {"term": "context", "meaning": "语境", "source_scope": "generated"},
                {"term": "evidence", "meaning": "证据", "source_scope": "generated"},
                {"term": "infer", "meaning": "推断", "source_scope": "generated"},
                {"term": "contrast", "meaning": "对比", "source_scope": "generated"},
                {"term": "summarize", "meaning": "概括", "source_scope": "generated"},
                {"term": "accurate", "meaning": "准确的", "source_scope": "generated"},
            ]
        questions: list[Question] = []
        for offset in range(max(4, min(target_count, len(terms) or target_count))):
            item = terms[offset % len(terms)]
            sequence = start_sequence + offset
            term = str(item.get("term") or f"item-{sequence}").strip()
            meaning = str(item.get("meaning") or "该知识点的核心含义").strip()
            questions.append(
                self._fallback_question_for_term(
                    session_id,
                    exam_id,
                    sequence,
                    term,
                    meaning,
                    terms,
                    source_scope=str(item.get("source_scope") or ""),
                )
            )
        return questions

    def _fallback_question_for_term(
        self,
        session_id: str,
        exam_id: str,
        sequence: int,
        term: str,
        meaning: str,
        terms: list[dict[str, object]],
        *,
        source_scope: str = "",
    ) -> Question:
        distractors = [
            str(item.get("term") or "").strip().lower()
            for item in terms
            if str(item.get("term") or "").strip() != term and str(item.get("meaning") or "").strip()
        ]
        generic = ["context", "evidence", "method", "result"]
        options = [term.lower(), *distractors, *generic]
        deduped = []
        for option in options:
            if option and option not in deduped:
                deduped.append(option)
        option_count = 4 if len(deduped) >= 4 else max(2, len(deduped))
        correct_index = (sequence - 1) % option_count
        selected = deduped[:option_count]
        correct = selected.pop(0)
        selected.insert(correct_index, correct)
        letter = chr(ord("A") + correct_index)
        sentence = self._fallback_context_sentence(term.lower(), meaning)
        source_type = "user_import" if source_scope == "screenshot_import" else "generated"
        return Question(
            id=new_id("q"),
            session_id=session_id,
            sequence=sequence,
            type="cloze",
            prompt=(
                f"第 {sequence} 题\n"
                f"Choose the best word to complete the sentence.\n\n{sentence}"
            ),
            options=selected,
            answer={"correct": correct, "letter": letter},
            explanation=(
                f"`{term}` matches the sentence context. Its imported meaning is: {meaning}. "
                "The other options do not fit the semantic clue in the sentence."
            ),
            knowledge_tags=[f"vocabulary:{term}"],
            difficulty=0.35 + min((sequence % 5) * 0.08, 0.32),
            source_refs=[{"type": source_type, "boundary": "practice_only", "term": term}],
        )

    def _fallback_context_sentence(self, term: str, meaning: str) -> str:
        templates = {
            "collision": "The police report said the ______ on the icy road blocked traffic for two hours.",
            "snowstorm": "Because of the heavy ______, several flights were canceled last night.",
            "collection": "The museum's new ______ includes paintings from the nineteenth century.",
            "dry": "The clothes were still wet, so she left them outside to ______ in the sun.",
            "apply": "Students must ______ for the scholarship before the end of this month.",
            "bull": "The farmer kept the ______ in a separate field for safety.",
            "germ": "Washing your hands often can reduce the spread of ______s.",
            "fork": "He picked up a ______ and began to eat the salad.",
            "mysterious": "The scientist could not explain the ______ signal from the old machine.",
            "pot": "She put the soup into a large ______ and warmed it slowly.",
            "book": "Tourists are advised to ______ hotel rooms before the holiday begins.",
            "chair": "Please take a ______ near the window before the lecture starts.",
            "meal": "Breakfast is the first ______ of the day for many people.",
            "steal": "It is illegal to ______ another person's bicycle.",
            "save": "Using less electricity can help families ______ money.",
            "emerge": "New evidence began to ______ during the investigation.",
            "dish": "This restaurant is famous for a spicy chicken ______.",
            "aunt": "My ______ sent me a birthday card from another city.",
            "dull": "The lecture was so ______ that several students lost attention.",
            "state": "The witness was asked to ______ exactly what he had seen.",
            "champion": "After winning the final match, she became the national ______.",
            "aware": "Drivers should be ______ of children crossing the street.",
            "root": "The strong wind pulled the tree up by the ______.",
            "extreme": "The desert is known for its ______ heat during the day.",
            "skin": "Too much sunlight may damage your ______.",
            "hence": "The road was closed; ______, we had to take another route.",
            "vigorous": "The coach asked the team to do ______ exercise every morning.",
            "waterfall": "The path led us to a beautiful ______ deep in the forest.",
            "fierce": "The two companies are in ______ competition for the same market.",
            "contrary": "His actions were ______ to the advice he had received.",
            "discard": "Please ______ any broken glass into the special bin.",
            "evident": "It was ______ from her smile that she was pleased with the result.",
            "fall": "Temperatures usually ______ quickly after sunset in the mountains.",
            "class": "The teacher asked the whole ______ to hand in their papers.",
            "altogether": "There were thirty students ______ in the language club.",
            "forever": "Some memories seem to stay with us ______.",
            "cultivate": "Good teachers try to ______ students' interest in reading.",
            "material": "The factory needs more raw ______ to continue production.",
            "research": "The team carried out ______ into the causes of air pollution.",
            "course": "She signed up for an English writing ______ this semester.",
            "blood": "Doctors tested his ______ before the operation.",
            "executive": "The company hired a new ______ to manage daily operations.",
            "adequate": "The small room did not provide ______ space for all the students.",
            "process": "Learning a language is a long ______ that requires practice.",
            "bow": "The performer gave a polite ______ after the audience applauded.",
            "laser": "Doctors used a ______ to perform the delicate eye operation.",
            "robe": "The judge entered the room wearing a long black ______.",
            "loyalty": "The old worker was respected for his ______ to the company.",
        }
        if term in templates:
            return templates[term]
        hint = meaning.split("；", 1)[0].split(";", 1)[0].strip() or "the meaning in context"
        return f"In this short passage, the word that best matches the idea of \"{hint}\" is ______."

    def _try_parse_model_output(
        self, content: str, session_id: str, sequence: int
    ) -> Question | None:
        """尝试从模型 JSON 输出解析为 Question，失败返回 None。"""
        from .utils import loads as json_loads

        # 尝试从 markdown 代码块中提取 JSON
        import re

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        raw_json = json_match.group(1) if json_match else content

        parsed = json_loads(raw_json.strip(), None)
        if not isinstance(parsed, dict):
            return None

        try:
            # 补充必要的字段默认值
            parsed.setdefault("id", new_id("q"))
            parsed.setdefault("session_id", session_id)
            parsed.setdefault("sequence", sequence)
            parsed.setdefault("type", "multiple_choice")
            parsed.setdefault("difficulty", 0.5)
            parsed.setdefault("knowledge_tags", [])
            parsed.setdefault("source_refs", [{"type": "generated", "boundary": "practice_only"}])

            # 确保 answer 字段格式正确
            if "answer" not in parsed or not isinstance(parsed["answer"], dict):
                return None

            return Question(**parsed)
        except Exception:
            return None

    def _fallback_question(
        self,
        session_id: str,
        exam_name: str,
        sequence: int = 1,
        exam_id: str = "cet4",
    ) -> Question:
        imported_word = self._first_imported_word(exam_id)
        if imported_word:
            term = imported_word["term"]
            meaning = imported_word["meaning"] or "该单词的截图导入释义"
            terms = [imported_word, *self._term_distractors(exam_id, term)]
            logger.info("using imported vocabulary fallback question", extra={"term": term, "exam_id": exam_id})
            return self._fallback_question_for_term(
                session_id,
                exam_id,
                sequence,
                term,
                meaning,
                terms,
                source_scope="screenshot_import",
            )
        return Question(
            id=new_id("q"),
            session_id=session_id,
            sequence=sequence,
            type="multiple_choice",
            prompt=f"第 {sequence} 题 / 共 5 题\n根据今日学习内容，选择最符合 {exam_name or '目标考试'} 语境的答案：\nWhich sentence uses the word \"affect\" correctly?",
            options=["The new policy may affect student attendance.", "The new policy may effect student attendance.", "The new policy is affect on attendance.", "The policy affected to attendance."],
            answer={"correct": "The new policy may affect student attendance.", "letter": "A"},
            explanation='"Affect" is usually a verb meaning "to influence". In this sentence, the policy may influence attendance, so "affect" is correct.',
            knowledge_tags=["vocabulary:affect-vs-effect", "grammar:verb_usage"],
            difficulty=0.35,
            source_refs=[{"type": "generated", "boundary": "practice_only"}],
        )

    def _first_imported_word(self, exam_id: str) -> dict[str, str] | None:
        row = self.conn.execute(
            """
            SELECT term, meaning
            FROM knowledge_items
            WHERE exam_id=? AND source_scope='screenshot_import'
            ORDER BY mastery_score ASC, updated_at ASC
            LIMIT 1
            """,
            (exam_id,),
        ).fetchone()
        return dict(row) if row else None

    def _term_distractors(self, exam_id: str, correct_term: str) -> list[dict[str, str]]:
        rows = self.conn.execute(
            """
            SELECT term, meaning, source_scope
            FROM knowledge_items
            WHERE exam_id=? AND term<>? AND meaning<>''
            ORDER BY updated_at ASC
            LIMIT 3
            """,
            (exam_id, correct_term),
        ).fetchall()
        return [dict(row) for row in rows]

    def _save_question(self, question: Question) -> None:
        QuestionService(self.conn).save_question(question)

    def _question_from_row(self, row: sqlite3.Row) -> Question:
        from .utils import loads

        return Question(
            id=row["id"],
            session_id=row["session_id"],
            sequence=row["sequence"],
            type=row["type"],
            prompt=row["prompt"],
            options=loads(row["options_json"], []),
            answer=loads(row["answer_json"], {}),
            explanation=row["explanation"],
            knowledge_tags=loads(row["knowledge_tags_json"], []),
            difficulty=row["difficulty"],
            source_refs=loads(row["source_refs_json"], []),
        )

    def _record_model_call(self, result, prompt_modules: list[str], validation_status: str) -> None:
        self.conn.execute(
            """
            INSERT INTO model_calls
            (id, agent_name, task_type, provider_id, model, prompt_modules_json,
             input_tokens, output_tokens, latency_ms, validation_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("call"),
                self.name,
                "question_authoring",
                self.provider.provider_id,
                result.model,
                dumps(prompt_modules),
                result.input_tokens,
                result.output_tokens,
                result.latency_ms,
                validation_status,
            ),
        )


class EvaluatorTutorAgent:
    name = "evaluator_tutor"

    def __init__(self, conn: sqlite3.Connection, provider: ModelProvider):
        self.conn = conn
        self.provider = provider
        self.assembler = PromptAssembler(PromptRegistry(conn))

    def evaluate(
        self,
        session_id: str,
        question_payload: dict,
        user_answer: str,
        extra_prompt: str = "",
    ) -> EvaluationResult:
        correct = question_payload["answer"].get("correct")
        letter = question_payload["answer"].get("letter")
        normalized = user_answer.strip().upper()
        is_correct = normalized == str(letter).upper() or user_answer.strip() == str(correct).strip()
        score = mastery_score(
            MasteryInputs(
                correct_rate=1.0 if is_correct else 0.0,
                days_since_last_attempt=0,
                difficulty=float(question_payload.get("difficulty", 0.5)),
                answered_after_hint=False,
                answered_in_integrated_item=False,
                wrong_repeat_count=0 if is_correct else 1,
            )
        )
        feedback = (
            f"判断：{'正确' if is_correct else '不正确'}。\n\n"
            f"正确答案：{letter or ''} {correct}\n\n"
            f"讲解：{question_payload['explanation']}\n\n"
            f"知识点：{', '.join(question_payload.get('knowledge_tags', []))}"
        )
        try:
            feedback = self._feedback_with_model(
                session_id=session_id,
                question_payload=question_payload,
                user_answer=user_answer,
                is_correct=is_correct,
                base_feedback=feedback,
                extra_prompt=extra_prompt.strip(),
            )
        except RuntimeError:
            logger.warning("model request failed during answer feedback, using base feedback", exc_info=True)
        attempt_id = new_id("att")
        self.conn.execute(
            """
            INSERT INTO attempts
            (id, question_id, session_id, user_answer, is_correct, feedback, mastery_delta)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                question_payload["id"],
                session_id,
                user_answer,
                1 if is_correct else 0,
                feedback,
                score - 0.5,
            ),
        )
        QuestionService(self.conn).mark_answered(question_payload["id"])
        self.conn.execute(
            """
            INSERT INTO mastery_events (id, question_id, attempt_id, event_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                new_id("mev"),
                question_payload["id"],
                attempt_id,
                dumps({"score_after": score, "created_from": "evaluator_tutor"}),
            ),
        )
        self._update_knowledge_mastery(question_payload, score)
        return EvaluationResult(
            is_correct=is_correct,
            feedback=feedback,
            mastery_delta=score - 0.5,
            next_action="continue",
        )

    def _update_knowledge_mastery(self, question_payload: dict, score: float) -> None:
        due_at = next_review_at(score).isoformat(timespec="seconds")
        for tag in question_payload.get("knowledge_tags", []):
            term = str(tag).split(":", 1)[-1].strip()
            if not term:
                continue
            rows = self.conn.execute(
                """
                SELECT id FROM knowledge_items
                WHERE term=? OR term=?
                """,
                (term, tag),
            ).fetchall()
            for row in rows:
                self.conn.execute(
                    """
                    UPDATE knowledge_items
                    SET mastery_score=?, due_at=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (score, due_at, row["id"]),
                )

    def _feedback_with_model(
        self,
        *,
        session_id: str,
        question_payload: dict,
        user_answer: str,
        is_correct: bool,
        base_feedback: str,
        extra_prompt: str,
    ) -> str:
        profile = ProfileService(self.conn).get()
        context = ContextService(self.conn).prompt_context(session_id)
        pack = self.assembler.assemble(
            task_type="evaluation",
            exam_id=profile.exam_id,
            persona=profile.persona if profile.persona != "custom" else "professional",
            context_pack={
                "task_type": TaskType.answer_question.value,
                "session_id": session_id,
                "profile": profile.model_dump(),
                "conversation_context": context,
                "question": {
                    "id": question_payload.get("id"),
                    "sequence": question_payload.get("sequence"),
                    "prompt": question_payload.get("prompt"),
                    "options": question_payload.get("options", []),
                    "answer": question_payload.get("answer", {}),
                    "explanation": question_payload.get("explanation", ""),
                    "knowledge_tags": question_payload.get("knowledge_tags", []),
                },
                "programmatic_judgement": "correct" if is_correct else "incorrect",
                "base_feedback": base_feedback,
            },
            user_content=(
                f"用户选择：{user_answer}\n"
                f"用户额外提问：{extra_prompt or '无'}\n\n"
                "请基于程序判定、完整会话上下文、用户学习目标和背景，生成一段定制化判题讲解。"
                "必须保留对错结论和正确答案，不要更改正确答案；如果用户没有额外提问，也要主动解释为什么对/错，"
                "指出最该复习的知识点，并给出下一题前的一句具体提醒。"
            ),
            allow_global_user_prompt=True,
        )
        result = self.provider.complete(pack)
        self.conn.execute(
            """
            INSERT INTO model_calls
            (id, agent_name, task_type, provider_id, model, prompt_modules_json,
             input_tokens, output_tokens, latency_ms, validation_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("call"),
                self.name,
                "answer_evaluation",
                self.provider.provider_id,
                result.model,
                dumps([m["id"] for m in pack.system_modules]),
                result.input_tokens,
                result.output_tokens,
                result.latency_ms,
                "not_required",
            ),
        )
        return self._coerce_model_feedback(result.content, base_feedback)

    @staticmethod
    def _coerce_model_feedback(content: str, base_feedback: str) -> str:
        model_feedback = content.strip()
        if not model_feedback:
            return base_feedback
        if model_feedback.startswith("{"):
            parsed = loads(model_feedback, None)
            if isinstance(parsed, dict):
                message = str(
                    parsed.get("message")
                    or parsed.get("feedback")
                    or parsed.get("explanation")
                    or ""
                ).strip()
                if message:
                    return f"{base_feedback}\n\n模型补充：{message}"
                return base_feedback
        return model_feedback


def token_totals(conn: sqlite3.Connection, session_id: str | None = None) -> dict[str, Any]:
    context = ContextService(conn)
    return {
        **context.global_usage_stats(),
        **context.usage(session_id),
    }
