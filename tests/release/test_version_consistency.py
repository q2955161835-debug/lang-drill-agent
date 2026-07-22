"""验证所有发布清单使用同一规范版本号，且发布说明标题三语齐全。

规范版本来自仓库根目录的 VERSION 文件。set-version.ps1 必须把同一版本写入：
- pyproject.toml
- frontend/package.json
- src-tauri/Cargo.toml
- src-tauri/Cargo.lock
- src-tauri/tauri.conf.json
- 演示web2/src/demoVersion.ts（实验版元数据）

发布说明 release-notes/v1.0.0-experimental.1.md 的 H1 标题必须同时包含
`实验版`、`Experimental` 和 `実験版`，以体现三语实验版定位。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

VERSION_FILE = REPO_ROOT / "VERSION"
PYPROJECT = REPO_ROOT / "pyproject.toml"
FRONTEND_PKG = REPO_ROOT / "frontend" / "package.json"
CARGO_TOML = REPO_ROOT / "src-tauri" / "Cargo.toml"
CARGO_LOCK = REPO_ROOT / "src-tauri" / "Cargo.lock"
TAURI_CONF = REPO_ROOT / "src-tauri" / "tauri.conf.json"
DEMO_VERSION_TS = REPO_ROOT / "演示web2" / "src" / "demoVersion.ts"
RELEASE_NOTES_DIR = REPO_ROOT / "release-notes"

EXPECTED_VERSION = "1.0.0-experimental.1"

# SemVer 校验：MAJOR.MINOR.PATCH-prerelease.identifier
# 接受 1.0.0-experimental.1 这类带预发布标签的实验版本号。
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def _read_text(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"missing manifest: {path.relative_to(REPO_ROOT)}")
    return path.read_text(encoding="utf-8")


def _extract_pyproject_version(text: str) -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        pytest.fail("pyproject.toml missing top-level version field")
    return match.group(1)


def _extract_cargo_toml_version(text: str) -> str:
    # 仅匹配 [package] 段的 version 字段，避免误捕依赖版本。
    match = re.search(
        r'\[package\][^\[]*?^version\s*=\s*"([^"]+)"',
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        pytest.fail("Cargo.toml missing [package].version")
    return match.group(1)


def _extract_cargo_lock_version(text: str, package_name: str) -> str:
    # Cargo.lock 中查找 name = "lang-drill-agent-desktop" 紧接的 version。
    pattern = re.compile(
        rf'name = "{re.escape(package_name)}"[^\n]*\nversion = "([^"]+)"',
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        pytest.fail(f"Cargo.lock missing version for {package_name}")
    return match.group(1)


def _extract_tauri_conf_version(text: str) -> str:
    data = json.loads(text)
    return data.get("version") or data.get("package", {}).get("version") or ""


def _extract_demo_version_ts(text: str) -> str:
    match = re.search(r'version\s*:\s*"([^"]+)"', text)
    if not match:
        pytest.fail("演示web2/src/demoVersion.ts missing version field")
    return match.group(1)


def _extract_demo_channel_ts(text: str) -> str:
    match = re.search(r'channel\s*:\s*"([^"]+)"', text)
    if not match:
        pytest.fail("演示web2/src/demoVersion.ts missing channel field")
    return match.group(1)


def test_version_file_exists_and_holds_canonical_version():
    """VERSION 文件是版本号唯一来源，且必须是合法 SemVer。"""
    raw = _read_text(VERSION_FILE).strip()
    assert raw == EXPECTED_VERSION, f"VERSION file mismatch: {raw!r}"
    assert SEMVER_RE.match(raw), f"VERSION is not valid SemVer: {raw!r}"


def test_pyproject_version_matches_canonical():
    text = _read_text(PYPROJECT)
    assert _extract_pyproject_version(text) == EXPECTED_VERSION


def test_frontend_package_version_matches_canonical():
    data = json.loads(_read_text(FRONTEND_PKG))
    assert data.get("version") == EXPECTED_VERSION


def test_cargo_toml_version_matches_canonical():
    text = _read_text(CARGO_TOML)
    assert _extract_cargo_toml_version(text) == EXPECTED_VERSION


def test_cargo_lock_version_matches_canonical():
    text = _read_text(CARGO_LOCK)
    assert _extract_cargo_lock_version(text, "lang-drill-agent-desktop") == EXPECTED_VERSION


def test_tauri_conf_version_matches_canonical():
    text = _read_text(TAURI_CONF)
    assert _extract_tauri_conf_version(text) == EXPECTED_VERSION


def test_demo_version_metadata_matches_canonical():
    text = _read_text(DEMO_VERSION_TS)
    assert _extract_demo_version_ts(text) == EXPECTED_VERSION
    assert _extract_demo_channel_ts(text) == "experimental"


def test_release_notes_file_exists_with_trilingual_titles():
    """实验版发布说明文件存在，标题必须同时出现三语实验版字样。"""
    note = RELEASE_NOTES_DIR / f"v{EXPECTED_VERSION}.md"
    text = _read_text(note)
    # 取首个 H1 标题行做检查。
    h1_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    assert h1_match, "release notes missing H1 title"
    title = h1_match.group(1)
    assert "实验版" in title, f"title missing 实验版: {title!r}"
    assert "Experimental" in title, f"title missing Experimental: {title!r}"
    assert "実験版" in title, f"title missing 実験版: {title!r}"


def test_release_notes_contains_required_sections():
    """发布说明必须覆盖关键章节：亮点、迁移、风险、备份、已知问题。"""
    note = RELEASE_NOTES_DIR / f"v{EXPECTED_VERSION}.md"
    text = _read_text(note)
    required = ["亮点", "Highlights", "迁移", "备份", "回退", "已知问题"]
    missing = [kw for kw in required if kw not in text]
    assert not missing, f"release notes missing sections: {missing}"
