from langdrill_agent.db import connect, init_db
from langdrill_agent.runtime.repository import AgentRunRepository


def test_run_repository_round_trip(tmp_path):
    path = tmp_path / "runs.db"

    init_db(path)

    with connect(path) as conn:
        repo = AgentRunRepository(conn)
        run = repo.create(session_id="s1", task_type="knowledge_index", goal="index file")
        repo.append_event(run.id, "progress", {"percent": 25})
        repo.set_status(run.id, "completed")

        assert repo.get(run.id).status == "completed"
        assert repo.events_after(run.id, 0)[0].payload == {"percent": 25}
