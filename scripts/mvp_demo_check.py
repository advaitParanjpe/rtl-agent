"""Real Icarus-backed demonstration of the full evidence-guided counterfactual workflow.

It composes the existing services end to end on the project-owned counterexample
AXI fixture: build a target Git repository, produce a genuine baseline
failure-intelligence run from the failing regression, then run the MVP
demonstration driver, which sequences inspect-run, export-failure-package,
stimulus minimization, intervention-candidate generation, and experiment-matrix
execution into one evidence-qualified summary.

The driver composes existing services only; it applies nothing, and the source
repository stays byte-for-byte unchanged. The check asserts the summary is
coherent (every stage ran, at least one generated experiment removed or changed
the observed failure) and makes no causal claim.

Gated: when Icarus Verilog is unavailable the check skips cleanly.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from _example_check import ROOT
from counterexample_pilot_check import _build_baseline, _build_repo, _repo_snapshot

from rtl_agent.mvp_demo import run_mvp_demo

FIXTURE = ROOT / "examples" / "counterexample-axi"
STIMULUS = FIXTURE / "failing-stimulus.json"
ALLOWED_FILE = "rtl/axi_pipe.sv"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("mvp demo check skipped (iverilog/vvp not available)")
        return 0

    with TemporaryDirectory(prefix="rtl-agent-mvp-demo-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_repo(workspace)
        before_head, before_hashes = _repo_snapshot(repo)

        baseline_dir = _build_baseline(iverilog, vvp, workspace, repo)

        summary = run_mvp_demo(
            failure_run=baseline_dir,
            repo=repo,
            config_path=repo / "rtl-agent.yaml",
            command="structured-failure",
            stimulus=STIMULUS,
            allowed_files=[ALLOWED_FILE],
            output=workspace / "demo",
            max_candidates=8,
            max_experiments=12,
            timeout=60,
        )

        _check_summary(workspace / "demo", summary)
        _check_repo_unchanged(repo, before_head, before_hashes)

    print("mvp demo check passed")
    return 0


def _check_summary(output: Path, summary: object) -> None:
    report = json.loads((output / "mvp-demo-summary.json").read_text(encoding="utf-8"))
    assert (output / "mvp-demo-summary.md").exists()

    # Every workflow stage ran.
    stages = {s["stage"]: s["status"] for s in report["stages"]}
    for stage in (
        "inspect-run",
        "export-failure-package",
        "minimize-stimulus",
        "generate-interventions",
        "run-experiment-matrix",
    ):
        assert stage in stages, stages
    assert stages["inspect-run"] == "valid"
    assert stages["run-experiment-matrix"] == "executed"

    of = report["original_failure"]
    assert of["run_valid"] and of["family_digest"]
    assert of["failure_package_files"] >= 1

    mn = report["minimization"]
    assert mn["minimized_item_count"] < mn["original_item_count"]

    assert len(report["generated_candidates"]) >= 3
    assert report["experiment_outcomes"], "no experiment outcomes recorded"
    # At least one generated experiment measurably affected the observed failure.
    assert any(
        o["failure_removed"] or o["different_failure"] for o in report["experiment_outcomes"]
    )
    assert any(o["category"] == "experiment_result" for o in report["observations"])

    # No unsupported causal claim anywhere in the summary.
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
