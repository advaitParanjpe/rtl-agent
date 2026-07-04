from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.run_inspection import (
    RunInspectionError,
    inspect_run,
    write_inspection_report,
)

FAILING_VCD = Path("examples/waveforms/failure.vcd")
PASSING_VCD = Path("examples/waveforms/passing.vcd")
SIMPLE_RTL = Path("examples/simple-rtl")


def build_run(
    tmp_path: Path, run_id: str = "r1", *, failing: Path = FAILING_VCD
) -> FailureIntelligenceRunManifest:
    store = RunStore(tmp_path / "runs", run_id=run_id)
    store.create()
    return run_failure_intelligence(
        store,
        failing_vcd=failing,
        passing_vcd=PASSING_VCD,
        repository_root=SIMPLE_RTL,
        failure_time=40,
        before=15,
        after=15,
    )


def run_dir_of(tmp_path: Path, run_id: str = "r1") -> Path:
    return tmp_path / "runs" / run_id


def edit_manifest(run_dir: Path, mutate: object) -> None:
    path = run_dir / "run-manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw)  # type: ignore[operator]
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_inspect_valid_run(tmp_path: Path) -> None:
    build_run(tmp_path)

    report = inspect_run(run_dir_of(tmp_path))

    assert report.valid is True
    assert report.manifest_status == "completed"
    assert report.missing_artifacts == 0
    assert report.invalid_artifacts == 0
    assert all(a.validity == "valid" for a in report.artifacts)
    assert all(s.validity == "valid" for s in report.stages)
    assert report.schema_version == 1


def test_inspect_corrupted_artifact_hash_mismatch(tmp_path: Path) -> None:
    build_run(tmp_path)
    (run_dir_of(tmp_path) / "signal-source-map.json").write_text("corrupt", encoding="utf-8")

    report = inspect_run(run_dir_of(tmp_path))

    assert report.valid is False
    signal_map = next(a for a in report.artifacts if a.relative_path == "signal-source-map.json")
    assert signal_map.validity == "hash_mismatch"
    by_name = {s.name: s.validity for s in report.stages}
    assert by_name["map-signals"] == "invalid"
    # Downstream stages whose own outputs are intact become stale.
    assert by_name["divergence-graph"] == "stale"


def test_inspect_missing_artifact(tmp_path: Path) -> None:
    build_run(tmp_path)
    (run_dir_of(tmp_path) / "driver-trace.json").unlink()

    report = inspect_run(run_dir_of(tmp_path))

    assert report.valid is False
    assert report.missing_artifacts >= 1
    trace = next(a for a in report.artifacts if a.relative_path == "driver-trace.json")
    assert trace.validity == "missing"
    by_name = {s.name: s.validity for s in report.stages}
    assert by_name["trace-drivers"] == "incomplete"


def test_inspect_malformed_schema(tmp_path: Path) -> None:
    build_run(tmp_path)
    # Replace an artifact with valid JSON that fails its typed model, and drop the
    # recorded hash so the hash check does not shadow the schema check.
    (run_dir_of(tmp_path) / "waveform" / "comparison.json").write_text("{}", encoding="utf-8")

    def drop_hash(raw: dict[str, Any]) -> None:
        for artifact in raw["artifacts"]:
            if artifact["relative_path"] == "waveform/comparison.json":
                artifact["sha256"] = None

    edit_manifest(run_dir_of(tmp_path), drop_hash)

    report = inspect_run(run_dir_of(tmp_path))

    comparison = next(a for a in report.artifacts if a.relative_path == "waveform/comparison.json")
    assert comparison.validity == "schema_malformed"
    assert report.valid is False


def test_inspect_unsupported_artifact_schema(tmp_path: Path) -> None:
    build_run(tmp_path)
    slice_path = run_dir_of(tmp_path) / "waveform" / "failing-slice.json"
    raw = json.loads(slice_path.read_text(encoding="utf-8"))
    raw["schema_version"] = 99
    slice_path.write_text(json.dumps(raw), encoding="utf-8")

    def drop_hash(raw_manifest: dict[str, Any]) -> None:
        for artifact in raw_manifest["artifacts"]:
            if artifact["relative_path"] == "waveform/failing-slice.json":
                artifact["sha256"] = None

    edit_manifest(run_dir_of(tmp_path), drop_hash)

    report = inspect_run(run_dir_of(tmp_path))

    failing = next(a for a in report.artifacts if a.relative_path == "waveform/failing-slice.json")
    assert failing.validity == "schema_unsupported"
    assert report.valid is False


def test_inspect_unsafe_recorded_path(tmp_path: Path) -> None:
    build_run(tmp_path)

    def tamper(raw: dict[str, Any]) -> None:
        for artifact in raw["artifacts"]:
            if artifact["relative_path"] == "waveform/comparison.json":
                artifact["relative_path"] = "../escape.json"

    edit_manifest(run_dir_of(tmp_path), tamper)

    report = inspect_run(run_dir_of(tmp_path))

    assert report.valid is False
    unsafe = [a for a in report.artifacts if a.validity == "unsafe_path"]
    assert [a.relative_path for a in unsafe] == ["../escape.json"]
    assert any("unsafe recorded artifact path" in w for w in report.warnings)
    # Nothing outside the run directory was created.
    assert not (tmp_path / "runs" / "escape.json").exists()


def test_inspect_moved_run_is_valid(tmp_path: Path) -> None:
    import shutil

    build_run(tmp_path)
    moved = tmp_path / "moved" / "r1"
    shutil.copytree(run_dir_of(tmp_path), moved)

    report = inspect_run(moved)

    assert report.valid is True
    assert str(report.run_dir).endswith("moved/r1")


def test_inspect_missing_external_input_reported_not_invalid(tmp_path: Path) -> None:
    build_run(tmp_path)

    def break_external(raw: dict[str, Any]) -> None:
        for external in raw["external_inputs"]:
            if external["name"] == "failing_vcd":
                external["path"] = str(tmp_path / "gone.vcd")

    edit_manifest(run_dir_of(tmp_path), break_external)

    report = inspect_run(run_dir_of(tmp_path))

    assert report.external_inputs_present is False
    assert any("external input is missing now" in w for w in report.warnings)
    # Artifacts are still valid, so the run itself remains valid.
    assert report.valid is True


def test_inspect_unsupported_manifest_version(tmp_path: Path) -> None:
    build_run(tmp_path)
    edit_manifest(run_dir_of(tmp_path), lambda raw: raw.__setitem__("schema_version", 99))

    report = inspect_run(run_dir_of(tmp_path))

    assert report.valid is False
    assert report.artifacts == []
    assert any("unsupported run manifest schema version" in w for w in report.warnings)


def test_inspect_failed_run_is_invalid(tmp_path: Path) -> None:
    build_run(tmp_path, failing=tmp_path / "missing.vcd")

    report = inspect_run(run_dir_of(tmp_path))

    assert report.valid is False
    assert report.manifest_status == "failed"


def test_inspection_is_read_only(tmp_path: Path) -> None:
    build_run(tmp_path)
    run_dir = run_dir_of(tmp_path)
    before = {p: p.read_bytes() for p in run_dir.rglob("*") if p.is_file()}

    inspect_run(run_dir)

    after = {p: p.read_bytes() for p in run_dir.rglob("*") if p.is_file()}
    assert before == after


def test_missing_manifest_errors(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(RunInspectionError, match="run manifest not found"):
        inspect_run(empty)


def test_deterministic_inspection_report(tmp_path: Path) -> None:
    build_run(tmp_path)
    report = inspect_run(run_dir_of(tmp_path))
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_inspection_report(report, first)
    write_inspection_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1
