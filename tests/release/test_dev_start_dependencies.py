from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_START = REPO_ROOT / "scripts" / "dev" / "start-dev.ps1"


def test_dev_start_installs_required_paper_parsing_dependencies() -> None:
    script = DEV_START.read_text(encoding="utf-8")

    assert '"$Root[dev,paper-parsing]"' in script
