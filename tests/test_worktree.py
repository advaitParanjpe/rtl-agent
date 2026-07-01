from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rtl_agent.git import GitWorktreeError, GitWorktreeManager


def test_worktree_plan_is_under_run_dir(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run_dir = tmp_path / "runs" / "run-1"
    repo.mkdir()
    manager = GitWorktreeManager(repo, run_dir)

    plan = manager.plan("wt-1")

    assert plan.worktree_path == (run_dir / "worktrees" / "wt-1").resolve()
    assert plan.git_add_command[:5] == ["git", "-C", str(repo.resolve()), "worktree", "add"]
    assert "--detach" in plan.git_add_command


def test_worktree_rejects_path_escape(tmp_path: Path) -> None:
    manager = GitWorktreeManager(tmp_path / "repo", tmp_path / "runs")

    with pytest.raises(GitWorktreeError, match="invalid worktree name"):
        manager.choose_worktree_path("../escape")


def test_worktree_create_and_remove(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, stdout=subprocess.PIPE)

    manager = GitWorktreeManager(repo, tmp_path / "runs" / "run-1")
    plan = manager.create("wt-1")

    assert (plan.worktree_path / "README.md").exists()
    manager.remove(plan.worktree_path)
    assert not plan.worktree_path.exists()
