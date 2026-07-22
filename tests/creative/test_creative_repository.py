from pathlib import Path

import pytest

from langdrill_agent.creative.models import PermissionProfile
from langdrill_agent.creative.repository import (
    CreativeRepository,
    CreativeRuntimeUnavailable,
)
from langdrill_agent.db import connect, init_db


def test_creative_mode_cannot_enable_when_runtime_is_not_ready(tmp_path: Path) -> None:
    db_path = tmp_path / "creative.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = CreativeRepository(conn)
        repo.save_runtime_status(
            state="install_failed",
            version=None,
            error_code="npm_failed",
        )

        with pytest.raises(CreativeRuntimeUnavailable, match="npm_failed"):
            repo.save_settings(
                enabled=True,
                permission_profile=PermissionProfile.FULL_ACCESS,
            )

        saved = repo.get_settings()
        assert saved.enabled is False
        assert saved.permission_profile is PermissionProfile.REQUEST_APPROVAL


def test_full_access_profile_round_trips(tmp_path: Path) -> None:
    db_path = tmp_path / "creative.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = CreativeRepository(conn)
        status = repo.save_runtime_status(state="ready", version="0.80.10")
        saved = repo.save_settings(
            enabled=True,
            permission_profile="full_access",
        )

        assert status.state == "ready"
        assert status.version == "0.80.10"
        assert saved.enabled is True
        assert saved.permission_profile is PermissionProfile.FULL_ACCESS
        assert repo.get_settings() == saved


def test_audit_event_keeps_run_and_session_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "creative.db"
    init_db(db_path)

    with connect(db_path) as conn:
        repo = CreativeRepository(conn)
        event = repo.record_audit_event(
            event_type="settings_saved",
            run_id="run-1",
            session_id="session-1",
            reason_code="creative_mode_enabled",
            payload={"permission_profile": "smart_approval"},
        )

        assert event.run_id == "run-1"
        assert event.session_id == "session-1"
        assert event.payload == {"permission_profile": "smart_approval"}
        assert repo.list_audit_events(limit=10) == [event]
