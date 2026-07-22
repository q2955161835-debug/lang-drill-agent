from collections import deque
from pathlib import Path

from langdrill_agent.creative.pi_adapter import PiAdapter, PiRunRequest
from langdrill_agent.creative.supervisor import (
    PiProcessExited,
    PiProcessSupervisor,
)


class FakeProcess:
    def __init__(self, events):
        self.events = deque(events)
        self.sent: list[dict] = []
        self.started = False
        self.stopped = False

    def start(self, env):
        self.started = True
        self.env = env

    def send(self, command):
        self.sent.append(command)

    def read_event(self, timeout=None):
        event = self.events.popleft()
        if isinstance(event, Exception):
            raise event
        return event

    def is_alive(self):
        return self.started and not self.stopped

    def stop(self):
        self.stopped = True


def test_adapter_restarts_once_after_unexpected_exit(tmp_path: Path) -> None:
    processes = deque(
        [
            FakeProcess([PiProcessExited("first crash")]),
            FakeProcess(
                [
                    {"type": "run.started", "requestId": "run-1"},
                    {"type": "message.delta", "requestId": "run-1", "delta": "done"},
                    {"type": "run.completed", "requestId": "run-1"},
                ]
            ),
        ]
    )
    created: list[FakeProcess] = []

    def factory():
        process = processes.popleft()
        created.append(process)
        return process

    supervisor = PiProcessSupervisor(
        process_factory=factory,
        base_env={"PATH": "safe-path", "SECRET_TOKEN": "do-not-copy"},
    )
    adapter = PiAdapter(supervisor)

    events = list(
        adapter.run(
            PiRunRequest(
                request_id="run-1",
                prompt="perform task",
                provider="openai",
                model="gpt-test",
                thinking_level="medium",
                api_key="request-secret",
            )
        )
    )

    assert len(created) == 2
    assert created[0].env == {"PATH": "safe-path"}
    assert created[1].env == {"PATH": "safe-path"}
    assert any(event["type"] == "runtime.restarted" for event in events)
    assert events[-1]["type"] == "run.completed"
    assert created[1].sent[0]["apiKey"] == "request-secret"
    assert all("request-secret" not in str(event) for event in events)


def test_cancel_targets_active_request(tmp_path: Path) -> None:
    process = FakeProcess([])
    supervisor = PiProcessSupervisor(
        process_factory=lambda: process,
        base_env={"PATH": "safe-path"},
    )
    adapter = PiAdapter(supervisor)
    supervisor.start()

    adapter.cancel("run-1")

    assert process.sent == [
        {
            "type": "cancel",
            "requestId": "cancel-run-1",
            "targetRequestId": "run-1",
        }
    ]
