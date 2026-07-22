import subprocess
from pathlib import Path

from langdrill_agent.creative.self_upgrade import SelfUpgradeService


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def initialized_repo(path: Path) -> Path:
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Lang Drill Test")
    git(path, "config", "user.email", "langdrill@example.test")
    (path / "app.txt").write_text("stable\n", encoding="utf-8")
    git(path, "add", "app.txt")
    git(path, "commit", "-m", "baseline")
    return path


def test_failed_self_upgrade_returns_to_checkpoint(tmp_path: Path) -> None:
    repo = initialized_repo(tmp_path / "repo")
    checkpoint = git(repo, "rev-parse", "HEAD")

    def apply_change(worktree: Path, _change_set: str) -> None:
        (worktree / "app.txt").write_text("broken\n", encoding="utf-8")
        (worktree / "new-file.txt").write_text("temporary\n", encoding="utf-8")

    service = SelfUpgradeService(
        repo,
        staging_root=tmp_path / "upgrade-worktrees",
        apply_change=apply_change,
        verify_change=lambda _worktree: False,
    )

    result = service.apply_and_verify(change_set="break tests")

    assert result.status == "rolled_back"
    assert result.checkpoint_commit == checkpoint
    assert service.git.head() == checkpoint
    assert (repo / "app.txt").read_text(encoding="utf-8") == "stable\n"
    assert not result.worktree_path.exists()


def test_successful_self_upgrade_stays_isolated_for_review(tmp_path: Path) -> None:
    repo = initialized_repo(tmp_path / "repo")

    def apply_change(worktree: Path, _change_set: str) -> None:
        (worktree / "app.txt").write_text("improved\n", encoding="utf-8")

    service = SelfUpgradeService(
        repo,
        staging_root=tmp_path / "upgrade-worktrees",
        apply_change=apply_change,
        verify_change=lambda worktree: (
            worktree.joinpath("app.txt").read_text(encoding="utf-8") == "improved\n"
        ),
    )

    result = service.apply_and_verify(change_set="improve app")

    assert result.status == "verified"
    assert result.worktree_path.is_dir()
    assert (repo / "app.txt").read_text(encoding="utf-8") == "stable\n"
    assert result.branch.startswith("agent/self-upgrade-")
