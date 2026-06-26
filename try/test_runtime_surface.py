from __future__ import annotations

from langdrill_agent.api import app


def test_removed_workbench_features_are_not_exposed_as_runtime_api_routes() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/composer/next" not in paths
    assert "/api/anki/status" not in paths
    assert "/api/anki/export" not in paths
