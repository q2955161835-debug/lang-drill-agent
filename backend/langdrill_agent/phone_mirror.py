from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PhoneMirrorService:
    adb_command: str = "adb"
    scrcpy_command: str = "scrcpy"

    def status(self) -> dict[str, Any]:
        adb_path = shutil.which(self.adb_command)
        scrcpy_path = shutil.which(self.scrcpy_command)
        devices: list[dict[str, str]] = []
        error = ""
        if adb_path:
            try:
                output = subprocess.run(
                    [adb_path, "devices"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                devices = self._parse_adb_devices(output.stdout)
                if output.stderr.strip():
                    error = output.stderr.strip()
            except Exception as exc:
                error = str(exc)
        return {
            "adb_available": bool(adb_path),
            "scrcpy_available": bool(scrcpy_path),
            "adb_path": adb_path or "",
            "scrcpy_path": scrcpy_path or "",
            "devices": devices,
            "error": error,
            "recommended_project": {
                "name": "scrcpy",
                "url": "https://github.com/Genymobile/scrcpy",
                "reason": "开源、低延迟、可通过 adb 控制 Android 设备，适合作为手机映像底层。",
            },
        }

    def start(self, device_id: str = "") -> dict[str, Any]:
        scrcpy_path = shutil.which(self.scrcpy_command)
        if not scrcpy_path:
            return {"ok": False, "error": "未检测到 scrcpy，请先安装并加入 PATH。"}
        command = [scrcpy_path]
        if device_id.strip():
            command.extend(["--serial", device_id.strip()])
        try:
            subprocess.Popen(command)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "command": " ".join(command)}

    def _parse_adb_devices(self, output: str) -> list[dict[str, str]]:
        devices: list[dict[str, str]] = []
        for line in output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                devices.append({"id": parts[0], "status": parts[1]})
        return devices
