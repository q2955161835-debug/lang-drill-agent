from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "runtime" / "pi-runtime-manifest.json"

SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$")


def load_manifest() -> dict:
    assert MANIFEST_PATH.is_file(), f"pi runtime manifest is missing at {MANIFEST_PATH}"
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_has_required_top_level_fields() -> None:
    manifest = load_manifest()
    assert manifest["manifest_version"] == 1
    assert SEMVER_PATTERN.match(manifest["runtime_version"])
    assert isinstance(manifest["platforms"], list) and manifest["platforms"]
    assert isinstance(manifest["arches"], list) and manifest["arches"]


def test_node_version_and_archive_sha256_are_pinned() -> None:
    manifest = load_manifest()
    node = manifest["node"]
    assert SEMVER_PATTERN.match(node["version"])
    downloads = node["downloads"]
    assert "x86_64-windows" in downloads
    entry = downloads["x86_64-windows"]
    assert entry["url"].startswith("https://")
    assert SHA256_PATTERN.match(entry["sha256"]), (
        "node archive sha256 must be pinned with sha256:<hex> format"
    )


def test_pi_version_matches_bridge_package_json() -> None:
    manifest = load_manifest()
    pi = manifest["pi"]
    package_json = json.loads(
        (ROOT / "runtime" / "pi-bridge" / "package.json").read_text(encoding="utf-8")
    )
    expected = package_json["dependencies"]["@earendil-works/pi-coding-agent"]
    assert pi["version"] == expected
    assert pi["package"] == "@earendil-works/pi-coding-agent"


def test_bridge_entrypoint_exists_in_repository() -> None:
    manifest = load_manifest()
    bridge = manifest["bridge"]
    entrypoint = ROOT / bridge["entrypoint"]
    package = ROOT / bridge["package"]
    assert entrypoint.is_file(), f"bridge entrypoint is missing: {entrypoint}"
    assert package.is_file(), f"bridge package.json is missing: {package}"


def test_bundled_skill_manifests_exist_and_hashes_match() -> None:
    manifest = load_manifest()
    skills = manifest["bundled_skills"]
    assert skills, "manifest must declare at least one bundled skill"

    for skill in skills:
        skill_manifest_path = ROOT / skill["manifest_path"]
        assert skill_manifest_path.is_file(), (
            f"bundled skill manifest is missing: {skill_manifest_path}"
        )
        assert skill["origin_commit"], "origin_commit is required"
        assert skill["license"], "license is required"

        payload = json.loads(skill_manifest_path.read_text(encoding="utf-8"))
        assert payload["license"] == skill["license"]
        assert payload["origin_commit"] == skill["origin_commit"]

        skill_root = skill_manifest_path.parent
        for entry in payload["files"]:
            assert SHA256_PATTERN.match(entry["sha256"]), (
                f"skill file sha256 is malformed: {entry}"
            )
            target = skill_root / entry["path"]
            assert target.is_file(), f"skill file is missing: {target}"
            actual = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            assert actual == entry["sha256"], (
                f"skill file hash mismatch for {entry['path']}: "
                f"expected {entry['sha256']}, got {actual}"
            )


def test_supported_platform_and_arch_includes_windows_x86_64() -> None:
    manifest = load_manifest()
    assert "x86_64-windows" in manifest["platforms"]
    assert "x86_64" in manifest["arches"]


@pytest.mark.parametrize(
    "field",
    [
        "manifest_version",
        "runtime_version",
        "node",
        "pi",
        "bridge",
        "platforms",
        "arches",
        "bundled_skills",
    ],
)
def test_manifest_field_present(field: str) -> None:
    manifest = load_manifest()
    assert field in manifest, f"manifest is missing required field: {field}"
