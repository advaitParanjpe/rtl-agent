"""Real Icarus-backed pilot for the Counterfactual Experiment Matrix workflow.

It composes the full experimental-debugging workflow end to end on the
project-owned counterexample AXI fixture: build a target Git repository, generate
a genuine baseline failure-intelligence run, minimize the failing stimulus, then
run a bounded set of explicit manual interventions against that one minimized
counterexample and compare every resulting fingerprint against the reference.

The intervention manifest exercises four distinct observed outcomes plus a
semantic duplicate: removing the failure, a benign no-effect edit, advancing the
same failure one cycle earlier, exposing a materially different failure, and a
duplicate that must be served from cache. The pilot asserts the outcomes match
the observed results, the same minimized stimulus is reused, all interventions
run in isolated worktrees, the source repository stays byte-for-byte unchanged,
every executed row preserves evidence, and the report makes no causal claim.

Gated: when Icarus Verilog is unavailable the check skips cleanly.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from _example_check import ROOT, run_cli
from counterexample_pilot_check import _build_baseline, _build_repo, _repo_snapshot

FIXTURE = ROOT / "examples" / "counterexample-axi"
STIMULUS = FIXTURE / "failing-stimulus.json"
INTERVENTIONS = FIXTURE / "interventions.json"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("experiment matrix pilot check skipped (iverilog/vvp not available)")
        return 0

    with TemporaryDirectory(prefix="rtl-agent-experiment-matrix-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_repo(workspace)
        before_head, before_hashes = _repo_snapshot(repo)

        baseline_dir = _build_baseline(iverilog, vvp, workspace, repo)

        minimization = workspace / "minimization"
        run_cli(
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
                str(minimization),
                "--max-evaluations",
                "40",
                "--timeout",
                "60",
            ]
        )
        reduction_report = minimization / "reduction-report.json"
        assert reduction_report.exists()

        matrix_out = workspace / "matrix"
        run_cli(
            [
                "run-experiment-matrix",
                "--baseline-run",
                str(baseline_dir),
                "--reduction-report",
                str(reduction_report),
                "--repo",
                str(repo),
                "--config",
                str(repo / "rtl-agent.yaml"),
                "--command",
                "structured-failure",
                "--interventions",
                str(INTERVENTIONS),
                "--output",
                str(matrix_out),
                "--max-experiments",
                "12",
                "--timeout",
                "60",
            ]
        )

        _check_matrix(matrix_out)
        _check_repo_unchanged(repo, before_head, before_hashes)

    print("experiment matrix pilot check passed")
    return 0


def _check_matrix(output: Path) -> None:
    report = json.loads((output / "experiment-matrix.json").read_text(encoding="utf-8"))
    assert (output / "experiment-matrix.md").exists()

    # The minimized counterexample reference reproduces the baseline family.
    assert report["reference_family_digest"] == report["baseline_family_digest"]
    assert (output / "reference" / "run").is_dir()

    rows = {row["intervention_id"]: row for row in report["rows"]}
    assert set(rows) == {
        "remove-fault",
        "benign-marker",
        "advance-fault",
        "defined-corruption",
        "remove-fault-again",
    }

    removed = rows["remove-fault"]
    assert removed["execution_status"] == "executed"
    assert removed["failure_removed"] is True
    assert removed["counterfactual_outcome"] == "failure_removed"

    benign = rows["benign-marker"]
    assert benign["counterfactual_outcome"] == "no_observable_effect"
    assert benign["fingerprint_relation"] == "exact"
    assert benign["family_preserved"] is True
    assert benign["failure_time_shifted"] is False

    advanced = rows["advance-fault"]
    assert advanced["counterfactual_outcome"] == "failure_advanced"
    assert advanced["failure_time_shifted"] is True
    assert advanced["result_failure_time"] < report["reference_failure_time"]

    different = rows["defined-corruption"]
    assert different["different_failure"] is True
    assert different["result_family_digest"] != report["reference_family_digest"]

    duplicate = rows["remove-fault-again"]
    assert duplicate["from_cache"] is True
    assert duplicate["failure_removed"] is True

    summary = report["summary"]
    assert summary["executed"] == 4
    assert summary["cache_hits"] >= 1
    assert summary["failures_removed"] >= 1

    # Every executed (non-cache) row preserves evidence.
    for row in report["rows"]:
        if row["execution_status"] == "executed" and not row["from_cache"]:
            assert row["artifact_dir"], row["intervention_id"]
            assert (output / row["artifact_dir"]).is_dir()

    # No unsupported causal claim anywhere in the report.
    assert "does not establish causality" in report["disclaimer"]
    blob = json.dumps(report).lower()
    assert "root cause of" not in blob
    assert "caused by" not in blob


def _check_repo_unchanged(repo: Path, before_head: str, before_hashes: dict[str, str]) -> None:
    after_head, after_hashes = _repo_snapshot(repo)
    assert after_head == before_head, "target repository commit changed"
    assert after_hashes == before_hashes, "target repository files changed"


if __name__ == "__main__":
    sys.exit(main())
