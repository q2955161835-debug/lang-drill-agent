from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "desktop" / "build-desktop.ps1"


def _preview_build_command(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD_SCRIPT),
            "-SkipInstall",
            "-PrintBuildCommand",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _preview_payload(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert lines, "构建命令预览没有输出 JSON"
    return json.loads(lines[-1])


def test_local_build_without_private_key_disables_updater_signing() -> None:
    env = os.environ.copy()
    env.pop("TAURI_SIGNING_PRIVATE_KEY", None)
    env.pop("TAURI_SIGNING_PRIVATE_KEY_PASSWORD", None)

    payload = _preview_payload(_preview_build_command(env))

    assert payload["signing_key_configured"] is False
    assert payload["arguments"][-1] == "--no-sign"


def test_release_build_with_private_key_keeps_updater_signing_enabled() -> None:
    env = os.environ.copy()
    secret = "test-private-key-must-not-appear"
    env["TAURI_SIGNING_PRIVATE_KEY"] = secret
    env["TAURI_SIGNING_PRIVATE_KEY_PASSWORD"] = "test-password-must-not-appear"

    result = _preview_build_command(env)
    payload = _preview_payload(result)

    assert payload["signing_key_configured"] is True
    assert "--no-sign" not in payload["arguments"]
    assert secret not in result.stdout
    assert secret not in result.stderr
