from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from langdrill_agent.services import ModelConfigService


def _load_smoke_module():
    smoke_path = Path(__file__).with_name("full_chain_smoke.py")
    spec = importlib.util.spec_from_file_location("full_chain_smoke_for_test", smoke_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_chain_smoke_isolates_env_writes(tmp_path: Path, monkeypatch) -> None:
    real_project = tmp_path / "real-project"
    real_project.mkdir()
    real_env = real_project / ".env"
    real_env.write_text("LANGDRILL_DEFAULT_PROVIDER=mimo\n", encoding="utf-8")

    smoke_runtime = tmp_path / "smoke-runtime"
    monkeypatch.setenv("LANGDRILL_SMOKE_RUNTIME", str(smoke_runtime))
    monkeypatch.setenv("LANGDRILL_PROVIDER_API_KEY_MIMO", "real-key-should-not-leak")
    monkeypatch.delenv("LANGDRILL_SMOKE_ALLOW_REAL_ENV", raising=False)

    smoke = _load_smoke_module()
    smoke.config_module.PROJECT_ROOT = real_project
    smoke.services_module.PROJECT_ROOT = real_project
    runtime = smoke.isolate_smoke_runtime()

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE app_settings (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    ModelConfigService(conn).save("mimo", "https://api.xiaomimimo.com/anthropic", "mimo-v2.5-pro", "")

    isolated_env = runtime["project_root"] / ".env"
    assert isolated_env.exists()
    assert "LANGDRILL_DEFAULT_PROVIDER=mimo" in isolated_env.read_text(encoding="utf-8")
    assert real_env.read_text(encoding="utf-8") == "LANGDRILL_DEFAULT_PROVIDER=mimo\n"
    assert "LANGDRILL_PROVIDER_API_KEY_MIMO" not in __import__("os").environ

