"""Real Icarus-backed pilot for Hypothesis-Driven Intervention Templates.

It composes the evidence-to-experiment generation layer end to end on the
project-owned counterexample AXI fixture: build a target Git repository,
generate a genuine baseline failure-intelligence run (fingerprint, source map,
driver trace, divergence graph), then generate a bounded set of reviewable
intervention candidates from that evidence and confirm the resulting manifest is
directly consumable by the experiment matrix.

The generator itself is generation-only: it never applies, executes, commits, or
pushes anything, and the source repository stays byte-for-byte unchanged. As a
separate integration step the pilot runs the existing experiment matrix against
the generated manifest and confirms at least one evidence-backed candidate
removes or changes the observed failure.

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
ALLOWED_FILE = "rtl/axi_pipe.sv"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("intervention templates pilot check skipped (iverilog/vvp not available)")
        return 0

    with TemporaryDirectory(prefix="rtl-agent-intervention-templates-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_repo(workspace)
        before_head, before_hashes = _repo_snapshot(repo)

        baseline_dir = _build_baseline(iverilog, vvp, workspace, repo)

        generated = workspace / "generated"
        summary = run_cli(
            [
                "generate-interventions",
                "--failure-run",
                str(baseline_dir),
                "--repo",
                str(repo),
                "--allowed-file",
                ALLOWED_FILE,
                "--max-candidates",
                "12",
                "--output",
                str(generated),
            ]
        )
        assert summary["target_commit"], summary
        _check_generation(generated, repo)
        # Generation must not touch the repository at all.
        _check_repo_unchanged(repo, before_head, before_hashes)

        # Separate integration step: the generated manifest drives the matrix.
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
        matrix = workspace / "matrix"
        run_cli(
            [
                "run-experiment-matrix",
                "--baseline-run",
                str(baseline_dir),
                "--reduction-report",
                str(minimization / "reduction-report.json"),
                "--repo",
                str(repo),
                "--config",
                str(repo / "rtl-agent.yaml"),
                "--command",
                "structured-failure",
                "--interventions",
                str(generated / "interventions.json"),
                "--output",
                str(matrix),
                "--max-experiments",
                "12",
                "--timeout",
                "60",
            ]
        )
        _check_matrix_integration(matrix)
        _check_repo_unchanged(repo, before_head, before_hashes)

    print("intervention templates pilot check passed")
    return 0


def _check_generation(generated: Path, repo: Path) -> None:
    report = json.loads((generated / "intervention-templates.json").read_text(encoding="utf-8"))
    assert (generated / "intervention-templates.md").exists()
    assert (generated / "interventions.json").exists()

    candidates = report["candidates"]
    assert len(candidates) >= 3, candidates
    kinds = {c["template_kind"] for c in candidates}
    assert "suppress_assignment" in kinds
    assert "hold_register" in kinds
    assert kinds & {"override_condition", "block_state_transition"}

    # Exact evidence references are preserved for every candidate.
    for c in candidates:
        assert c["file"] == ALLOWED_FILE
        assert c["allowed_files"] == [ALLOWED_FILE]
        assert c["source_line"] >= 1
        assert c["source_span_text"]
        assert c["source_sha256"] and c["file_sha256"]
        assert c["evidence"]["drivers"], c["candidate_id"]
        assert c["experiment_note"]
        # The recorded span must actually exist in the committed source.
        source = (repo / c["file"]).read_text(encoding="utf-8")
        assert source.count(c["replace_old"]) == 1, c["candidate_id"]

    # No unsupported causal claim anywhere in the report.
    assert "not a causal claim" in report["disclaimer"] or "causal" in report["disclaimer"]
    blob = json.dumps(report).lower()
    assert "root cause of" not in blob
    assert "caused by" not in blob

    # The manifest is a valid, matrix-compatible InterventionManifest.
    from rtl_agent.experiment_matrix_models import InterventionManifest

    manifest = InterventionManifest.model_validate_json(
        (generated / "interventions.json").read_text(encoding="utf-8")
    )
    assert len(manifest.interventions) == len(candidates)
    for entry in manifest.interventions:
        assert entry.replace is not None
        assert entry.allowed_files == [ALLOWED_FILE]


def _check_matrix_integration(matrix: Path) -> None:
    report = json.loads((matrix / "experiment-matrix.json").read_text(encoding="utf-8"))
    rows = report["rows"]
    assert rows, "experiment matrix produced no rows from the generated manifest"
    # At least one generated candidate removes or changes the observed failure.
    assert any(row["failure_removed"] or row["different_failure"] for row in rows), (
        "no generated candidate removed or changed the failure"
    )


def _check_repo_unchanged(repo: Path, before_head: str, before_hashes: dict[str, str]) -> None:
    after_head, after_hashes = _repo_snapshot(repo)
    assert after_head == before_head, "target repository commit changed"
    assert after_hashes == before_hashes, "target repository files changed"


if __name__ == "__main__":
    sys.exit(main())
