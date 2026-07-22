from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel


class GitOperationError(RuntimeError):
    pass


class SelfUpgradeResult(BaseModel):
    status: str
    checkpoint_commit: str
    branch: str
    worktree_path: Path
    verification_passed: bool


class GitClient:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()

    def run(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise GitOperationError(f"git {' '.join(args)} failed: {message}")
        return result.stdout.strip()

    def head(self) -> str:
        return self.run("rev-parse", "HEAD")


class SelfUpgradeService:
    def __init__(
        self,
        repository: Path,
        *,
        staging_root: Path,
        apply_change: Callable[[Path, str], None],
        verify_change: Callable[[Path], bool],
    ) -> None:
        self.repository = repository.resolve()
        self.staging_root = staging_root.resolve()
        self.apply_change = apply_change
        self.verify_change = verify_change
        self.git = GitClient(self.repository)

    def prepare_checkpoint(self) -> tuple[str, str, Path]:
        checkpoint = self.git.head()
        suffix = uuid.uuid4().hex[:12]
        branch = f"agent/self-upgrade-{suffix}"
        worktree = self.staging_root / suffix
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.git.run(
            "worktree",
            "add",
            str(worktree),
            "-b",
            branch,
            checkpoint,
        )
        return checkpoint, branch, worktree

    def apply_and_verify(self, *, change_set: str) -> SelfUpgradeResult:
        checkpoint, branch, worktree = self.prepare_checkpoint()
        try:
            self.apply_change(worktree, change_set)
            passed = bool(self.verify_change(worktree))
        except Exception:
            self._remove_failed_worktree(worktree, branch)
            return SelfUpgradeResult(
                status="rolled_back",
                checkpoint_commit=checkpoint,
                branch=branch,
                worktree_path=worktree,
                verification_passed=False,
            )
        if not passed:
            self._remove_failed_worktree(worktree, branch)
            return SelfUpgradeResult(
                status="rolled_back",
                checkpoint_commit=checkpoint,
                branch=branch,
                worktree_path=worktree,
                verification_passed=False,
            )
        return SelfUpgradeResult(
            status="verified",
            checkpoint_commit=checkpoint,
            branch=branch,
            worktree_path=worktree,
            verification_passed=True,
        )

    def _remove_failed_worktree(self, worktree: Path, branch: str) -> None:
        try:
            self.git.run("worktree", "remove", "--force", str(worktree))
        except GitOperationError:
            shutil.rmtree(worktree, ignore_errors=True)
            self.git.run("worktree", "prune")
        self.git.run("branch", "-D", branch)
