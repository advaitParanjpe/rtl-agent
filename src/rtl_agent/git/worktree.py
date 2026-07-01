from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rtl_agent.models import WorktreePlan


class GitWorktreeError(RuntimeError):
    pass


class GitWorktreeManager:
    def __init__(self, source_repo: Path, run_dir: Path) -> None:
        self.source_repo = source_repo.resolve()
        self.run_dir = run_dir.resolve()

    def validate_source_repo(self) -> None:
        if not self.source_repo.exists() or not self.source_repo.is_dir():
            raise GitWorktreeError(f"source repository is not a directory: {self.source_repo}")
        result = subprocess.run(
            ["git", "-C", str(self.source_repo), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            raise GitWorktreeError(f"not a Git repository: {self.source_repo}")
        top = Path(result.stdout.strip()).resolve()
        if top != self.source_repo:
            raise GitWorktreeError(f"source path must be repository root: {self.source_repo}")

    def choose_worktree_path(self, name: str) -> Path:
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            raise GitWorktreeError(f"invalid worktree name: {name!r}")
        path = (self.run_dir / "worktrees" / name).resolve()
        self._assert_safe_worktree_path(path)
        return path

    def plan(self, name: str, ref: str = "HEAD") -> WorktreePlan:
        path = self.choose_worktree_path(name)
        return WorktreePlan(
            source_repo=self.source_repo,
            worktree_path=path,
            git_add_command=[
                "git",
                "-C",
                str(self.source_repo),
                "worktree",
                "add",
                "--detach",
                str(path),
                ref,
            ],
            git_remove_command=[
                "git",
                "-C",
                str(self.source_repo),
                "worktree",
                "remove",
                "--force",
                str(path),
            ],
        )

    def create(self, name: str, ref: str = "HEAD") -> WorktreePlan:
        self.validate_source_repo()
        plan = self.plan(name, ref)
        plan.worktree_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            plan.git_add_command,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            raise GitWorktreeError(result.stderr.strip() or "git worktree add failed")
        return plan

    def remove(self, path: Path) -> None:
        resolved = path.resolve()
        self._assert_safe_worktree_path(resolved)
        if not resolved.exists():
            return
        result = subprocess.run(
            ["git", "-C", str(self.source_repo), "worktree", "remove", "--force", str(resolved)],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            raise GitWorktreeError(result.stderr.strip() or "git worktree remove failed")
        if resolved.exists():
            shutil.rmtree(resolved)

    def _assert_safe_worktree_path(self, path: Path) -> None:
        if path == self.run_dir:
            raise GitWorktreeError("worktree path cannot be the run directory")
        if not path.is_relative_to(self.run_dir):
            raise GitWorktreeError(f"worktree path must be under run directory: {path}")
        if self.source_repo == path or self.source_repo.is_relative_to(path):
            raise GitWorktreeError("worktree path cannot contain source repository")
