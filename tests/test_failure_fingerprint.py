from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from rtl_agent.cli import app
from rtl_agent.failure_fingerprint import (
    FailureFingerprintError,
    compare_fingerprints,
    fingerprint_run,
    write_fingerprint_report,
)
from rtl_agent.failure_fingerprint_models import FingerprintMatchKind


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _semantic_payload(
    *,
    run_id: str,
    time: int = 40,
    signal: str = "tb.dut.payload_out",
    assertion: str = "payload_stable",
    source_file: str = "rtl/axi_pipe.sv",
    dependency: str = "payload_reg",
    ambiguous: bool = False,
) -> dict[str, dict[str, object]]:
    leaf = signal.split(".")[-1]
    failure_report = {
        "schema_version": 1,
        "divergence_graph_path": "failure-divergence-graph.json",
        "observed_failure_facts": [
            {
                "signal": signal,
                "identifier": leaf,
                "first_divergence_time": time,
                "failing_value": "x",
                "passing_value": "1",
                "xz_difference": True,
                "divergence_score": 12,
                "source": "waveform_comparison_report",
            }
        ],
        "earliest_divergence_time": time,
        "earliest_divergence_signals": [leaf],
        "ranked_relevant_signals": [
            {
                "name": signal,
                "score": 9,
                "criteria": ["transition_at_failure", "unknown_or_highz"],
                "source": "relevant_signal_reduction_report",
            }
        ],
        "candidate_source_locations": [
            {
                "identifier": leaf,
                "declaration_name": leaf,
                "declaration_kind": "logic",
                "file_path": source_file,
                "line": 21,
                "mapping_status": "exact",
                "source": "signal_source_map_report",
            }
        ],
        "driver_dependency_evidence": [
            {
                "source_signal": leaf,
                "depends_on": dependency,
                "label": "textual",
                "statement_kind": "procedural_assign",
                "evidence_file": source_file,
                "evidence_line": 44,
                "statement_text": f"{leaf} <= {dependency};",
                "guard": "rst == 0",
                "source": "rtl_driver_trace_report",
            }
        ],
        "unresolved_evidence": [],
        "ambiguous_evidence": [
            {
                "identifier": leaf,
                "kind": "multi_candidate",
                "detail": "two textual declarations",
                "source": "signal_source_map_report",
            }
        ]
        if ambiguous
        else [],
        "generated_from": [],
        "warnings": [],
        "parser_notes": [],
    }
    comparison = {
        "schema_version": 1,
        "failing_slice_path": "slices/failing.json",
        "passing_slice_path": "slices/passing.json",
        "time_basis": {
            "kind": "shared_ticks",
            "normalized": False,
            "common_start": time - 15,
            "common_end": time + 15,
            "detail": "shared ticks",
        },
        "shared_signal_count": 2,
        "diverging_signals": [
            {
                "name": signal,
                "identical": False,
                "first_divergence_time": time,
                "failing_value_at_divergence": "x",
                "passing_value_at_divergence": "1",
                "failing_transition_count": 3,
                "passing_transition_count": 2,
                "xz_difference": True,
                "divergence_duration": 5,
                "divergence_intervals": [{"start": time, "end": time + 5}],
                "divergence_score": 12,
            }
        ],
        "identical_signals": ["tb.dut.clk"],
        "global_earliest_divergence_time": time,
        "global_earliest_divergence_signals": [leaf],
        "warnings": [],
        "parser_notes": [],
    }
    reduction = {
        "schema_version": 1,
        "waveform_slice_path": "slices/failing.json",
        "assertion_link_path": "assertion-link.json",
        "assertion_signal": assertion,
        "assertion_summary": "assertion failed",
        "failure_time": time,
        "max_signals": 4,
        "total_candidate_signals": 2,
        "retained_signals": [
            {
                "name": signal,
                "identifier": leaf,
                "score": 9,
                "transition_count": 3,
                "nearest_transition_distance": 0,
                "reasons": [
                    {
                        "criterion": "transition_at_failure",
                        "points": 4,
                        "detail": "transition at failure",
                    }
                ],
            }
        ],
        "excluded": [],
        "reduced_slice_path": "slices/reduced.json",
        "reduced_slice_sha256": "volatile-hash-not-fingerprinted",
        "warnings": [],
        "parser_notes": [],
    }
    signal_map = {
        "schema_version": 1,
        "repository_map_path": "repo-map.json",
        "waveform_slice_path": "slices/failing.json",
        "comparison_path": "comparison.json",
        "total_signals": 1,
        "exact_count": 1,
        "probable_count": 0,
        "ambiguous_count": 1 if ambiguous else 0,
        "unresolved_count": 0,
        "mappings": [
            {
                "signal": signal,
                "leaf": leaf,
                "scope": ["tb", "dut"],
                "status": "ambiguous" if ambiguous else "exact",
                "reason": "textual declaration match",
                "candidates": [
                    {
                        "declaration_name": leaf,
                        "declaration_kind": "logic",
                        "file_path": source_file,
                        "line": 21,
                        "matched_element": leaf,
                        "matched_role": "declaration",
                        "match_reason": "leaf name",
                        "score": 100,
                        "primary": True,
                    }
                ],
            }
        ],
        "warnings": [],
        "parser_notes": [],
    }
    driver_trace = {
        "schema_version": 1,
        "signal_source_map_path": "signal-source-map.json",
        "repository_map_path": "repo-map.json",
        "repository_root": "/tmp/volatile/repo",
        "max_depth": 2,
        "max_nodes": 8,
        "traced_signals": [],
        "dependency_nodes": [
            {"identifier": leaf, "depth": 0, "resolved": True, "driver_count": 1},
            {"identifier": dependency, "depth": 1, "resolved": True, "driver_count": 1},
        ],
        "dependency_edges": [
            {
                "source_signal": leaf,
                "depends_on": dependency,
                "label": "textual",
                "statement_kind": "procedural_assign",
                "evidence_file": source_file,
                "evidence_line": 44,
            }
        ],
        "unresolved_identifiers": [],
        "truncated": False,
        "warnings": [],
        "parser_notes": [],
    }
    graph = {
        "schema_version": 1,
        "comparison_path": "comparison.json",
        "signal_source_map_path": "signal-source-map.json",
        "driver_trace_path": "rtl-driver-trace.json",
        "max_depth": 2,
        "max_nodes": 8,
        "root_identifiers": [leaf],
        "global_earliest_divergence_time": time,
        "nodes": [
            {
                "identifier": leaf,
                "depth": 0,
                "is_root": True,
                "signal": signal,
                "mapping_status": "ambiguous" if ambiguous else "exact",
                "driver_resolved": True,
                "driver_count": 1,
                "divergence": {
                    "first_divergence_time": time,
                    "failing_value": "x",
                    "passing_value": "1",
                    "divergence_score": 12,
                    "xz_difference": True,
                },
                "declarations": [
                    {
                        "declaration_name": leaf,
                        "declaration_kind": "logic",
                        "file_path": source_file,
                        "line": 21,
                    }
                ],
            },
            {
                "identifier": dependency,
                "depth": 1,
                "is_root": False,
                "mapping_status": "exact",
                "driver_resolved": True,
                "driver_count": 1,
                "declarations": [
                    {
                        "declaration_name": dependency,
                        "declaration_kind": "logic",
                        "file_path": source_file,
                        "line": 19,
                    }
                ],
            },
        ],
        "edges": [
            {
                "source": leaf,
                "target": dependency,
                "label": "textual",
                "statement_kind": "procedural_assign",
                "evidence_file": source_file,
                "evidence_line": 44,
            }
        ],
        "unresolved_identifiers": [],
        "truncated": False,
        "warnings": [],
        "parser_notes": [],
    }
    triage = {
        "schema_version": 1,
        "command_name": "sim",
        "command_status": "failed",
        "command_exit_code": 1,
        "command_result_path": "commands/sim/result.json",
        "stdout_path": "commands/sim/stdout.log",
        "stderr_path": "commands/sim/stderr.log",
        "assertion_failures": [
            {
                "source": "stderr",
                "line": 2,
                "summary": "assertion failed",
                "signal_or_label": assertion,
                "time_context": f"t={time}",
            }
        ],
        "waveform_references": [],
        "simulator_context": [],
        "bounded_evidence": [],
        "warnings": [],
        "parser_notes": [],
    }
    command_result = {
        "schema_version": 1,
        "command_id": f"{run_id}-volatile-command-id",
        "command_name": "sim",
        "argv": ["iverilog", "-o", f"/tmp/{run_id}/sim"],
        "cwd": f"/tmp/{run_id}/repo",
        "status": "failed",
        "started_at": "2026-07-05T12:00:00Z",
        "ended_at": "2026-07-05T12:00:01Z",
        "duration_seconds": 1.234,
        "exit_code": 1,
        "stdout_path": f"/tmp/{run_id}/stdout.log",
        "stderr_path": f"/tmp/{run_id}/stderr.log",
        "error": f"failure in /tmp/{run_id}/repo/rtl/axi_pipe.sv",
    }
    manifest = {
        "schema_version": 3,
        "run_id": run_id,
        "run_dir": f"/tmp/{run_id}",
        "created_at": "2026-07-05T12:00:00Z",
        "status": "completed",
        "failing_vcd": f"/tmp/{run_id}/failure.vcd",
        "passing_vcd": f"/tmp/{run_id}/passing.vcd",
        "repository_root": f"/tmp/{run_id}/repo",
        "external_inputs": [],
        "failure_time": time,
        "before": 15,
        "after": 15,
        "stages": [],
        "artifacts": [
            {
                "artifact_id": kind,
                "kind": kind,
                "path_kind": "run_relative",
                "relative_path": path,
                "schema_version": 1,
                "sha256": f"volatile-{run_id}-{kind}",
            }
            for kind, path in [
                ("failure_report", "failure-report.json"),
                ("waveform_comparison_report", "comparison.json"),
                ("relevant_signal_reduction_report", "reduction.json"),
                ("signal_source_map_report", "signal-source-map.json"),
                ("rtl_driver_trace_report", "rtl-driver-trace.json"),
                ("failure_divergence_graph_report", "failure-divergence-graph.json"),
                ("triage_report", "triage.json"),
                ("command_result", "commands/sim/result.json"),
            ]
        ],
        "failure_report_path": "failure-report.json",
        "warnings": [],
        "parser_notes": [],
    }
    return {
        "run-manifest.json": manifest,
        "failure-report.json": failure_report,
        "comparison.json": comparison,
        "reduction.json": reduction,
        "signal-source-map.json": signal_map,
        "rtl-driver-trace.json": driver_trace,
        "failure-divergence-graph.json": graph,
        "triage.json": triage,
        "commands/sim/result.json": command_result,
    }


def _make_run(tmp_path: Path, name: str, **overrides: Any) -> Path:
    run = tmp_path / name
    payloads = _semantic_payload(run_id=name, **overrides)
    for relative_path, payload in payloads.items():
        _write_json(run / relative_path, payload)
    return run


def _write_fingerprint(tmp_path: Path, run: Path, name: str) -> Path:
    path = tmp_path / f"{name}.json"
    write_fingerprint_report(fingerprint_run(run), path)
    return path


def test_identical_failures_ignore_run_dirs_ids_and_volatile_metadata(tmp_path: Path) -> None:
    left = fingerprint_run(_make_run(tmp_path, "run-a"))
    right = fingerprint_run(_make_run(tmp_path, "run-b"))

    assert left.exact_digest == right.exact_digest
    assert left.family_digest == right.family_digest
    assert left.terminal_outcome == ["sim|failed|1"]
    assert [item.path.as_posix() for item in left.inputs] == [
        item.path.as_posix() for item in right.inputs
    ]


def test_shifted_time_is_same_family_not_exact(tmp_path: Path) -> None:
    left_path = _write_fingerprint(tmp_path, _make_run(tmp_path, "run-a"), "left")
    right_path = _write_fingerprint(tmp_path, _make_run(tmp_path, "run-b", time=55), "right")

    report = compare_fingerprints(left_path, right_path)

    assert report.match_kind == FingerprintMatchKind.SAME_FAMILY
    assert not report.exact_match
    assert report.family_match


def test_same_signal_mechanism_with_different_volatile_metadata(tmp_path: Path) -> None:
    run = _make_run(tmp_path, "run-a")
    baseline = fingerprint_run(run)
    command_path = run / "commands/sim/result.json"
    command = json.loads(command_path.read_text(encoding="utf-8"))
    command["command_id"] = "different-uuid-like-id"
    command["started_at"] = "2026-07-05T13:00:00Z"
    command["ended_at"] = "2026-07-05T14:00:00Z"
    command["duration_seconds"] = 3600.0
    command["cwd"] = "/different/absolute/path"
    command["stderr_path"] = "/different/absolute/path/stderr.log"
    command["error"] = "failure in /different/absolute/path/source.sv"
    _write_json(command_path, command)

    changed = fingerprint_run(run)

    assert changed.exact_digest == baseline.exact_digest
    assert changed.family_digest == baseline.family_digest


@pytest.mark.parametrize(
    ("overrides", "component"),
    [
        ({"assertion": "different_assertion"}, "assertion_identity"),
        ({"signal": "tb.dut.ready_out"}, "earliest_divergent_signals"),
        ({"source_file": "rtl/other_pipe.sv", "dependency": "ready_reg"}, "mapped_sources"),
    ],
)
def test_material_mechanism_changes_differ(
    tmp_path: Path, overrides: dict[str, Any], component: str
) -> None:
    left_path = _write_fingerprint(tmp_path, _make_run(tmp_path, "run-a"), "left")
    right_path = _write_fingerprint(tmp_path, _make_run(tmp_path, "run-b", **overrides), "right")

    report = compare_fingerprints(left_path, right_path)

    assert report.match_kind == FingerprintMatchKind.RELATED_DIFFERENT
    assert not report.family_match
    changed = {item.component for item in report.component_matches if not item.match}
    assert component in changed


def test_ambiguous_and_incomplete_evidence_is_reported(tmp_path: Path) -> None:
    complete = _make_run(tmp_path, "complete", ambiguous=True)
    incomplete = _make_run(tmp_path, "incomplete")
    manifest_path = incomplete / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"] = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact["kind"]
        not in {
            "failure_divergence_graph_report",
            "signal_source_map_report",
            "rtl_driver_trace_report",
        }
    ]
    _write_json(manifest_path, manifest)
    (incomplete / "failure-report.json").unlink()

    complete_report = fingerprint_run(complete)
    incomplete_path = _write_fingerprint(tmp_path, incomplete, "incomplete")
    complete_path = _write_fingerprint(tmp_path, complete, "complete")
    comparison = compare_fingerprints(complete_path, incomplete_path)

    assert complete_report.ambiguous_markers
    assert fingerprint_run(incomplete).insufficient_evidence
    assert comparison.match_kind == FingerprintMatchKind.INSUFFICIENT


def test_fingerprint_serialization_and_digest_are_deterministic(tmp_path: Path) -> None:
    run = _make_run(tmp_path, "run-a")
    report = fingerprint_run(run)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_fingerprint_report(report, first)
    write_fingerprint_report(fingerprint_run(run), second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert report.exact_digest == fingerprint_run(run).exact_digest


def test_malformed_inputs_are_rejected(tmp_path: Path) -> None:
    run = tmp_path / "bad-run"
    run.mkdir()
    (run / "run-manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(FailureFingerprintError, match="run manifest is unreadable"):
        fingerprint_run(run)

    bad_fingerprint = tmp_path / "bad-fingerprint.json"
    bad_fingerprint.write_text("{}", encoding="utf-8")
    good = _write_fingerprint(tmp_path, _make_run(tmp_path, "good"), "good")
    with pytest.raises(FailureFingerprintError, match="could not load fingerprint"):
        compare_fingerprints(good, bad_fingerprint)


def test_cli_fingerprint_and_compare(tmp_path: Path) -> None:
    left = _make_run(tmp_path, "run-a")
    right = _make_run(tmp_path, "run-b", time=55)
    runner = CliRunner()
    left_fp = tmp_path / "left.json"
    right_fp = tmp_path / "right.json"
    comparison = tmp_path / "comparison.json"

    first = runner.invoke(
        app, ["fingerprint-run", "--run-dir", str(left), "--output", str(left_fp)]
    )
    second = runner.invoke(
        app, ["fingerprint-run", "--run-dir", str(right), "--output", str(right_fp)]
    )
    compared = runner.invoke(
        app,
        [
            "compare-fingerprints",
            "--left",
            str(left_fp),
            "--right",
            str(right_fp),
            "--output",
            str(comparison),
        ],
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert compared.exit_code == 0
    assert "same_likely_observed_failure_family" in compared.stdout
    assert comparison.exists()


def test_deepcopy_payload_helper_remains_plain_data() -> None:
    payload = _semantic_payload(run_id="plain")

    assert deepcopy(payload) == payload
