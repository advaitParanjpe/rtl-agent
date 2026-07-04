from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rtl_agent.evidence_bundle_models import (
    EvidenceArtifactKind,
    EvidenceArtifactReference,
    EvidenceBundleManifest,
    EvidenceBundleReport,
    EvidenceBundleStatus,
)


class EvidenceBundleError(RuntimeError):
    pass


def export_evidence_bundle(run_dir: Path, output_dir: Path) -> EvidenceBundleReport:
    manifest = EvidenceBundleManifest(
        run_dir=run_dir.resolve(),
        output_dir=output_dir.resolve(),
    )
    artifacts: list[EvidenceArtifactReference] = []
    warnings: list[str] = []
    failure_reason: str | None = None

    if not manifest.run_dir.exists() or not manifest.run_dir.is_dir():
        failure_reason = f"run directory does not exist: {manifest.run_dir}"
    elif not (manifest.run_dir / "run.json").exists():
        failure_reason = f"required run metadata is missing: {manifest.run_dir / 'run.json'}"
    else:
        artifacts = _collect_artifacts(manifest)
        warnings.extend(_missing_optional_warnings(manifest))

    status = EvidenceBundleStatus.FAILED if failure_reason else EvidenceBundleStatus.PASSED
    manifest_path = manifest.output_dir / "manifest.json"
    report = EvidenceBundleReport(
        status=status,
        run_dir=manifest.run_dir,
        output_dir=manifest.output_dir,
        manifest_path=manifest_path,
        artifacts=artifacts,
        warnings=warnings,
        failure_reason=failure_reason,
        summary=_summary(status, artifacts, warnings, failure_reason),
    )
    _write_bundle_outputs(manifest, report)
    return report


def write_evidence_bundle_report(report: EvidenceBundleReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_bundle_outputs(manifest: EvidenceBundleManifest, report: EvidenceBundleReport) -> None:
    manifest.output_dir.mkdir(parents=True, exist_ok=True)
    (manifest.output_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_evidence_bundle_report(report, manifest.output_dir / "bundle.json")


def _collect_artifacts(manifest: EvidenceBundleManifest) -> list[EvidenceArtifactReference]:
    paths = [
        path
        for path in manifest.run_dir.rglob("*")
        if path.is_file() and not _is_within(path, manifest.output_dir)
    ]
    return [
        _artifact_reference(manifest, path)
        for path in sorted(paths, key=lambda item: item.relative_to(manifest.run_dir).as_posix())
    ]


def _artifact_reference(manifest: EvidenceBundleManifest, path: Path) -> EvidenceArtifactReference:
    relative_path = path.relative_to(manifest.run_dir).as_posix()
    kind = _artifact_kind(path, relative_path)
    is_referenced_only = _is_referenced_only(manifest, relative_path)
    schema_version = _schema_version(path) if path.suffix == ".json" else None
    return EvidenceArtifactReference(
        artifact_id=_artifact_id(relative_path),
        kind=kind,
        source_path=path.resolve(),
        relative_path=relative_path,
        exists=True,
        size_bytes=path.stat().st_size,
        sha256=_sha256(path),
        schema_version=schema_version,
        included_in_bundle=False,
        omitted_reason=(
            "referenced only; artifact content remains in the local run directory"
            if is_referenced_only
            else "index only; content is not duplicated in compact evidence bundle"
        ),
        provenance=f"local run artifact: {relative_path}",
    )


def _artifact_kind(path: Path, relative_path: str) -> EvidenceArtifactKind:
    if relative_path == "run.json":
        return EvidenceArtifactKind.RUN_METADATA
    if relative_path == "events.jsonl":
        return EvidenceArtifactKind.RUN_EVENTS
    if relative_path.startswith("commands/") and relative_path.endswith("/result.json"):
        return EvidenceArtifactKind.COMMAND_RESULT
    if relative_path.startswith("commands/") and relative_path.endswith("/stdout.log"):
        return EvidenceArtifactKind.COMMAND_STDOUT
    if relative_path.startswith("commands/") and relative_path.endswith("/stderr.log"):
        return EvidenceArtifactKind.COMMAND_STDERR
    if relative_path == "discovery/repository-map.json":
        return EvidenceArtifactKind.DISCOVERY_REPOSITORY_MAP
    if relative_path == "implementation/report.json":
        return EvidenceArtifactKind.IMPLEMENTATION_REPORT
    if relative_path == "benchmarks/report.json":
        return EvidenceArtifactKind.BENCHMARK_REPORT
    if path.suffix == ".json":
        return _json_artifact_kind(path)
    return EvidenceArtifactKind.OTHER_ARTIFACT


def _json_artifact_kind(path: Path) -> EvidenceArtifactKind:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return EvidenceArtifactKind.OTHER_JSON
    if not isinstance(raw, dict):
        return EvidenceArtifactKind.OTHER_JSON
    keys = set(raw)
    if {"outcome", "deterministic_findings", "implementation_report_path"} <= keys:
        return EvidenceArtifactKind.REVIEW_REPORT
    if {"assertion_failures", "command_result_path", "bounded_evidence"} <= keys:
        return EvidenceArtifactKind.TRIAGE_REPORT
    if {"strength", "weak_patterns", "implementation_report_path"} <= keys:
        return EvidenceArtifactKind.VERIFICATION_STRENGTH_REPORT
    if {"selected_assertion", "selected_waveform", "timestamp_conversion"} <= keys:
        return EvidenceArtifactKind.ASSERTION_WAVEFORM_LINK_REPORT
    if {"window", "value_changes", "parse_statistics", "selected_signals"} <= keys:
        return EvidenceArtifactKind.WAVEFORM_SLICE_REPORT
    if {"retained_signals", "reduced_slice_path", "total_candidate_signals"} <= keys:
        return EvidenceArtifactKind.RELEVANT_SIGNAL_REDUCTION_REPORT
    if {"diverging_signals", "time_basis", "shared_signal_count"} <= keys:
        return EvidenceArtifactKind.WAVEFORM_COMPARISON_REPORT
    if {"mappings", "exact_count", "ambiguous_count"} <= keys:
        return EvidenceArtifactKind.SIGNAL_SOURCE_MAP_REPORT
    if {"traced_signals", "dependency_nodes", "dependency_edges"} <= keys:
        return EvidenceArtifactKind.RTL_DRIVER_TRACE_REPORT
    if {"root_identifiers", "nodes", "edges"} <= keys:
        return EvidenceArtifactKind.FAILURE_DIVERGENCE_GRAPH_REPORT
    return EvidenceArtifactKind.OTHER_JSON


def _schema_version(path: Path) -> int | None:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            schema_version = raw.get("schema_version")
            if isinstance(schema_version, int):
                return schema_version
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        return None
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _missing_optional_warnings(manifest: EvidenceBundleManifest) -> list[str]:
    warnings: list[str] = []
    for relative_path in manifest.optional_artifact_paths:
        if not (manifest.run_dir / relative_path).exists():
            warnings.append(f"optional artifact is missing: {relative_path}")
    return warnings


def _is_referenced_only(manifest: EvidenceBundleManifest, relative_path: str) -> bool:
    return any(
        fnmatch.fnmatch(relative_path, pattern)
        or fnmatch.fnmatch(Path(relative_path).name, pattern)
        for pattern in manifest.referenced_only_patterns
    )


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _artifact_id(relative_path: str) -> str:
    return relative_path.replace("/", "__").replace(".", "-")


def _summary(
    status: EvidenceBundleStatus,
    artifacts: list[EvidenceArtifactReference],
    warnings: list[str],
    failure_reason: str | None,
) -> str:
    if failure_reason:
        return f"{status} evidence bundle export: {failure_reason}"
    return (
        f"{status} evidence bundle export with {len(artifacts)} artifact reference(s) "
        f"and {len(warnings)} warning(s)"
    )


def report_summary_payload(report: EvidenceBundleReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "status": report.status,
        "output": str(report.output_dir / "bundle.json"),
        "manifest": str(report.manifest_path),
        "artifacts": len(report.artifacts),
        "warnings": len(report.warnings),
        "failure_reason": report.failure_reason,
        "summary": report.summary,
    }
