from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtensionInstallError(RuntimeError):
    pass


class ExtensionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    version: str = Field(min_length=1, max_length=80)
    origin: str = Field(min_length=1, max_length=500)
    entrypoint: str = Field(min_length=1, max_length=500)
    tools: list[str] = Field(default_factory=list, max_length=100)
    requested_permissions: list[str] = Field(default_factory=list, max_length=100)
    compatibility: str = Field(min_length=1, max_length=200)

    @field_validator("entrypoint")
    @classmethod
    def validate_relative_entrypoint(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("extension entrypoint must be relative and contained")
        return value


class ExtensionInstallResult(BaseModel):
    status: str
    extension_id: str
    version: str
    content_hash: str
    install_path: Path
    manifest: ExtensionManifest


class BundledSkillManifest(BaseModel):
    id: str
    version: str
    path: str
    intents: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    origin: str = ""
    license: str = ""


class BundledSkillSelector:
    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path

    def select(self, *, intent: str) -> list[BundledSkillManifest]:
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        bundles = payload.get("bundles", [])
        return [
            BundledSkillManifest.model_validate(item)
            for item in bundles
            if intent in item.get("intents", [])
        ]


class ExtensionInstaller:
    def __init__(self, install_root: Path) -> None:
        self.install_root = install_root

    def install(
        self,
        source: Path,
        *,
        expected_hash: str,
        permissions: set[str],
    ) -> ExtensionInstallResult:
        source = source.resolve()
        manifest = load_extension_manifest(source)
        actual_hash = directory_hash(source)
        if actual_hash != expected_hash:
            raise ExtensionInstallError(
                f"extension hash mismatch: expected {expected_hash}, got {actual_hash}"
            )
        missing = sorted(set(manifest.requested_permissions) - permissions)
        if missing:
            raise ExtensionInstallError(
                "extension permission was not granted: " + ", ".join(missing)
            )
        entrypoint = (source / manifest.entrypoint).resolve()
        if not entrypoint.is_file() or not _is_within(entrypoint, source):
            raise ExtensionInstallError("extension entrypoint is missing or outside source")

        self.install_root.mkdir(parents=True, exist_ok=True)
        target = self.install_root / f"{manifest.id}-{manifest.version}"
        if target.exists():
            if directory_hash(target) == actual_hash:
                return ExtensionInstallResult(
                    status="installed",
                    extension_id=manifest.id,
                    version=manifest.version,
                    content_hash=actual_hash,
                    install_path=target,
                    manifest=manifest,
                )
            raise ExtensionInstallError("extension target already exists with different content")

        staging = self.install_root / f".{manifest.id}-{manifest.version}.staging-{uuid.uuid4().hex}"
        try:
            shutil.copytree(source, staging)
            if directory_hash(staging) != actual_hash:
                raise ExtensionInstallError("extension staging hash verification failed")
            os.replace(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return ExtensionInstallResult(
            status="installed",
            extension_id=manifest.id,
            version=manifest.version,
            content_hash=actual_hash,
            install_path=target,
            manifest=manifest,
        )


def load_extension_manifest(source: Path) -> ExtensionManifest:
    path = source / "manifest.json"
    if not path.is_file():
        raise ExtensionInstallError("extension manifest is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ExtensionManifest.model_validate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ExtensionInstallError(f"extension manifest is invalid: {exc}") from exc


def directory_hash(root: Path) -> str:
    root = root.resolve()
    if not root.is_dir():
        raise ExtensionInstallError("extension source directory is missing")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ExtensionInstallError("extension source cannot contain symbolic links")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
