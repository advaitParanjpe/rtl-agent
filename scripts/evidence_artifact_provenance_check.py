"""Validate provenance/path/hash integrity across generated evidence artifacts.

This check exercises the existing production paths:

- failure-intelligence run generation
- run inspection
- evidence-bundle export
- failure-package export
- MVP demo summary generation

It intentionally does not introduce a new provenance schema. The assertions
below validate the conventions that already exist: run-relative artifact paths,
SHA-256 file hashes, index-only evidence bundles, packaged run-relative copies,
and MVP summary artifact references.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from _example_check import ROOT

from rtl_agent.artifacts import RunStore
from rtl_agent.evidence_bundle import export_evidence_bundle
from rtl_agent.evidence_bundle_models import EvidenceBundleManifest, EvidenceBundleReport
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.failure_intelligence_run_models import FailureIntelligenceRunManifest
from rtl_agent.failure_package import export_failure_package
from rtl_agent.failure_package_models import FailurePackageManifest
from rtl_agent.mvp_demo import run_mvp_demo
from rtl_agent.mvp_demo_models import MvpDemoSummary
from rtl_agent.run_inspection import inspect_run
from rtl_agent.run_inspection_models import ArtifactValidity

AXI_FIXTURE = ROOT / "examples" / "axi-stream-router"
FAILING_VCD = AXI_FIXTURE / "waveforms" / "failure.vcd"
PASSING_VCD = AXI_FIXTURE / "waveforms" / "passing.vcd"
ALLOWED_FILE = "rtl/axi_stream_router.sv"


def main() -> int:
    with TemporaryDirectory(prefix="rtl-agent-provenance-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_target_repo(workspace)

        baseline_run = _generate_failure_run(workspace, repo)
        _validate_originating_run(baseline_run, expected_run_id="baseline")

        bundle_dir = workspace / "evidence-bundle"
        bundle = export_evidence_bundle(baseline_run, bundle_dir)
        _validate_evidence_bundle(bundle_dir, bundle, baseline_run)

        package_dir = workspace / "failure-package"
        package = export_failure_package(baseline_run, package_dir)
        _validate_failure_package(package_dir, package, baseline_run)

        summary = run_mvp_demo(
            failure_run=baseline_run,
            repo=repo,
            config_path=repo / "rtl-agent.yaml",
            command="emit-vcd",
            stimulus=repo / "stimulus.json",
            allowed_files=[ALLOWED_FILE],
            output=workspace / "mvp-demo",
            max_candidates=3,
            max_experiments=3,
            timeout=30,
        )
        _validate_mvp_summary(workspace / "mvp-demo", summary)

        _negative_content_tamper_detected(baseline_run, workspace)
        _negative_unsafe_path_detected(baseline_run, workspace)

    print("evidence artifact provenance check passed")
    return 0


def _build_target_repo(workspace: Path) -> Path:
    repo = workspace / "target"
    (repo / "rtl").mkdir(parents=True)
    (repo / "sim").mkdir()
    shutil.copyfile(AXI_FIXTURE / "rtl" / "axi_stream_router.sv", repo / ALLOWED_FILE)
    shutil.copyfile(FAILING_VCD, repo / "sim" / "failing-template.vcd")
    shutil.copyfile(PASSING_VCD, repo / "sim" / "passing-template.vcd")
    (repo / "sim" / "emit_vcd.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import shutil",
                "root = Path.cwd()",
                "shutil.copyfile(root / 'sim' / 'failing-template.vcd', root / 'failing.vcd')",
                "shutil.copyfile(root / 'sim' / 'passing-template.vcd', root / 'passing.vcd')",
                "print('assertion payload_stable failed at time=40 ns')",
                "raise SystemExit(1)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "rtl-agent.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "repository_path: rtl",
                "run_artifact_dir: .rtl-agent/runs",
                "allowed_working_paths:",
                "  - .",
                "protected_paths: []",
                "execution:",
                "  timeout_seconds: 30",
                "  max_output_bytes: 1048576",
                "commands:",
                "  emit-vcd:",
                "    argv:",
                f"      - {json.dumps(sys.executable)}",
                "      - sim/emit_vcd.py",
                "    cwd: .",
                "    timeout_seconds: 30",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_json(
        repo / "stimulus.json",
        {
            "schema_version": 1,
            "items": [
                {"id": "warmup", "index": 0, "kind": "idle", "payload": {}},
                {"id": "send", "index": 1, "kind": "send", "payload": {"data": "AA"}},
                {"id": "stall", "index": 2, "kind": "stall", "payload": {}},
            ],
        },
    )

    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=fixture@local", "-c", "user.name=fixture", "commit", "-qm", "seed")
    return repo


def _generate_failure_run(workspace: Path, repo: Path) -> Path:
    store = RunStore(workspace / "runs", run_id="baseline")
    store.create()
    manifest = run_failure_intelligence(
        store,
        failing_vcd=FAILING_VCD,
        passing_vcd=PASSING_VCD,
        repository_root=repo / "rtl",
        failure_time=40,
        before=15,
        after=15,
    )
    assert manifest.status == "completed"
    assert manifest.run_id == "baseline"
    return store.run_dir


def _validate_originating_run(run_dir: Path, *, expected_run_id: str) -> None:
    manifest = FailureIntelligenceRunManifest.model_validate_json(
        (run_dir / "run-manifest.json").read_text(encoding="utf-8")
    )
    inspection = inspect_run(run_dir)
    assert inspection.valid is True
    assert inspection.manifest_run_id == expected_run_id
    assert manifest.run_id == expected_run_id
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["run_id"] == manifest.run_id

    by_path = {artifact.relative_path: artifact for artifact in manifest.artifacts}
    assert by_path
    assert len({artifact.artifact_id for artifact in manifest.artifacts}) == len(manifest.artifacts)
    for artifact in manifest.artifacts:
        assert artifact.path_kind == "run_relative"
        assert _is_safe_relative(artifact.relative_path)
        path = run_dir / artifact.relative_path
        assert path.exists() and path.is_file(), artifact.relative_path
        assert artifact.sha256 == _sha256(path)
        if artifact.schema_version is not None:
            raw = json.loads(path.read_text(encoding="utf-8"))
            assert raw["schema_version"] == artifact.schema_version

    output_paths = {
        output.path
        for stage in manifest.stages
        for output in stage.outputs
        if output.kind == "run_relative"
    }
    assert output_paths == set(by_path)
    assert manifest.failure_report_path in by_path
    assert manifest.failure_report_markdown_path in by_path


def _validate_evidence_bundle(
    bundle_dir: Path, report: EvidenceBundleReport, run_dir: Path
) -> None:
    manifest = EvidenceBundleManifest.model_validate_json(
        (bundle_dir / "manifest.json").read_text(encoding="utf-8")
    )
    persisted = EvidenceBundleReport.model_validate_json(
        (bundle_dir / "bundle.json").read_text(encoding="utf-8")
    )
    assert report.status == "passed"
    assert persisted.status == "passed"
    assert manifest.include_contents is False
    assert manifest.run_dir == run_dir.resolve()
    assert persisted.manifest_path == (bundle_dir / "manifest.json").resolve()

    by_path = {artifact.relative_path: artifact for artifact in persisted.artifacts}
    assert "run-manifest.json" in by_path
    assert "failure-report.json" in by_path
    assert all(not artifact.included_in_bundle for artifact in persisted.artifacts)
    for artifact in persisted.artifacts:
        assert _is_safe_relative(artifact.relative_path)
        expected_source = (run_dir / artifact.relative_path).resolve()
        assert artifact.source_path == expected_source
        assert artifact.exists is True
        assert artifact.sha256 == _sha256(expected_source)
        assert artifact.size_bytes == expected_source.stat().st_size
        assert artifact.provenance == f"local run artifact: {artifact.relative_path}"
        if artifact.schema_version is not None:
            raw = json.loads(expected_source.read_text(encoding="utf-8"))
            assert raw["schema_version"] == artifact.schema_version

    relocated = bundle_dir.parent / "relocated-bundle"
    shutil.copytree(bundle_dir, relocated)
    relocated_report = EvidenceBundleReport.model_validate_json(
        (relocated / "bundle.json").read_text(encoding="utf-8")
    )
    assert [artifact.relative_path for artifact in relocated_report.artifacts] == [
        artifact.relative_path for artifact in persisted.artifacts
    ]


def _validate_failure_package(
    package_dir: Path, manifest: FailurePackageManifest, run_dir: Path
) -> None:
    persisted = FailurePackageManifest.model_validate_json(
        (package_dir / "package-manifest.json").read_text(encoding="utf-8")
    )
    assert persisted == manifest
    assert persisted.package_status == "valid"
    assert persisted.verified is True
    assert persisted.run_id == "baseline"
    assert Path(persisted.source_run_dir) == run_dir.resolve()
    assert persisted.file_count == len(persisted.files)

    for item in persisted.files:
        assert _is_safe_relative(item.package_path)
        packaged = package_dir / item.package_path
        assert packaged.exists() and packaged.is_file(), item.package_path
        assert item.sha256 == _sha256(packaged)
        assert item.size_bytes == packaged.stat().st_size
        if item.run_relative_path is not None:
            assert _is_safe_relative(item.run_relative_path)
            source = run_dir / item.run_relative_path
            assert packaged.read_bytes() == source.read_bytes()
            assert item.sha256 == _sha256(source)

    package_inspection = inspect_run(package_dir / "run")
    assert package_inspection.valid is True
    assert package_inspection.manifest_run_id == persisted.run_id


def _validate_mvp_summary(output_dir: Path, summary: MvpDemoSummary) -> None:
    persisted = MvpDemoSummary.model_validate_json(
        (output_dir / "mvp-demo-summary.json").read_text(encoding="utf-8")
    )
    markdown = (output_dir / "mvp-demo-summary.md").read_text(encoding="utf-8")
    assert persisted.demo_id == summary.demo_id
    assert persisted.stages
    assert persisted.original_failure.run_valid is True
    assert persisted.original_failure.failure_package is not None
    assert persisted.original_failure.failure_package_files > 0
    assert persisted.generated_candidates
    assert persisted.experiment_outcomes
    assert persisted.experiment_comparisons
    assert persisted.intervention_rankings
    assert persisted.evidence_references

    for stage in persisted.stages:
        if stage.reference is not None:
            _assert_existing_path(stage.reference, output_dir)
            assert stage.reference in markdown

    _assert_existing_path(persisted.original_failure.failure_run, output_dir)
    _assert_existing_path(persisted.original_failure.failure_package, output_dir)
    _assert_existing_path(persisted.minimization.reduction_report, output_dir)
    assert persisted.minimization.reduction_report in markdown

    for reference in persisted.evidence_references:
        _assert_existing_path(reference.path, output_dir)
        assert reference.path in markdown

    for outcome in persisted.experiment_outcomes:
        if outcome.artifact_dir is not None:
            _assert_existing_path(outcome.artifact_dir, output_dir)

    for comparison in persisted.experiment_comparisons:
        if comparison.artifact_dir is not None:
            _assert_existing_path(comparison.artifact_dir, output_dir)
        assert (
            comparison.minimized_stimulus_digest == persisted.minimization.minimized_stimulus_digest
        )

    ranking_refs = [
        Path(ref.removeprefix("artifact:"))
        for ranking in persisted.intervention_rankings
        for ref in ranking.evidence_refs
        if "/" in ref
    ]
    for ref in ranking_refs:
        _assert_existing_path(str(ref), output_dir)

    package_manifest = FailurePackageManifest.model_validate_json(
        (Path(persisted.original_failure.failure_package) / "package-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert package_manifest.file_count == persisted.original_failure.failure_package_files


def _negative_content_tamper_detected(source_run: Path, workspace: Path) -> None:
    tampered_root = workspace / "tampered-runs"
    shutil.copytree(source_run, tampered_root / "baseline")
    tampered_run = tampered_root / "baseline"
    target = tampered_run / "waveform" / "comparison.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    inspection = inspect_run(tampered_run)
    mismatches = [
        artifact
        for artifact in inspection.artifacts
        if artifact.relative_path == "waveform/comparison.json"
    ]
    assert len(mismatches) == 1
    assert mismatches[0].validity == ArtifactValidity.HASH_MISMATCH
    assert inspection.valid is False


def _negative_unsafe_path_detected(source_run: Path, workspace: Path) -> None:
    unsafe_root = workspace / "unsafe-runs"
    shutil.copytree(source_run, unsafe_root / "baseline")
    unsafe_run = unsafe_root / "baseline"
    manifest_path = unsafe_run / "run-manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in raw["artifacts"]:
        if artifact["relative_path"] == "waveform/comparison.json":
            artifact["relative_path"] = "../escape.json"
            break
    _write_json(manifest_path, raw)

    inspection = inspect_run(unsafe_run)
    unsafe = [artifact for artifact in inspection.artifacts if artifact.validity == "unsafe_path"]
    assert len(unsafe) == 1
    assert unsafe[0].relative_path == "../escape.json"
    assert inspection.valid is False
    assert any("unsafe recorded artifact path" in warning for warning in inspection.warnings)


def _assert_existing_path(raw: str, mvp_output_dir: Path) -> Path:
    path = Path(raw)
    candidates = [path]
    if not path.is_absolute():
        candidates.extend([mvp_output_dir / path, mvp_output_dir / "matrix" / path])
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise AssertionError(raw)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _is_safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return bool(path) and not pure.is_absolute() and ".." not in pure.parts


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


if __name__ == "__main__":
    sys.exit(main())
