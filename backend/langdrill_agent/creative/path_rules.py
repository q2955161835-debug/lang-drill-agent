from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_PATH_ARGUMENTS = {
    "read": ("path",),
    "write": ("path",),
    "edit": ("path",),
}


def normalize_path(value: str, *, cwd: str) -> str:
    raw = value.strip().strip('"\'')
    if not raw:
        raise ValueError("filesystem target is required")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(cwd) / path
    return str(path.resolve(strict=False))


def tool_path_targets(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    cwd: str,
) -> list[str]:
    keys = _PATH_ARGUMENTS.get(tool_name, ())
    targets: list[str] = []
    for key in keys:
        value = arguments.get(key)
        if not isinstance(value, str):
            raise ValueError(f"{tool_name} requires a string {key}")
        targets.append(normalize_path(value, cwd=cwd))
    return targets


def is_within(path: str, root: str) -> bool:
    normalized_path = os.path.normcase(os.path.abspath(path))
    normalized_root = os.path.normcase(os.path.abspath(root))
    try:
        return os.path.commonpath([normalized_path, normalized_root]) == normalized_root
    except ValueError:
        return False


# 会被当前进程或下一次启动执行的脚本后缀：写入等于取得代码执行。
_EXECUTABLE_SUFFIXES = {".ps1", ".bat", ".cmd", ".sh", ".psm1"}
# 凭据类文件后缀与文件名。
_CREDENTIAL_SUFFIXES = {".pem", ".key", ".pfx", ".p12"}
_CREDENTIAL_NAMES = {"id_rsa", "id_ed25519", "credentials", "secrets.json"}
# 工作区内的敏感目录（相对 workspace_root）。
_SENSITIVE_DIRS = {"scripts", ".git", ".github"}


def sensitive_path_reason(path: str, root: str) -> str | None:
    """返回敏感原因，没有则返回 None。

    `is_within(workspace_root)` 不足以判断安全：仓库根目录里就有开发期 `.env`
    （含 provider API Key 与 MinerU token）、`start.bat` 和 `scripts/dev/*.ps1`。
    这些目标必须走人工确认，而不是被 smart_approval 自动放行。
    """
    target = Path(path)
    name = target.name.casefold()
    suffix = target.suffix.casefold()

    if name == ".env" or name.startswith(".env."):
        return "env_file"
    if suffix in _CREDENTIAL_SUFFIXES or name in _CREDENTIAL_NAMES:
        return "credential_file"
    if suffix in _EXECUTABLE_SUFFIXES:
        return "executable_script"

    try:
        relative = Path(os.path.relpath(os.path.abspath(path), os.path.abspath(root)))
    except ValueError:
        # 跨盘符无法求相对路径；此时按目录规则无从判断，交给调用方的越界逻辑处理。
        return None
    parts = [part.casefold() for part in relative.parts]
    if ".." in parts:
        return None
    if parts and parts[0] in _SENSITIVE_DIRS:
        return f"sensitive_dir:{parts[0]}"
    return None
