"""Demonstrate that many failing regression seeds reduce to a few failure families.

This hermetic check generates real failure fingerprints from the checked-in
waveform/RTL fixtures for three distinct observed failure mechanisms, replays
each mechanism three times (repeated regression "seeds"), and then clusters all
of them with the real `cluster-failures` command. It asserts that the nine runs
collapse into exactly three observed failure families, that repeated seeds land
in one family (as exact duplicates), and that the report is deterministic and
order-independent — all read-only, with no simulator and no new analysis.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from _example_check import ROOT, run_cli

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_fingerprint import fingerprint_run, write_fingerprint_report
from rtl_agent.failure_intelligence_run import run_failure_intelligence

# (label, fixture directory, failure time) for three distinct failure mechanisms.
MECHANISMS = [
    ("stream", ROOT / "examples" / "axi-stream-router", 40),
    ("repo", ROOT / "examples" / "axi-router-repo", 45),
    ("ambiguity", ROOT / "examples" / "axi-router-ambiguity", 40),
]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rtl-agent-family-cluster-") as raw_tmp:
        workspace = Path(raw_tmp)
        fingerprint_dir = workspace / "fingerprints"
        fingerprint_dir.mkdir()

        seed_count = 0
        for label, fixture, failure_time in MECHANISMS:
            # Three repeated seeds per mechanism (identical re-runs of one seed).
            for index in range(3):
                run_dir = _build_run(workspace, f"{label}-{index}", fixture, failure_time)
                report = fingerprint_run(run_dir)
                assert not report.insufficient_evidence, (label, report.insufficient_evidence)
                write_fingerprint_report(report, fingerprint_dir / f"{label}-{index}.json")
                seed_count += 1

        output = workspace / "regression"
        summary = run_cli(
            ["cluster-failures", "--fingerprint-dir", str(fingerprint_dir), "--output", str(output)]
        )

        assert summary["valid_fingerprints"] == seed_count == 9, summary
        assert summary["family_count"] == 3, summary
        assert summary["family_count"] < summary["valid_fingerprints"]
        # Each mechanism's three repeated seeds are recorded as exact duplicates.
        assert summary["exact_duplicates"] == 6, summary
        assert summary["insufficient_evidence"] == 0

        report_json = json.loads((output / "regression-families.json").read_text(encoding="utf-8"))
        assert len(report_json["families"]) == 3
        for family in report_json["families"]:
            assert family["size"] == 3
            assert family["representative"]["selection_reason"]
            assert "not a root-cause claim" in family["description"]
        assert (output / "regression-families.md").exists()

        _check_order_independent(fingerprint_dir)

    print("failure family cluster check passed")
    return 0


def _build_run(workspace: Path, run_id: str, fixture: Path, failure_time: int) -> Path:
    store = RunStore(workspace / "runs", run_id=run_id)
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=fixture / "waveforms" / "failure.vcd",
        passing_vcd=fixture / "waveforms" / "passing.vcd",
        repository_root=fixture / "rtl",
        failure_time=failure_time,
        before=15,
        after=15,
    )
    return store.run_dir


def _check_order_independent(fingerprint_dir: Path) -> None:
    from rtl_agent.failure_family import cluster_fingerprints

    paths = sorted(fingerprint_dir.glob("*.json"))
    forward = cluster_fingerprints(fingerprint_paths=paths).model_dump(mode="json")
    reverse = cluster_fingerprints(fingerprint_paths=list(reversed(paths))).model_dump(mode="json")
    assert forward == reverse, "clustering result depends on input order"


if __name__ == "__main__":
    sys.exit(main())
