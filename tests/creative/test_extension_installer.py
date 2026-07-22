import json
from pathlib import Path

import pytest

from langdrill_agent.creative.extensions import (
    ExtensionInstallError,
    ExtensionInstaller,
    directory_hash,
)


def make_extension(root: Path, *, requested_permissions: list[str]) -> Path:
    source = root / "source-extension"
    source.mkdir()
    (source / "index.js").write_text("export default {}\n", encoding="utf-8")
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "id": "report-tools",
                "version": "1.0.0",
                "origin": "local-test",
                "entrypoint": "index.js",
                "tools": ["report.generate"],
                "requested_permissions": requested_permissions,
                "compatibility": ">=0.80.10 <0.81.0",
            }
        ),
        encoding="utf-8",
    )
    return source


def test_extension_install_is_atomic_and_hash_verified(tmp_path: Path) -> None:
    source = make_extension(tmp_path, requested_permissions=["workspace.write"])
    installer = ExtensionInstaller(tmp_path / "installed")

    result = installer.install(
        source,
        expected_hash=directory_hash(source),
        permissions={"workspace.write"},
    )

    assert result.status == "installed"
    assert result.install_path.name == "report-tools-1.0.0"
    assert (result.install_path / "index.js").is_file()
    assert not list((tmp_path / "installed").glob("*.staging-*"))


def test_extension_install_rejects_hash_or_permission_without_partial_target(
    tmp_path: Path,
) -> None:
    source = make_extension(
        tmp_path,
        requested_permissions=["workspace.write", "network"],
    )
    installer = ExtensionInstaller(tmp_path / "installed")

    with pytest.raises(ExtensionInstallError, match="permission"):
        installer.install(
            source,
            expected_hash=directory_hash(source),
            permissions={"workspace.write"},
        )
    with pytest.raises(ExtensionInstallError, match="hash"):
        installer.install(
            source,
            expected_hash="sha256:wrong",
            permissions={"workspace.write", "network"},
        )

    assert not (tmp_path / "installed" / "report-tools-1.0.0").exists()
    assert not list((tmp_path / "installed").glob("*.staging-*"))
