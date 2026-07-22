from __future__ import annotations

import re
from urllib.parse import urlparse

_DESTRUCTIVE = re.compile(
    r"(?:\brm\b[^\n]*(?:-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)|"
    r"\bremove-item\b[^\n]*(?:-recurse)[^\n]*(?:-force)|"
    r"\bdel\b[^\n]*/s|\brmdir\b[^\n]*/s)",
    re.IGNORECASE,
)
_ROOT_TARGET = re.compile(
    r"(?:^|\s)(?:[a-z]:[\\/]+|/)[\"']?\s*$",
    re.IGNORECASE,
)
_DISK_OPERATION = re.compile(
    r"(?:\bdiskpart\b|\bformat(?:\.com)?\b\s+[a-z]:|"
    r"\bdd\b[^\n]*\bof=/dev/(?:sd[a-z]|nvme\d+n\d+|vd[a-z])|"
    r"\b(?:mkfs|fdisk|parted)\b)",
    re.IGNORECASE,
)
_NETWORK_SENDER = re.compile(
    r"(?:\bcurl\b|\bwget\b|\binvoke-webrequest\b|\binvoke-restmethod\b)",
    re.IGNORECASE,
)
_SECRET_REFERENCE = re.compile(
    r"(?:\$\{?\w*(?:api[_-]?key|token|secret|password|credential)\w*\}?|"
    r"%\w*(?:api[_-]?key|token|secret|password|credential)\w*%)",
    re.IGNORECASE,
)
_POLICY_BYPASS = re.compile(
    r"(?:disable|bypass|stop|turn.?off|remove|delete)[-_\s\w]{0,40}"
    r"(?:policy|audit)|(?:policy|audit)[-_\s\w]{0,40}"
    r"(?:disable|bypass|stop|turn.?off|remove|delete)",
    re.IGNORECASE,
)
_UNRESOLVED_TARGET = re.compile(r"(?:\$\{?\w+\}?|%\w+%)")
_URL = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_EXECUTABLE = re.compile(r"^\s*(?:&\s*)?[\"']?([^\s\"']+)")


def normalize_command(command: str) -> str:
    clean = " ".join(command.split())
    if not clean:
        raise ValueError("bash command is required")
    return clean


def command_executable(command: str) -> str:
    matched = _EXECUTABLE.search(command)
    if not matched:
        raise ValueError("command executable cannot be resolved")
    executable = matched.group(1)
    if executable.casefold() in {"sudo", "cmd", "cmd.exe", "powershell", "powershell.exe"}:
        return executable.casefold()
    return executable.casefold()


def command_network_hosts(command: str) -> list[str]:
    hosts: list[str] = []
    for raw_url in _URL.findall(command):
        host = urlparse(raw_url).hostname
        if host and host.casefold() not in hosts:
            hosts.append(host.casefold())
    return hosts


def catastrophic_reason(command: str) -> str | None:
    clean = normalize_command(command)
    if _DESTRUCTIVE.search(clean) and _ROOT_TARGET.search(clean):
        return "catastrophic_unbounded_delete"
    if _DISK_OPERATION.search(clean):
        return "catastrophic_disk_operation"
    if _NETWORK_SENDER.search(clean) and _SECRET_REFERENCE.search(clean):
        return "catastrophic_credential_exfiltration"
    if _POLICY_BYPASS.search(clean):
        return "catastrophic_policy_bypass"
    if _DESTRUCTIVE.search(clean) and _UNRESOLVED_TARGET.search(clean):
        return "catastrophic_unresolved_destructive_target"
    return None


def is_read_only_command(command: str) -> bool:
    executable = command_executable(command)
    clean = normalize_command(command).casefold()
    if executable in {"pwd", "whoami", "where", "which", "ls", "dir"}:
        return True
    if executable == "git" and re.match(r"^git\s+(?:status|diff|log|show|branch)(?:\s|$)", clean):
        return True
    return False
