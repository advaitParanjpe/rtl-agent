from __future__ import annotations

import json
import shutil
from pathlib import Path

from rtl_agent.failure_intelligence_run import (
    FailureIntelligenceRunError,
    resolve_run_relative,
    sha256_file,
)
from rtl_agent.failure_package_models import (
    FailurePackageManifest,
    PackagedFile,
    PackageFileRole,
    PackageStatus,
)
from rtl_agent.run_inspection import RunInspectionError, inspect_run, write_inspection_report
from rtl_agent.run_inspection_models import RunInspectionReport

_RUN_SUBDIR = "run"
_PACKAGE_MANIFEST_NAME = "package-manifest.json"
_INSPECTION_REPORT_NAME = "inspection-report.json"
_RUN_MANIFEST_NAME = "run-manifest.json"


class FailurePackageError(RuntimeError):
    pass


def export_failure_package(
    run_dir: Path, output_dir: Path, *, allow_failed: bool = False
) -> FailurePackageManifest:
    """Package a validated run directory into a portable directory package (read-only)."""

    source_run = run_dir.resolve()
    package_dir = output_dir.resolve()
    if package_dir == source_run or package_dir.is_relative_to(source_run):
        raise FailurePackageError("package output must be outside the run directory")

    try:
        inspection = inspect_run(source_run)
    except RunInspectionError as exc:
        raise FailurePackageError(f"cannot inspect run for export: {exc}") from exc

    status = _gate_export(inspection, allow_failed=allow_failed)

    if package_dir.exists() and any(package_dir.iterdir()):
        raise FailurePackageError(f"package output directory is not empty: {package_dir}")
    (package_dir / _RUN_SUBDIR).mkdir(parents=True, exist_ok=True)

    run_manifest_raw = _load_run_manifest(source_run)
    run_id = run_manifest_raw.get("run_id")
    run_manifest_version = run_manifest_raw.get("schema_version")

    files: list[PackagedFile] = []

    # The inspection report (freshly generated) is written into the package.
    inspection_pkg = package_dir / _INSPECTION_REPORT_NAME
    write_inspection_report(inspection, inspection_pkg)
    files.append(
        _packaged_file(
            package_dir,
            inspection_pkg,
            PackageFileRole.INSPECTION_REPORT,
            kind=None,
            schema_version=inspection.schema_version,
            run_relative_path=None,
        )
    )

    # The run manifest, copied under the run subdirectory.
    run_manifest_src = source_run / _RUN_MANIFEST_NAME
    run_manifest_pkg = package_dir / _RUN_SUBDIR / _RUN_MANIFEST_NAME
    _copy(run_manifest_src, run_manifest_pkg)
    files.append(
        _packaged_file(
            package_dir,
            run_manifest_pkg,
            PackageFileRole.RUN_MANIFEST,
            kind=None,
            schema_version=run_manifest_version if isinstance(run_manifest_version, int) else None,
            run_relative_path=_RUN_MANIFEST_NAME,
        )
    )

    # Every validated, manifest-referenced artifact, at its run-relative path.
    for artifact in inspection.artifacts:
        if artifact.validity != "valid":
            continue
        source = _safe_relative(source_run, artifact.relative_path)
        package_path = package_dir / _RUN_SUBDIR / artifact.relative_path
        _copy(source, package_path)
        files.append(
            _packaged_file(
                package_dir,
                package_path,
                _artifact_role(artifact.kind),
                kind=artifact.kind,
                schema_version=artifact.actual_schema_version,
                run_relative_path=artifact.relative_path,
            )
        )

    files.sort(key=lambda item: item.package_path)
    verified = _verify_package(package_dir, files)

    manifest = FailurePackageManifest(
        package_status=status,
        run_id=str(run_id) if isinstance(run_id, str) else None,
        run_manifest_schema_version=(
            run_manifest_version if isinstance(run_manifest_version, int) else None
        ),
        source_run_dir=str(source_run),
        verified=verified,
        file_count=len(files),
        total_bytes=sum(item.size_bytes for item in files),
        files=files,
        warnings=list(inspection.warnings),
        parser_notes=[
            "This package is a self-contained, read-only export of a validated run directory; "
            "it contains only manifest-referenced artifacts that passed inspection, the run "
            "manifest, the inspection report, and the failure report (JSON and Markdown).",
            "All package paths are relative and traversal-safe; external inputs, run event logs, "
            "caches, and unrelated files are never included.",
        ],
    )
    manifest_path = package_dir / _PACKAGE_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not verified:
        raise FailurePackageError("package verification failed: a packaged file hash did not match")
    return manifest


def _gate_export(inspection: RunInspectionReport, *, allow_failed: bool) -> PackageStatus:
    if inspection.valid:
        return PackageStatus.VALID
    internally_consistent = (
        inspection.missing_artifacts == 0
        and inspection.invalid_artifacts == 0
        and all(artifact.validity != "unsafe_path" for artifact in inspection.artifacts)
    )
    if inspection.manifest_status == "failed" and internally_consistent and allow_failed:
        return PackageStatus.FAILED
    if not internally_consistent:
        raise FailurePackageError(
            "refusing to export: run has missing, invalid, or unsafe artifacts"
        )
    raise FailurePackageError(
        "refusing to export an invalid run; pass allow_failed for a "
        "failed-but-internally-consistent run"
    )


def _verify_package(package_dir: Path, files: list[PackagedFile]) -> bool:
    for item in files:
        path = package_dir / item.package_path
        if not path.exists() or sha256_file(path) != item.sha256:
            return False
    return True


def _artifact_role(kind: str) -> PackageFileRole:
    if kind == "failure_report":
        return PackageFileRole.FAILURE_REPORT
    if kind == "failure_report_markdown":
        return PackageFileRole.FAILURE_REPORT_MARKDOWN
    return PackageFileRole.EVIDENCE_ARTIFACT


def _packaged_file(
    package_dir: Path,
    path: Path,
    role: PackageFileRole,
    *,
    kind: str | None,
    schema_version: int | None,
    run_relative_path: str | None,
) -> PackagedFile:
    return PackagedFile(
        package_path=path.relative_to(package_dir).as_posix(),
        role=role,
        kind=kind,
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        schema_version=schema_version,
        run_relative_path=run_relative_path,
    )


def _copy(source: Path, destination: Path) -> None:
    if not source.exists() or not source.is_file():
        raise FailurePackageError(f"cannot package missing file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _load_run_manifest(run_dir: Path) -> dict[str, object]:
    path = run_dir / _RUN_MANIFEST_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FailurePackageError(f"run manifest is unreadable: {path}") from exc
    if not isinstance(raw, dict):
        raise FailurePackageError(f"run manifest is not a JSON object: {path}")
    return raw


def _safe_relative(run_dir: Path, relative_path: str) -> Path:
    try:
        return resolve_run_relative(run_dir, relative_path)
    except FailureIntelligenceRunError as exc:
        raise FailurePackageError(f"unsafe run-relative path: {relative_path}") from exc
