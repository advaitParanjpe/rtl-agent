"""Real Icarus-backed pilot for the Manual Counterfactual Intervention Runner.

It builds a small target Git repository from the checked-in counterfactual AXI
fixture, generates a genuine baseline failure-intelligence run from the seeded
backpressure failure (the payload is corrupted to x under backpressure), and
then runs one manual intervention — a unified diff that removes the corrupting
assignment — through the real ``run-counterfactual`` flow. The intervention is
applied in an isolated Git worktree, the simulator reruns via the configured
command, and the existing pipeline analyzes the result.

Assertions: the original source repository stays byte-for-byte unchanged (and on
the same commit), the seeded failure is removed, the experiment is classified
``failure_removed``, all intermediate evidence is preserved, the worktree is
cleaned up, and the report makes no unsupported causal claim.

Gated: when Icarus Verilog is unavailable the check skips cleanly and returns
success, so the default validation suite stays hermetic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _example_check import ROOT, run_cli

FIXTURE = ROOT / "examples" / "counterfactual-axi"
PATCH = FIXTURE / "interventions" / "remove-fault.diff"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("counterfactual pilot check skipped (iverilog/vvp not available)")
        return 0

    with tempfile.TemporaryDirectory(prefix="rtl-agent-counterfactual-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_target_repo(workspace)
        before_head, before_hashes = _repo_snapshot(repo)

        baseline_dir = _build_baseline(iverilog, vvp, workspace, repo)

        experiment_dir = workspace / "experiment"
        summary = run_cli(
            [
                "run-counterfactual",
                "--baseline-run",
                str(baseline_dir),
                "--repo",
                str(repo),
                "--config",
                str(repo / "rtl-agent.yaml"),
                "--command",
                "seeded-failure",
                "--patch",
                str(PATCH),
                "--allowed-file",
                "rtl/axi_pipe.sv",
                "--output-run",
                str(experiment_dir),
                "--description",
                "remove the corrupting backpressure assignment",
            ]
        )

        assert summary["outcome"] == "failure_removed", summary
        assert summary["intervention_applied"] is True
        assert summary["command_status"] == "passed"

        _check_report(experiment_dir)
        _check_repo_unchanged(repo, before_head, before_hashes)
        _check_worktree_cleaned(experiment_dir)

    print("counterfactual pilot check passed")
    return 0


def _build_target_repo(workspace: Path) -> Path:
    repo = workspace / "target"
    for sub in ("rtl", "tb", "sim"):
        shutil.copytree(FIXTURE / sub, repo / sub)
    shutil.copyfile(FIXTURE / "rtl-agent.yaml", repo / "rtl-agent.yaml")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=fixture@local", "-c", "user.name=fixture", "commit", "-qm", "seed")
    return repo


def _build_baseline(iverilog: str, vvp: str, workspace: Path, repo: Path) -> Path:
    """Generate a genuine baseline failure-intelligence run from the seeded fault."""

    failing_vcd = workspace / "baseline-failing.vcd"
    passing_vcd = workspace / "baseline-passing.vcd"
    _compile_and_run(iverilog, vvp, repo, workspace, failing_vcd, inject_fault=True)
    _compile_and_run(iverilog, vvp, repo, workspace, passing_vcd, inject_fault=False)

    baseline_dir = workspace / "baseline"
    summary = run_cli(
        [
            "run-failure-intelligence",
            "--failing-vcd",
            str(failing_vcd),
            "--passing-vcd",
            str(passing_vcd),
            "--repo",
            str(repo / "rtl"),
            "--failure-time",
            "45",
            "--before",
            "20",
            "--after",
            "20",
            "--run-root",
            str(baseline_dir.parent),
            "--run-id",
            baseline_dir.name,
        ]
    )
    assert summary["status"] == "completed", summary
    return baseline_dir


def _compile_and_run(
    iverilog: str, vvp: str, repo: Path, workspace: Path, vcd: Path, *, inject_fault: bool
) -> None:
    binary = workspace / (vcd.stem + ".vvp")
    args = [iverilog, "-g2012"]
    if inject_fault:
        args.append("-DINJECT_FAULT")
    args.extend(["-o", str(binary), "rtl/axi_pipe.sv", "tb/axi_pipe_tb.sv"])
    _run(args, cwd=repo)
    # The faulted build terminates non-zero ($fatal) after dumping the full VCD,
    # so only require that the waveform was produced, not a zero exit.
    subprocess.run(
        [vvp, str(binary), f"+vcd={vcd}"],
        cwd=repo,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert vcd.exists(), vcd


def _check_report(experiment_dir: Path) -> None:
    report = json.loads((experiment_dir / "experiment-report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "failure_removed"
    assert report["intervention"]["kind"] == "patch"
    assert report["intervention"]["applied"] is True
    assert report["intervention"]["target_files"] == ["rtl/axi_pipe.sv"]
    assert report["baseline_failure"]["divergence_present"] is True
    assert report["intervention_failure"]["divergence_present"] is False
    assert report["baseline"]["valid"] is True
    assert report["baseline"]["manifest_sha256"]
    # Intermediate evidence is preserved.
    roles = {artifact["role"] for artifact in report["generated_artifacts"]}
    assert {"command_stdout", "intervention_waveform", "intervention_failure_report"} <= roles
    for artifact in report["generated_artifacts"]:
        assert (experiment_dir / artifact["relative_path"]).exists()
    assert (experiment_dir / "intervention" / "intervention.patch").exists()
    # No unsupported causal claim; the non-causality disclaimer is present.
    assert "does not establish causality" in report["disclaimer"]
    blob = json.dumps(report).lower()
    assert "root cause of" not in blob
    assert "caused by" not in blob
    markdown = (experiment_dir / "experiment-report.md").read_text(encoding="utf-8")
    assert "does not establish causality" in markdown


def _check_repo_unchanged(repo: Path, before_head: str, before_hashes: dict[str, str]) -> None:
    after_head, after_hashes = _repo_snapshot(repo)
    assert after_head == before_head, "baseline repository commit changed"
    assert after_hashes == before_hashes, "baseline repository files changed"
    # No stray commits, branches, or remotes were created.
    assert _git(repo, "remote").strip() == ""


def _check_worktree_cleaned(experiment_dir: Path) -> None:
    assert not (experiment_dir / "worktrees" / "intervention").exists()


def _repo_snapshot(repo: Path) -> tuple[str, dict[str, str]]:
    head = _git(repo, "rev-parse", "HEAD").strip()
    hashes: dict[str, str] = {}
    for path in sorted(repo.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            import hashlib

            hashes[path.relative_to(repo).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return head, hashes


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(
        args, cwd=cwd, env=os.environ.copy(), capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(
            "\n".join(
                [
                    f"command failed: {' '.join(args)}",
                    f"exit: {result.returncode}",
                    result.stdout[-1500:],
                    result.stderr[-1500:],
                ]
            )
        )


if __name__ == "__main__":
    sys.exit(main())
