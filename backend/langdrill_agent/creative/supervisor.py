from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol


class PiProcessExited(RuntimeError):
    pass


class PiProcess(Protocol):
    def start(self, env: Mapping[str, str]) -> None: ...
    def send(self, command: dict[str, Any]) -> None: ...
    def read_event(self, timeout: float | None = None) -> dict[str, Any]: ...
    def is_alive(self) -> bool: ...
    def stop(self) -> None: ...


_ALLOWED_ENV_KEYS = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "LANG",
        "LC_ALL",
    }
)


class PiProcessSupervisor:
    def __init__(
        self,
        *,
        process_factory: Callable[[], PiProcess],
        base_env: Mapping[str, str] | None = None,
    ) -> None:
        self.process_factory = process_factory
        self.base_env = dict(base_env or os.environ)
        self._process: PiProcess | None = None

    @property
    def process(self) -> PiProcess:
        if self._process is None or not self._process.is_alive():
            raise PiProcessExited("Pi bridge process is not running")
        return self._process

    def start(self) -> PiProcess:
        if self._process is not None and self._process.is_alive():
            return self._process
        process = self.process_factory()
        process.start(self._minimal_env())
        self._process = process
        return process

    def restart(self) -> PiProcess:
        if self._process is not None:
            self._process.stop()
        self._process = None
        return self.start()

    def stop(self) -> None:
        if self._process is not None:
            self._process.stop()
        self._process = None

    def send(self, command: dict[str, Any]) -> None:
        self.process.send(command)

    def read_event(self, timeout: float | None = None) -> dict[str, Any]:
        return self.process.read_event(timeout)

    def health(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def _minimal_env(self) -> dict[str, str]:
        return {
            key: value
            for key, value in self.base_env.items()
            if key.upper() in _ALLOWED_ENV_KEYS
        }


class SubprocessJsonlProcess:
    def __init__(
        self,
        *,
        node_path: str,
        entrypoint: Path,
        cwd: Path,
    ) -> None:
        self.node_path = node_path
        self.entrypoint = entrypoint
        self.cwd = cwd
        self._process: subprocess.Popen[bytes] | None = None
        self._events: queue.Queue[dict[str, Any] | Exception] = queue.Queue()

    def start(self, env: Mapping[str, str]) -> None:
        if not self.entrypoint.is_file():
            raise PiProcessExited(f"Pi bridge entrypoint is missing: {self.entrypoint}")
        self._process = subprocess.Popen(
            [self.node_path, str(self.entrypoint)],
            cwd=self.cwd,
            env=dict(env),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def send(self, command: dict[str, Any]) -> None:
        process = self._require_process()
        if process.stdin is None or process.poll() is not None:
            raise PiProcessExited("Pi bridge stdin is unavailable")
        payload = (json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            process.stdin.write(payload)
            process.stdin.flush()
        except OSError as exc:
            raise PiProcessExited("Pi bridge write failed") from exc

    def read_event(self, timeout: float | None = None) -> dict[str, Any]:
        try:
            event = self._events.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("Pi bridge event timed out") from exc
        if isinstance(event, Exception):
            raise event
        return event

    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        self._process = None

    def _read_stdout(self) -> None:
        process = self._require_process()
        if process.stdout is None:
            self._events.put(PiProcessExited("Pi bridge stdout is unavailable"))
            return
        buffer = b""
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)
                line = raw_line.removesuffix(b"\r")
                if not line:
                    continue
                try:
                    event = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    self._events.put(PiProcessExited(f"Pi bridge emitted invalid JSON: {exc}"))
                    continue
                if isinstance(event, dict):
                    self._events.put(event)
        self._events.put(PiProcessExited("Pi bridge exited unexpectedly"))

    def _drain_stderr(self) -> None:
        process = self._require_process()
        if process.stderr is None:
            return
        while process.stderr.read(4096):
            pass

    def _require_process(self) -> subprocess.Popen[bytes]:
        if self._process is None:
            raise PiProcessExited("Pi bridge has not started")
        return self._process
