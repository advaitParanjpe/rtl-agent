from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_run_inspection import build_run, edit_manifest, run_dir_of

from rtl_agent.failure_package import FailurePackageError, export_failure_package


def read_package_manifest(package_dir: Path) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(
        (package_dir / "package-manifest.json").read_text(encoding="utf-8")
    )
    return raw


def test_export_valid_run(tmp_path: Path) -> None:
    build_run(tmp_path)
    package = tmp_path / "pkg"

    manifest = export_failure_package(run_dir_of(tmp_path), package)

    assert manifest.package_status == "valid"
    assert manifest.verified is True
    assert manifest.run_id == "r1"
    package_paths = {file.package_path for file in manifest.files}
    assert "inspection-report.json" in package_paths
    assert "run/run-manifest.json" in package_paths
    assert "run/failure-report.json" in package_paths
    assert "run/failure-report.md" in package_paths
    assert "run/waveform/comparison.json" in package_paths
    for file in manifest.files:
        assert (package / file.package_path).exists()


def test_package_manifest_records_required_fields(tmp_path: Path) -> None:
    build_run(tmp_path)
    package = tmp_path / "pkg"

    export_failure_package(run_dir_of(tmp_path), package)

    raw = read_package_manifest(package)
    assert raw["schema_version"] == 1
    roles = {file["role"] for file in raw["files"]}
    assert {"run_manifest", "inspection_report", "failure_report", "evidence_artifact"} <= roles
    for file in raw["files"]:
        assert file["sha256"]
        assert file["size_bytes"] >= 0
        assert not file["package_path"].startswith("/")
        assert ".." not in Path(file["package_path"]).parts
    # Evidence artifacts carry their original run-relative provenance.
    comparison = next(
        f for f in raw["files"] if f["package_path"] == "run/waveform/comparison.json"
    )
    assert comparison["run_relative_path"] == "waveform/comparison.json"
    assert comparison["schema_version"] == 1


def test_export_excludes_unrelated_files(tmp_path: Path) -> None:
    build_run(tmp_path)
    package = tmp_path / "pkg"

    export_failure_package(run_dir_of(tmp_path), package)

    # Run-store bookkeeping and any external inputs are never packaged.
    assert not (package / "run" / "events.jsonl").exists()
    assert not (package / "run" / "run.json").exists()
    packaged = {p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()}
    assert "run/events.jsonl" not in packaged
    assert "run/run.json" not in packaged


def test_refuse_invalid_run(tmp_path: Path) -> None:
    build_run(tmp_path)
    (run_dir_of(tmp_path) / "signal-source-map.json").write_text("corrupt", encoding="utf-8")
    package = tmp_path / "pkg"

    with pytest.raises(FailurePackageError, match="refusing to export"):
        export_failure_package(run_dir_of(tmp_path), package)
    assert not package.exists() or not any(package.iterdir())


def test_allow_failed_exports_marked_failed(tmp_path: Path) -> None:
    build_run(tmp_path)
    edit_manifest(run_dir_of(tmp_path), lambda raw: raw.__setitem__("status", "failed"))
    package = tmp_path / "pkg"

    with pytest.raises(FailurePackageError, match="allow_failed"):
        export_failure_package(run_dir_of(tmp_path), package)

    manifest = export_failure_package(run_dir_of(tmp_path), tmp_path / "pkg2", allow_failed=True)
    assert manifest.package_status == "failed"
    assert manifest.verified is True
    assert any(f.package_path == "run/waveform/comparison.json" for f in manifest.files)


def test_refuse_unsafe_recorded_path(tmp_path: Path) -> None:
    build_run(tmp_path)

    def tamper(raw: dict[str, Any]) -> None:
        for artifact in raw["artifacts"]:
            if artifact["relative_path"] == "waveform/comparison.json":
                artifact["relative_path"] = "../escape.json"

    edit_manifest(run_dir_of(tmp_path), tamper)

    with pytest.raises(FailurePackageError, match="refusing to export"):
        export_failure_package(run_dir_of(tmp_path), tmp_path / "pkg")


def test_output_must_be_empty(tmp_path: Path) -> None:
    build_run(tmp_path)
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FailurePackageError, match="not empty"):
        export_failure_package(run_dir_of(tmp_path), package)


def test_output_must_be_outside_run(tmp_path: Path) -> None:
    build_run(tmp_path)
    inside = run_dir_of(tmp_path) / "package"

    with pytest.raises(FailurePackageError, match="outside the run directory"):
        export_failure_package(run_dir_of(tmp_path), inside)


def test_deterministic_package(tmp_path: Path) -> None:
    build_run(tmp_path)
    export_failure_package(run_dir_of(tmp_path), tmp_path / "a")
    export_failure_package(run_dir_of(tmp_path), tmp_path / "b")

    manifest_a = (tmp_path / "a" / "package-manifest.json").read_text(encoding="utf-8")
    manifest_b = (tmp_path / "b" / "package-manifest.json").read_text(encoding="utf-8")
    assert manifest_a == manifest_b
    slice_a = (tmp_path / "a" / "run" / "waveform" / "failing-slice.json").read_bytes()
    slice_b = (tmp_path / "b" / "run" / "waveform" / "failing-slice.json").read_bytes()
    assert slice_a == slice_b


def test_export_is_read_only_on_source(tmp_path: Path) -> None:
    build_run(tmp_path)
    run_dir = run_dir_of(tmp_path)
    before = {p: p.read_bytes() for p in run_dir.rglob("*") if p.is_file()}

    export_failure_package(run_dir, tmp_path / "pkg")

    after = {p: p.read_bytes() for p in run_dir.rglob("*") if p.is_file()}
    assert before == after


def test_missing_manifest_errors(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(FailurePackageError, match="cannot inspect run"):
        export_failure_package(empty, tmp_path / "pkg")
