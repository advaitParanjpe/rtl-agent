"""Validated adapters from existing artifact layouts into HKG source payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ValidationError

from rtl_agent.experiment_matrix_models import ExperimentMatrixReport, InterventionManifest
from rtl_agent.failure_intelligence_run import resolve_run_relative, sha256_file
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.failure_package_models import (
    FAILURE_PACKAGE_SCHEMA_VERSION,
    FailurePackageManifest,
)
from rtl_agent.hkg.builder import FailureBundle, load_failure_bundle
from rtl_agent.hkg.identity import failure_source_id, mvp_source_id
from rtl_agent.hkg.models import (
    HkgSourceArtifact,
    HkgSourceRecord,
    HkgSourceType,
    Provenance,
)
from rtl_agent.intervention_template_models import InterventionTemplateReport
from rtl_agent.mvp_demo_models import MvpDemoSummary
from rtl_agent.reduction_models import StimulusReductionReport
from rtl_agent.run_inspection import RunInspectionError, inspect_run
from rtl_agent.stimulus import StimulusError, parse_stimulus, stimulus_digest


class HkgSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class HkgSourcePayload:
    record: HkgSourceRecord
    bundle: FailureBundle


def load_failure_run_source(run_dir: Path) -> HkgSourcePayload:
    root = run_dir.resolve()
    try:
        inspection = inspect_run(root)
    except RunInspectionError as exc:
        raise HkgSourceError(f"failure source is unreadable: {root} ({exc})") from exc
    if not inspection.valid:
        raise HkgSourceError(f"failure source failed run inspection: {root}")

    manifest_path = root / "run-manifest.json"
    manifest = _read(manifest_path, FailureIntelligenceRunManifest, "run manifest")
    artifacts = [
        _source_artifact(
            "run-manifest",
            "run-manifest.json",
            manifest_path,
            manifest.schema_version,
        )
    ]
    for artifact in sorted(manifest.artifacts, key=lambda item: item.artifact_id):
        if artifact.path_kind != "run_relative":
            raise HkgSourceError(f"unsupported non-run-relative artifact: {artifact.artifact_id}")
        try:
            path = resolve_run_relative(root, artifact.relative_path)
        except Exception as exc:
            raise HkgSourceError(f"unsafe run artifact path: {artifact.relative_path}") from exc
        artifacts.append(
            _source_artifact(
                artifact.artifact_id,
                artifact.relative_path,
                path,
                artifact.schema_version,
                expected_sha256=artifact.sha256,
            )
        )
    artifacts = _sorted_artifacts(artifacts)
    source_id = failure_source_id(manifest.run_id)
    record = HkgSourceRecord(
        source_id=source_id,
        source_type=HkgSourceType.FAILURE,
        logical_id=manifest.run_id,
        content_sha256=source_content_sha256(artifacts),
        artifacts=tuple(artifacts),
    )
    bundle = load_failure_bundle(manifest.run_id, root)
    bundle.source_record = record
    bundle.manifest_prov = provenance_for(record, "run-manifest")
    return HkgSourcePayload(record=record, bundle=bundle)


def load_failure_package_source(package_dir: Path) -> HkgSourcePayload:
    root = package_dir.resolve()
    manifest_path = root / "package-manifest.json"
    package = _read(manifest_path, FailurePackageManifest, "failure package manifest")
    if package.schema_version != FAILURE_PACKAGE_SCHEMA_VERSION:
        raise HkgSourceError(f"unsupported failure package schema: {package.schema_version}")
    if not package.verified or package.file_count != len(package.files):
        raise HkgSourceError("failure package is not declared verified and complete")
    for item in package.files:
        path = _safe_path(root, item.package_path)
        _verify_file(path, item.sha256, f"packaged artifact {item.package_path}")

    payload = load_failure_run_source(root / "run")
    if package.run_id != payload.bundle.manifest.run_id:
        raise HkgSourceError("failure package run_id does not agree with its packaged run manifest")
    return payload


def load_mvp_demo_sources(demo_dir: Path) -> list[HkgSourcePayload]:
    root = demo_dir.resolve()
    required = {
        "summary": root / "mvp-demo-summary.json",
        "reduction": root / "minimization/reduction-report.json",
        "stimulus": root / "minimization/minimized-stimulus.json",
        "manifest": root / "generated/interventions.json",
        "templates": root / "generated/intervention-templates.json",
        "matrix": root / "matrix/experiment-matrix.json",
        "package": root / "failure-package/package-manifest.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise HkgSourceError(
            "unrecognized or incomplete MVP demo directory; missing: " + ", ".join(sorted(missing))
        )

    failure_payload = load_failure_package_source(root / "failure-package")
    summary = _read(required["summary"], MvpDemoSummary, "MVP summary")
    reduction = _read(required["reduction"], StimulusReductionReport, "reduction report")
    intervention_manifest = _read(
        required["manifest"], InterventionManifest, "intervention manifest"
    )
    templates = _read(required["templates"], InterventionTemplateReport, "intervention templates")
    matrix = _read(required["matrix"], ExperimentMatrixReport, "experiment matrix")
    try:
        minimized = parse_stimulus(required["stimulus"])
    except StimulusError as exc:
        raise HkgSourceError(f"minimized stimulus is invalid: {exc}") from exc

    _validate_mvp_relationships(
        failure_payload.bundle,
        summary,
        reduction,
        intervention_manifest,
        templates,
        matrix,
        minimized_digest=stimulus_digest(minimized),
    )

    artifacts = [
        _source_artifact(
            "mvp-summary", "mvp-demo-summary.json", required["summary"], summary.schema_version
        ),
        _source_artifact(
            "reduction-report",
            "minimization/reduction-report.json",
            required["reduction"],
            reduction.schema_version,
        ),
        _source_artifact(
            "minimized-stimulus",
            "minimization/minimized-stimulus.json",
            required["stimulus"],
            minimized.schema_version,
        ),
        _source_artifact(
            "interventions",
            "generated/interventions.json",
            required["manifest"],
            intervention_manifest.schema_version,
        ),
        _source_artifact(
            "intervention-templates",
            "generated/intervention-templates.json",
            required["templates"],
            templates.schema_version,
        ),
        _source_artifact(
            "experiment-matrix",
            "matrix/experiment-matrix.json",
            required["matrix"],
            matrix.schema_version,
        ),
    ]
    for row in matrix.rows:
        if row.artifact_dir is None:
            continue
        row_relative = f"matrix/{row.artifact_dir}"
        row_root = _safe_path(root, row_relative)
        result_run = row_root / "run"
        if row.result_family_digest is not None:
            try:
                result_inspection = inspect_run(result_run)
            except RunInspectionError as exc:
                raise HkgSourceError(
                    f"experiment result run is unreadable: {row_relative}/run ({exc})"
                ) from exc
            if not result_inspection.valid:
                raise HkgSourceError(f"experiment result run is invalid: {row_relative}/run")
            result_manifest = _read(
                result_run / "run-manifest.json",
                FailureIntelligenceRunManifest,
                "experiment result run manifest",
            )
            artifacts.append(
                _source_artifact(
                    f"result:{row.intervention_id}:run-manifest",
                    f"{row_relative}/run/run-manifest.json",
                    result_run / "run-manifest.json",
                    result_manifest.schema_version,
                )
            )
            for artifact in result_manifest.artifacts:
                path = resolve_run_relative(result_run, artifact.relative_path)
                artifacts.append(
                    _source_artifact(
                        f"result:{row.intervention_id}:{artifact.artifact_id}",
                        f"{row_relative}/run/{artifact.relative_path}",
                        path,
                        artifact.schema_version,
                        expected_sha256=artifact.sha256,
                    )
                )

    artifacts = _sorted_artifacts(artifacts)
    source_id = mvp_source_id(summary.target_commit, summary.demo_id)
    record = HkgSourceRecord(
        source_id=source_id,
        source_type=HkgSourceType.MVP_DEMO,
        logical_id=summary.demo_id,
        content_sha256=source_content_sha256(artifacts),
        artifacts=tuple(artifacts),
    )
    bundle = replace(
        failure_payload.bundle,
        source_record=None,
        matrix=matrix,
        matrix_prov=provenance_for(record, "experiment-matrix"),
        interventions=templates,
        interventions_prov=provenance_for(record, "intervention-templates"),
        experiment_comparisons=list(summary.experiment_comparisons),
        experiment_comparisons_prov=provenance_for(record, "mvp-summary"),
        intervention_rankings=list(summary.intervention_rankings),
        intervention_rankings_prov=provenance_for(record, "mvp-summary"),
    )
    return [failure_payload, HkgSourcePayload(record=record, bundle=bundle)]


def provenance_for(record: HkgSourceRecord, artifact_id: str) -> Provenance:
    artifact = next((item for item in record.artifacts if item.artifact_id == artifact_id), None)
    if artifact is None:
        raise HkgSourceError(f"source artifact is not indexed: {record.source_id}:{artifact_id}")
    return Provenance(
        source_id=record.source_id,
        artifact_id=artifact.artifact_id,
        schema_version=artifact.schema_version,
        content_sha256=artifact.sha256,
        path=artifact.relative_path,
    )


def source_content_sha256(artifacts: list[HkgSourceArtifact]) -> str:
    payload = [artifact.model_dump(mode="json") for artifact in _sorted_artifacts(artifacts)]
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return sha256(encoded).hexdigest()


def _validate_mvp_relationships(
    failure: FailureBundle,
    summary: MvpDemoSummary,
    reduction: StimulusReductionReport,
    intervention_manifest: InterventionManifest,
    templates: InterventionTemplateReport,
    matrix: ExperimentMatrixReport,
    *,
    minimized_digest: str,
) -> None:
    if summary.original_failure.exact_digest != failure.fingerprint.exact_digest:
        raise HkgSourceError("MVP summary baseline exact digest does not match packaged failure")
    if summary.original_failure.family_digest != failure.fingerprint.family_digest:
        raise HkgSourceError("MVP summary baseline family digest does not match packaged failure")
    digests = {
        summary.minimization.minimized_stimulus_digest,
        reduction.minimized_stimulus_digest,
        matrix.minimized_stimulus_digest,
        minimized_digest,
    }
    if len(digests) != 1:
        raise HkgSourceError("MVP minimized-stimulus digests do not agree")
    template_ids = [candidate.candidate_id for candidate in templates.candidates]
    manifest_ids = [entry.id for entry in intervention_manifest.interventions]
    summary_ids = [candidate.candidate_id for candidate in summary.generated_candidates]
    row_ids = [row.intervention_id for row in matrix.rows]
    if template_ids != manifest_ids or template_ids != summary_ids or row_ids != template_ids:
        raise HkgSourceError("MVP intervention identifiers do not agree across artifacts")
    if [outcome.intervention_id for outcome in summary.experiment_outcomes] != row_ids:
        raise HkgSourceError("MVP outcome identifiers do not agree with matrix rows")
    if [comparison.intervention_id for comparison in summary.experiment_comparisons] != row_ids:
        raise HkgSourceError("MVP comparison identifiers do not agree with matrix rows")
    if sorted(ranking.intervention_id for ranking in summary.intervention_rankings) != sorted(
        row_ids
    ):
        raise HkgSourceError("MVP ranking identifiers do not agree with matrix rows")
    if matrix.baseline_exact_digest != failure.fingerprint.exact_digest:
        raise HkgSourceError("MVP matrix baseline exact digest does not match packaged failure")
    if templates.baseline_exact_digest != failure.fingerprint.exact_digest:
        raise HkgSourceError("MVP template baseline exact digest does not match packaged failure")
    if (
        summary.target_commit != matrix.target_commit
        or summary.target_commit != templates.target_commit
    ):
        raise HkgSourceError("MVP target commits do not agree")


def _source_artifact(
    artifact_id: str,
    relative_path: str,
    path: Path,
    schema_version: int | None,
    *,
    expected_sha256: str | None = None,
) -> HkgSourceArtifact:
    if not _safe_relative(relative_path):
        raise HkgSourceError(f"unsafe source-relative path: {relative_path}")
    if not path.is_file():
        raise HkgSourceError(f"missing source artifact: {relative_path}")
    digest = sha256_file(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise HkgSourceError(
            f"source artifact hash mismatch: {relative_path} "
            f"(expected {expected_sha256}, actual {digest})"
        )
    return HkgSourceArtifact(
        artifact_id=artifact_id,
        relative_path=relative_path,
        schema_version=schema_version,
        sha256=digest,
    )


def _safe_path(root: Path, relative_path: str) -> Path:
    if not _safe_relative(relative_path):
        raise HkgSourceError(f"unsafe source-relative path: {relative_path}")
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise HkgSourceError(f"source-relative path escapes root: {relative_path}")
    return path


def _safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return bool(path) and not pure.is_absolute() and ".." not in pure.parts


def _verify_file(path: Path, expected_sha256: str, label: str) -> None:
    if not path.is_file():
        raise HkgSourceError(f"missing {label}: {path}")
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise HkgSourceError(f"{label} hash mismatch (expected {expected_sha256}, actual {actual})")


def _sorted_artifacts(artifacts: list[HkgSourceArtifact]) -> list[HkgSourceArtifact]:
    ordered = sorted(artifacts, key=lambda item: (item.artifact_id, item.relative_path))
    keys = [(item.artifact_id, item.relative_path) for item in ordered]
    if len(keys) != len(set(keys)):
        raise HkgSourceError("duplicate source artifact identity")
    return ordered


def _read[ModelT: BaseModel](path: Path, model: type[ModelT], label: str) -> ModelT:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise HkgSourceError(f"{label} is unreadable: {path} ({exc})") from exc
