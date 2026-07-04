from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from rtl_agent.failure_divergence_graph_models import (
    FAILURE_DIVERGENCE_GRAPH_SCHEMA_VERSION,
    FailureDivergenceGraphReport,
)
from rtl_agent.failure_intelligence_run import (
    FailureIntelligenceRunError,
    resolve_run_relative,
    schema_version_of,
    sha256_file,
)
from rtl_agent.failure_report_models import FAILURE_REPORT_SCHEMA_VERSION, FailureReport
from rtl_agent.relevant_signal_models import (
    RELEVANT_SIGNAL_REDUCTION_SCHEMA_VERSION,
    RelevantSignalReductionReport,
)
from rtl_agent.repository_map import REPOSITORY_MAP_SCHEMA_VERSION, RepositoryMap
from rtl_agent.rtl_driver_trace_models import RTL_DRIVER_TRACE_SCHEMA_VERSION, RtlDriverTraceReport
from rtl_agent.run_inspection_models import (
    ArtifactInspection,
    ArtifactValidity,
    ExternalInputInspection,
    RunInspectionReport,
    StageInspection,
    StageValidity,
)
from rtl_agent.signal_source_map_models import (
    SIGNAL_SOURCE_MAP_SCHEMA_VERSION,
    SignalSourceMapReport,
)
from rtl_agent.waveform_comparison_models import (
    WAVEFORM_COMPARISON_SCHEMA_VERSION,
    WaveformComparisonReport,
)
from rtl_agent.waveform_slice_models import WAVEFORM_SLICE_SCHEMA_VERSION, WaveformSliceReport

_SUPPORTED_MANIFEST_VERSIONS = frozenset({2, 3})

# Registry mapping recorded artifact kind -> (typed model, expected schema version).
# Kinds with no model (e.g. Markdown) are validated by existence and hash only.
_ARTIFACT_MODELS: dict[str, tuple[type[BaseModel] | None, int | None]] = {
    "waveform_slice_report": (WaveformSliceReport, WAVEFORM_SLICE_SCHEMA_VERSION),
    "waveform_comparison_report": (WaveformComparisonReport, WAVEFORM_COMPARISON_SCHEMA_VERSION),
    "discovery_repository_map": (RepositoryMap, REPOSITORY_MAP_SCHEMA_VERSION),
    "signal_source_map_report": (SignalSourceMapReport, SIGNAL_SOURCE_MAP_SCHEMA_VERSION),
    "rtl_driver_trace_report": (RtlDriverTraceReport, RTL_DRIVER_TRACE_SCHEMA_VERSION),
    "failure_divergence_graph_report": (
        FailureDivergenceGraphReport,
        FAILURE_DIVERGENCE_GRAPH_SCHEMA_VERSION,
    ),
    "relevant_signal_reduction_report": (
        RelevantSignalReductionReport,
        RELEVANT_SIGNAL_REDUCTION_SCHEMA_VERSION,
    ),
    "failure_report": (FailureReport, FAILURE_REPORT_SCHEMA_VERSION),
    "failure_report_markdown": (None, None),
}


class RunInspectionError(RuntimeError):
    pass


def inspect_run(run_dir: Path) -> RunInspectionReport:
    """Validate an existing run directory against its manifest (read-only)."""

    resolved_dir = run_dir.resolve()
    manifest_path = resolved_dir / "run-manifest.json"
    if not manifest_path.exists():
        raise RunInspectionError(f"run manifest not found: {manifest_path}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RunInspectionError(f"run manifest is unreadable: {manifest_path}") from exc
    if not isinstance(raw, dict):
        raise RunInspectionError(f"run manifest is not a JSON object: {manifest_path}")

    schema_version = raw.get("schema_version")
    manifest_status = raw.get("status")
    run_id = raw.get("run_id")
    if schema_version not in _SUPPORTED_MANIFEST_VERSIONS:
        return RunInspectionReport(
            run_dir=resolved_dir,
            manifest_run_id=str(run_id) if isinstance(run_id, str) else None,
            manifest_schema_version=schema_version if isinstance(schema_version, int) else None,
            manifest_status=str(manifest_status) if isinstance(manifest_status, str) else None,
            valid=False,
            external_inputs_present=False,
            warnings=[f"unsupported run manifest schema version: {schema_version}"],
            parser_notes=_NOTES,
        )

    warnings: list[str] = []
    artifacts = _inspect_artifacts(resolved_dir, raw, warnings)
    by_path = {artifact.relative_path: artifact for artifact in artifacts}
    stages = _inspect_stages(raw, by_path)
    external_inputs = _inspect_external_inputs(raw, warnings)

    valid_artifacts = sum(1 for a in artifacts if a.validity == ArtifactValidity.VALID)
    missing_artifacts = sum(1 for a in artifacts if a.validity == ArtifactValidity.MISSING)
    invalid_artifacts = len(artifacts) - valid_artifacts - missing_artifacts
    external_present = all(external.exists_now for external in external_inputs)
    run_valid = (
        manifest_status == "completed"
        and bool(stages)
        and all(stage.validity == StageValidity.VALID for stage in stages)
        and missing_artifacts == 0
        and invalid_artifacts == 0
    )

    return RunInspectionReport(
        run_dir=resolved_dir,
        manifest_run_id=str(run_id) if isinstance(run_id, str) else None,
        manifest_schema_version=schema_version,
        manifest_status=str(manifest_status) if isinstance(manifest_status, str) else None,
        valid=run_valid,
        external_inputs_present=external_present,
        artifacts=artifacts,
        stages=stages,
        external_inputs=external_inputs,
        valid_artifacts=valid_artifacts,
        missing_artifacts=missing_artifacts,
        invalid_artifacts=invalid_artifacts,
        warnings=sorted(dict.fromkeys(warnings)),
        parser_notes=_NOTES,
    )


def write_inspection_report(report: RunInspectionReport, output: Path) -> None:
    if output.exists() and output.is_dir():
        raise RunInspectionError(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _inspect_artifacts(
    run_dir: Path, raw: dict[str, object], warnings: list[str]
) -> list[ArtifactInspection]:
    recorded = raw.get("artifacts")
    if not isinstance(recorded, list):
        return []
    inspected: list[ArtifactInspection] = []
    for entry in recorded:
        if not isinstance(entry, dict):
            continue
        relative = str(entry.get("relative_path"))
        kind = str(entry.get("kind"))
        recorded_hash = entry.get("sha256")
        recorded_hash = recorded_hash if isinstance(recorded_hash, str) else None
        recorded_version = entry.get("schema_version")
        recorded_version = recorded_version if isinstance(recorded_version, int) else None
        inspected.append(
            _inspect_one_artifact(
                run_dir, relative, kind, recorded_hash, recorded_version, warnings
            )
        )
    return inspected


def _inspect_one_artifact(
    run_dir: Path,
    relative: str,
    kind: str,
    recorded_hash: str | None,
    recorded_version: int | None,
    warnings: list[str],
) -> ArtifactInspection:
    def build(
        validity: ArtifactValidity, detail: str | None, **extra: object
    ) -> ArtifactInspection:
        return ArtifactInspection(
            artifact_id=_artifact_id(kind, relative),
            kind=kind,
            relative_path=relative,
            validity=validity,
            detail=detail,
            recorded_sha256=recorded_hash,
            recorded_schema_version=recorded_version,
            **extra,  # type: ignore[arg-type]
        )

    try:
        path = resolve_run_relative(run_dir, relative)
    except FailureIntelligenceRunError as exc:
        warnings.append(f"unsafe recorded artifact path (escapes run directory): {relative}")
        return build(ArtifactValidity.UNSAFE_PATH, str(exc))

    if not path.exists() or not path.is_file():
        return build(ArtifactValidity.MISSING, "artifact file is missing")

    actual_hash = sha256_file(path)
    if recorded_hash is None:
        warnings.append(f"artifact has no recorded sha256; hash not verified: {relative}")
    elif recorded_hash != actual_hash:
        return build(
            ArtifactValidity.HASH_MISMATCH,
            "recorded sha256 does not match the file",
            actual_sha256=actual_hash,
        )

    actual_version = schema_version_of(path)
    model, expected_version = _ARTIFACT_MODELS.get(kind, (None, None))
    if model is not None:
        try:
            model.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, ValueError, OSError):
            return build(
                ArtifactValidity.SCHEMA_MALFORMED,
                "artifact does not validate against its typed model",
                actual_sha256=actual_hash,
                actual_schema_version=actual_version,
            )
        if actual_version != expected_version:
            return build(
                ArtifactValidity.SCHEMA_UNSUPPORTED,
                f"schema version {actual_version} is not supported (expected {expected_version})",
                actual_sha256=actual_hash,
                actual_schema_version=actual_version,
            )
    return build(
        ArtifactValidity.VALID,
        None,
        actual_sha256=actual_hash,
        actual_schema_version=actual_version,
    )


def _inspect_stages(
    raw: dict[str, object], by_path: dict[str, ArtifactInspection]
) -> list[StageInspection]:
    recorded = raw.get("stages")
    if not isinstance(recorded, list):
        return []
    inspected: list[StageInspection] = []
    upstream_broken = False
    for entry in recorded:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name"))
        disposition = str(entry.get("disposition"))
        outputs = _stage_output_paths(entry.get("outputs"))
        validity, detail = _stage_validity(disposition, outputs, by_path, upstream_broken)
        if validity != StageValidity.VALID:
            upstream_broken = True
        inspected.append(
            StageInspection(
                name=name,
                disposition=disposition,
                validity=validity,
                outputs=outputs,
                detail=detail,
            )
        )
    return inspected


def _stage_validity(
    disposition: str,
    outputs: list[str],
    by_path: dict[str, ArtifactInspection],
    upstream_broken: bool,
) -> tuple[StageValidity, str | None]:
    if disposition in {"skipped", "failed"} or not outputs:
        return StageValidity.INCOMPLETE, f"stage recorded as {disposition} with no valid outputs"
    validities = [
        by_path[path].validity if path in by_path else ArtifactValidity.MISSING for path in outputs
    ]
    if any(
        v
        in {
            ArtifactValidity.HASH_MISMATCH,
            ArtifactValidity.SCHEMA_MALFORMED,
            ArtifactValidity.SCHEMA_UNSUPPORTED,
            ArtifactValidity.UNSAFE_PATH,
        }
        for v in validities
    ):
        return StageValidity.INVALID, "one or more outputs are invalid"
    if any(v == ArtifactValidity.MISSING for v in validities):
        return StageValidity.INCOMPLETE, "one or more outputs are missing"
    if upstream_broken:
        return (
            StageValidity.STALE,
            "outputs are valid but an upstream stage is invalid or incomplete",
        )
    return StageValidity.VALID, None


def _stage_output_paths(outputs: object) -> list[str]:
    if not isinstance(outputs, list):
        return []
    paths: list[str] = []
    for item in outputs:
        if isinstance(item, str):
            paths.append(item)
        elif isinstance(item, dict):
            path = item.get("path")
            if isinstance(path, str):
                paths.append(path)
    return paths


def _inspect_external_inputs(
    raw: dict[str, object], warnings: list[str]
) -> list[ExternalInputInspection]:
    recorded = raw.get("external_inputs")
    if not isinstance(recorded, list):
        return []
    inspected: list[ExternalInputInspection] = []
    for entry in recorded:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name"))
        path = str(entry.get("path"))
        recorded_exists = bool(entry.get("exists"))
        exists_now = Path(path).exists()
        if not exists_now:
            warnings.append(f"external input is missing now: {name} ({path})")
        inspected.append(
            ExternalInputInspection(
                name=name,
                path=path,
                recorded_exists=recorded_exists,
                exists_now=exists_now,
            )
        )
    return inspected


def _artifact_id(kind: str, relative: str) -> str:
    return f"{kind}:{relative}"


_NOTES = [
    "Run inspection is read-only: it validates the run directory against its manifest and never "
    "modifies, regenerates, deletes, migrates, resumes, or replays anything.",
    "Run-relative artifacts are resolved against the inspected directory; overall validity covers "
    "artifact and stage validity for a completed run, while missing external inputs are reported "
    "separately as they live outside the run.",
]
