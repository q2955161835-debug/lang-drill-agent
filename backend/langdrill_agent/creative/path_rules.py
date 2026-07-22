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
