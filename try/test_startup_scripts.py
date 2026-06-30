from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_start_bat_delegates_to_checked_powershell_launcher() -> None:
    start_bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    launcher = ROOT / "scripts" / "dev" / "start-dev.ps1"

    assert launcher.exists()
    assert "scripts\\dev\\start-dev.ps1" in start_bat
    assert "-ExecutionPolicy Bypass" in start_bat


def test_powershell_launcher_waits_for_http_and_writes_logs() -> None:
    launcher = (ROOT / "scripts" / "dev" / "start-dev.ps1").read_text(encoding="utf-8")

    assert "Wait-LangDrillHttp" in launcher
    assert "Invoke-WebRequest" in launcher
    assert "Start-Process" in launcher
    assert "-RedirectStandardOutput" in launcher
    assert "langdrill-backend.out.log" in launcher
    assert "langdrill-frontend.out.log" in launcher
    assert "LANGDRILL_PROVIDER_BASE_URL=https://api.xiaomimimo.com/anthropic" in launcher


def test_powershell_launcher_writes_env_without_utf8_bom() -> None:
    launcher = (ROOT / "scripts" / "dev" / "start-dev.ps1").read_text(encoding="utf-8")

    assert "UTF8Encoding]::new($false)" in launcher
    assert "[System.IO.File]::WriteAllLines" in launcher
    assert "Set-Content -Path $EnvPath -Encoding UTF8" not in launcher


def test_powershell_launcher_normalizes_existing_api_key_labels() -> None:
    launcher = (ROOT / "scripts" / "dev" / "start-dev.ps1").read_text(encoding="utf-8")

    assert "function Normalize-ApiKeyValue" in launcher
    assert "bearer\\s*[:\\uFF1A]" in launcher
    assert "apikey)\\s*[:\\uFF1A]" in launcher
    assert "[:：]" not in launcher
    assert '$line -notmatch "^\\s*#"' in launcher
    assert "Normalize-ApiKeyValue -Value" in launcher
