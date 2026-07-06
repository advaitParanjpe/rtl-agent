"""Real Icarus-backed pilot for the Counterexample Stimulus Minimization harness.

It builds a target Git repository from the checked-in counterexample AXI fixture,
generates a genuine baseline failure-intelligence run from the full structured
stimulus (three warmup idles, the send/stall failing core, two cooldown idles),
and runs the real `minimize-stimulus` flow. The minimizer materializes candidate
reduced stimuli in an isolated Git worktree, reruns the configured simulator
command, reuses the existing triage / failure-intelligence / fingerprint
services, and reduces the stimulus while preserving the observed failure family.

Assertions: the minimized stimulus is strictly smaller and still reproduces the
same failure family, the irrelevant idle actions are removed, the source
repository stays byte-for-byte unchanged (same commit), all candidate artifacts
are preserved, and the report makes no unsupported causal claim.

Gated: when Icarus Verilog is unavailable the check skips cleanly.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _example_check import ROOT, run_cli

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_fingerprint import fingerprint_run
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.stimulus import materialize_stimulus, parse_stimulus

FIXTURE = ROOT / "examples" / "counterexample-axi"
STIMULUS = FIXTURE / "failing-stimulus.json"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("counterexample pilot check skipped (iverilog/vvp not available)")
        return 0

    with tempfile.TemporaryDirectory(prefix="rtl-agent-counterexample-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_repo(workspace)
        before_head, before_hashes = _repo_snapshot(repo)

        baseline_dir = _build_baseline(iverilog, vvp, workspace, repo)

        output = workspace / "minimization"
        summary = run_cli(
            [
                "minimize-stimulus",
                "--baseline-run",
                str(baseline_dir),
                "--repo",
                str(repo),
                "--config",
                str(repo / "rtl-agent.yaml"),
                "--command",
                "structured-failure",
                "--stimulus",
                str(STIMULUS),
                "--output",
                str(output),
                "--max-evaluations",
                "40",
                "--timeout",
                "60",
            ]
        )

        assert summary["final_classification"] in {"same_failure_exact", "same_failure_family"}
        assert summary["minimized_item_count"] < summary["original_item_count"]
        _check_report(output)
        _check_repo_unchanged(repo, before_head, before_hashes)

    print("counterexample pilot check passed")
    return 0


def _build_repo(workspace: Path) -> Path:
    repo = workspace / "target"
    for sub in ("rtl", "tb", "sim"):
        shutil.copytree(FIXTURE / sub, repo / sub)
    shutil.copyfile(FIXTURE / "rtl-agent.yaml", repo / "rtl-agent.yaml")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=fixture@local", "-c", "user.name=fixture", "commit", "-qm", "seed")
    return repo


def _build_baseline(iverilog: str, vvp: str, workspace: Path, repo: Path) -> Path:
    stimulus = parse_stimulus(STIMULUS)
    materialize_stimulus(stimulus, repo)
    failing = workspace / "failing.vcd"
    passing = workspace / "passing.vcd"

    _run([iverilog, "-g2012", "-DINJECT_FAULT", "-o", "fail.vvp", *_SOURCES], cwd=repo)
    fault_run = subprocess.run(
        [vvp, "fail.vvp", f"+vcd={failing}", "+stim=sim/stimulus.mem"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"time=(\d+)", fault_run.stdout)
    failure_time = int(match.group(1)) if match else 65
    _run([iverilog, "-g2012", "-o", "pass.vvp", *_SOURCES], cwd=repo)
    subprocess.run(
        [vvp, "pass.vvp", f"+vcd={passing}", "+stim=sim/stimulus.mem"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert failing.exists() and passing.exists()

    store = RunStore(workspace / "baselines", run_id="baseline")
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=failing,
        passing_vcd=passing,
        repository_root=repo / "rtl",
        failure_time=failure_time,
        before=20,
        after=20,
    )
    fingerprint = fingerprint_run(store.run_dir)
    assert not fingerprint.insufficient_evidence, fingerprint.insufficient_evidence
    assert "payload_out" in fingerprint.earliest_divergent_signals

    # Restore the repository to its committed state (drop scratch build artifacts).
    _git(repo, "checkout", "--", "sim/stimulus.mem")
    for name in ("sim/stimulus.json", "fail.vvp", "pass.vvp"):
        (repo / name).unlink(missing_ok=True)
    return store.run_dir


_SOURCES = ["rtl/axi_pipe.sv", "tb/axi_pipe_prog_tb.sv"]


def _check_report(output: Path) -> None:
    report = json.loads((output / "reduction-report.json").read_text(encoding="utf-8"))
    assert report["final_classification"] in {"same_failure_exact", "same_failure_family"}
    assert report["minimized_item_count"] < report["original_item_count"]
    # The failing core is retained; irrelevant idle actions are removed.
    assert "load-packet" in report["retained_item_ids"]
    assert "backpressure" in report["retained_item_ids"]
    assert any(item.startswith("cooldown") for item in report["removed_item_ids"])
    assert report["total_evaluations"] >= 1
    assert (output / "reduction-report.md").exists()
    assert (output / "minimized-stimulus.json").exists()
    # Candidate artifacts are preserved and inspectable.
    assert (output / "candidates").is_dir()
    assert any((output / "candidates").iterdir())
    # No unsupported causal claim.
    assert "does not prove identical root cause" in report["disclaimer"]
    blob = json.dumps(report).lower()
    assert "root cause of" not in blob
    assert "caused by" not in blob


def _check_repo_unchanged(repo: Path, before_head: str, before_hashes: dict[str, str]) -> None:
    after_head, after_hashes = _repo_snapshot(repo)
    assert after_head == before_head, "target repository commit changed"
    assert after_hashes == before_hashes, "target repository files changed"
    assert _git(repo, "remote").strip() == ""


def _repo_snapshot(repo: Path) -> tuple[str, dict[str, str]]:
    head = _git(repo, "rev-parse", "HEAD").strip()
    hashes: dict[str, str] = {}
    for path in sorted(repo.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            hashes[path.relative_to(repo).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return head, hashes


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\n{result.stdout[-1500:]}\n{result.stderr[-1500:]}"
        )


if __name__ == "__main__":
    sys.exit(main())
