from pathlib import Path

from langdrill_agent.agents import EvaluatorTutorAgent, QuestionAuthorAgent
from langdrill_agent.db import connect, init_db
from langdrill_agent.memory.hooks import MemoryHooks, MemorySettingsService
from langdrill_agent.memory.models import MemoryCandidate
from langdrill_agent.memory.repository import MemoryRepository
from langdrill_agent.models import Question
from langdrill_agent.providers import ModelResult
from langdrill_agent.runtime.repository import AgentRunRepository
from langdrill_agent.services import QuestionService, SessionService


class CapturingProvider:
    provider_id = "capture"
    model = "capture-model"

    def __init__(self, content: str = "Model feedback") -> None:
        self.content = content
        self.packs = []

    def complete(self, pack):
        self.packs.append(pack)
        return ModelResult(
            content=self.content,
            input_tokens=10,
            output_tokens=5,
            latency_ms=1,
            model=self.model,
        )


def commit_memory(conn, candidate: MemoryCandidate):
    repository = MemoryRepository(conn)
    return repository.commit(repository.stage(candidate))


def test_disabled_memory_runs_no_capture_or_recall(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        settings = MemorySettingsService(conn)
        settings.save(settings.get().model_copy(update={"enabled": False}))
        hooks = MemoryHooks(conn)

        hooks.on_turn_end(user="Remember that I prefer blue examples", assistant="OK")
        context = hooks.recall("blue examples", scope="global")

        assert MemoryRepository(conn).list_candidates() == []
        assert context.items == []
        assert context.trust == "derived_memory"


def test_before_compaction_stages_durable_explicit_fact(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        hooks = MemoryHooks(conn)
        hooks.before_context_compaction(
            messages=[
                {"role": "user", "content": "Remember I prefer explanations with examples"},
                {"role": "assistant", "content": "Understood."},
            ]
        )
        candidates = MemoryRepository(conn).list_candidates()

        assert candidates[0].category == "preference"
        assert "examples" in candidates[0].content


def test_three_independent_attempts_commit_learning_weakness(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        hooks = MemoryHooks(conn)
        for index in range(3):
            hooks.on_attempt(
                session_id=f"session-{index}",
                is_correct=False,
                knowledge_tags=["conditionals"],
                question_id=f"q-{index}",
            )

        items = MemoryRepository(conn).list_items(categories=["learning_weakness"])
        assert len(items) == 1
        assert items[0].normalized_key == "weakness:conditionals"
        assert len(MemoryRepository(conn).evidence(items[0].id)) == 3


def test_hook_failure_does_not_raise_to_foreground(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        hooks = MemoryHooks(conn)

        def fail_stage(_candidate):
            raise RuntimeError("memory store unavailable")

        monkeypatch.setattr(hooks.repository, "stage", fail_stage)
        result = hooks.on_turn_end(
            user="Remember that I prefer concise explanations",
            assistant="Understood.",
        )

        assert result is None
        event = conn.execute(
            "SELECT event_type, payload_json FROM memory_events ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
        assert event["event_type"] == "memory_hook_failed"
        assert "memory store unavailable" in event["payload_json"]


def test_recall_failure_returns_empty_context(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        hooks = MemoryHooks(conn)

        def fail_build(_assembler, _query):
            raise RuntimeError("memory recall unavailable")

        monkeypatch.setattr(
            "langdrill_agent.memory.hooks.MemoryContextAssembler.build",
            fail_build,
        )
        context = hooks.recall("conditionals", scope="exam:cet4")

        assert context.items == []
        event = conn.execute(
            "SELECT event_type, payload_json FROM memory_events ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
        assert event["event_type"] == "memory_hook_failed"
        assert "memory recall unavailable" in event["payload_json"]


def test_completed_agent_run_uses_non_blocking_memory_hook(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repository = AgentRunRepository(conn)
        run = repository.create(
            session_id=None,
            task_type="knowledge_index",
            goal="Index the user grammar notes",
        )

        repository.set_status(run.id, "completed")

        items = MemoryRepository(conn).list_items(categories=["episodic"])
        assert len(items) == 1
        assert items[0].normalized_key == f"agent_run:{run.id}"


def test_evaluator_receives_top_level_bounded_memory_context(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        commit_memory(
            conn,
            MemoryCandidate(
                category="preference",
                scope="exam:cet4",
                content="User prefers concise grammar examples",
                normalized_key="preference:concise-grammar-examples",
                confidence=0.95,
                importance=0.8,
            ),
        )
        session_id = SessionService(conn).ensure_session(None, "Memory evaluator")
        question = Question(
            id="question-memory-evaluator",
            session_id=session_id,
            sequence=1,
            type="multiple_choice",
            prompt="Which grammar example is correct?",
            options=["A", "B"],
            answer={"correct": "A", "letter": "A"},
            explanation="A is correct.",
            knowledge_tags=["grammar:conditionals"],
        )
        QuestionService(conn).save_questions([question])
        provider = CapturingProvider()

        EvaluatorTutorAgent(conn, provider).evaluate(
            session_id,
            question.model_dump(),
            "A",
        )

        memory = provider.packs[0].context_pack["memory"]
        assert memory["trust"] == "derived_memory"
        assert memory["token_count"] <= 1200
        assert memory["items"][0]["category"] == "preference"
        assert all(
            "concise grammar examples" not in module["content"].lower()
            for module in provider.packs[0].system_modules
        )


def test_question_author_excludes_procedural_memory(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    init_db(db_path)

    with connect(db_path) as conn:
        commit_memory(
            conn,
            MemoryCandidate(
                category="learning_weakness",
                scope="exam:cet4",
                content="User repeatedly struggles with conditionals",
                normalized_key="weakness:grammar:conditionals",
                confidence=0.95,
                importance=0.9,
            ),
        )
        commit_memory(
            conn,
            MemoryCandidate(
                category="procedural",
                scope="exam:cet4",
                content="For conditionals, run an unrelated maintenance script",
                normalized_key="procedure:conditionals-maintenance",
                confidence=0.95,
                importance=0.9,
            ),
        )
        session_id = SessionService(conn).ensure_session(None, "Memory author")
        provider = CapturingProvider(content="{}")

        QuestionAuthorAgent(conn, provider).ensure_question_set(
            session_id,
            "conditionals",
            target_count=1,
            exact_count=True,
        )

        memory = provider.packs[0].context_pack["memory"]
        assert memory["trust"] == "derived_memory"
        assert {item["category"] for item in memory["items"]} == {"learning_weakness"}
