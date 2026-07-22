import json
from pathlib import Path

from langdrill_agent.creative.extensions import BundledSkillSelector


ROOT = Path(__file__).resolve().parents[2]


def test_complex_coding_intent_loads_superpowers() -> None:
    selected = BundledSkillSelector(
        ROOT / "runtime" / "bundled-skills" / "manifest.json"
    ).select(intent="multi_file_feature")

    assert "superpowers" in {skill.id for skill in selected}
    assert selected[0].skill_ids[:3] == [
        "using-superpowers",
        "brainstorming",
        "writing-plans",
    ]


def test_simple_intent_does_not_load_superpowers() -> None:
    selected = BundledSkillSelector(
        ROOT / "runtime" / "bundled-skills" / "manifest.json"
    ).select(intent="simple_explanation")

    assert selected == []


def test_superpowers_bundle_has_pinned_origin_license_and_file_hashes() -> None:
    manifest_path = (
        ROOT / "runtime" / "bundled-skills" / "superpowers" / "manifest.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["origin_commit"] == "d884ae04edebef577e82ff7c4e143debd0bbec99"
    assert payload["license"] == "MIT"
    assert payload["files"]
    assert all(item["sha256"].startswith("sha256:") for item in payload["files"])
