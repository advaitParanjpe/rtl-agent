from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from rtl_agent.benchmark_models import BenchmarkReport
from rtl_agent.evidence_bundle_models import EvidenceBundleReport
from rtl_agent.implementation_models import ImplementationReport
from rtl_agent.models import CommandResult
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.review_models import ReviewReport
from rtl_agent.task_contract import TaskContract
from rtl_agent.triage_models import TriageReport
from rtl_agent.verification_strength_models import VerificationStrengthReport

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rtl-agent-e2e-") as raw_tmp:
        workspace = Path(raw_tmp)
        examples = workspace / "examples"
        shutil.copytree(ROOT / "examples", examples)

        repository_map_path = workspace / "repository-map.json"
        task_contract_path = workspace / "task-contract.json"
        triage_report_path = workspace / "triage-report.json"
        review_report_path = workspace / "review-report.json"
        verification_strength_path = workspace / "verification-strength.json"
        evidence_bundle_dir = workspace / "bundle"

        run_cli(
            [
                "inspect-repo",
                "--repo",
                str(examples / "simple-rtl"),
                "--config",
                str(examples / "simple-rtl-agent.yaml"),
                "--output",
                str(repository_map_path),
            ]
        )
        repository_map = RepositoryMap.model_validate_json(
            repository_map_path.read_text(encoding="utf-8")
        )
        assert repository_map.schema_version == 1
        assert repository_map.scan_statistics.files_indexed > 0
        assert any(record.path == "rtl/defs.svh" for record in repository_map.files)

        run_cli(
            [
                "parse-issue",
                "--issue",
                str(examples / "issues" / "define-value.md"),
                "--repository-map",
                str(repository_map_path),
                "--output",
                str(task_contract_path),
            ]
        )
        task_contract = TaskContract.model_validate_json(
            task_contract_path.read_text(encoding="utf-8")
        )
        assert task_contract.schema_version == 1
        assert [item.value for item in task_contract.scoped_repository_context] == ["rtl/defs.svh"]
        assert len(task_contract.acceptance_criteria) == 1

        implementation_summary = run_cli(
            [
                "implement-task",
                "--config",
                str(examples / "simple-rtl-agent.yaml"),
                "--task-contract",
                str(task_contract_path),
                "--repository-map",
                str(repository_map_path),
                "--provider-plan",
                str(examples / "provider-plans" / "retry-after-failure.json"),
                "--allowed-file",
                "rtl/defs.svh",
                "--validation-command",
                "check-define",
                "--max-iterations",
                "2",
            ]
        )
        implementation_report_path = Path(str(implementation_summary["output"]))
        implementation_report = ImplementationReport.model_validate_json(
            implementation_report_path.read_text(encoding="utf-8")
        )
        assert implementation_report.status == "proposed_diff"
        assert implementation_report.provider == "stub"
        assert implementation_report.iterations == 2
        assert implementation_report.applied_files == ["rtl/defs.svh"]
        assert [result.status for result in implementation_report.validation_results] == [
            "failed",
            "passed",
        ]
        assert [
            result.classification.category for result in implementation_report.validation_results
        ] == [
            "assertion_or_test_failure",
            "passed",
        ]
        assert [decision.decision for decision in implementation_report.retry_decisions] == [
            "retry"
        ]
        assert implementation_report.diff_path is not None
        assert implementation_report.diff_path.exists()
        assert (examples / "simple-rtl" / "rtl" / "defs.svh").read_text(
            encoding="utf-8"
        ) == "`define SIMPLE_RTL_EXAMPLE 1\n"

        failed_command_result_path = implementation_report.validation_results[0].result_path
        failed_command_result = CommandResult.model_validate_json(
            failed_command_result_path.read_text(encoding="utf-8")
        )
        assert failed_command_result.command_name == "check-define"
        assert failed_command_result.status == "failed"

        run_cli(
            [
                "triage-command",
                "--command-result",
                str(failed_command_result_path),
                "--output",
                str(triage_report_path),
            ]
        )
        triage_report = TriageReport.model_validate_json(
            triage_report_path.read_text(encoding="utf-8")
        )
        assert triage_report.command_name == "check-define"
        assert triage_report.command_status == "failed"

        run_cli(
            [
                "review-task",
                "--task-contract",
                str(task_contract_path),
                "--repository-map",
                str(repository_map_path),
                "--implementation-report",
                str(implementation_report_path),
                "--triage-report",
                str(triage_report_path),
                "--output",
                str(review_report_path),
            ]
        )
        review_report = ReviewReport.model_validate_json(
            review_report_path.read_text(encoding="utf-8")
        )
        assert review_report.outcome == "acceptable"
        assert review_report.checked_files == ["rtl/defs.svh"]

        run_cli(
            [
                "assess-verification",
                "--task-contract",
                str(task_contract_path),
                "--repository-map",
                str(repository_map_path),
                "--implementation-report",
                str(implementation_report_path),
                "--review-report",
                str(review_report_path),
                "--triage-report",
                str(triage_report_path),
                "--output",
                str(verification_strength_path),
            ]
        )
        verification_strength = VerificationStrengthReport.model_validate_json(
            verification_strength_path.read_text(encoding="utf-8")
        )
        assert verification_strength.strength in {"moderate", "strong"}
        assert verification_strength.validation_commands == ["check-define"]
        assert verification_strength.changed_files == ["rtl/defs.svh"]

        benchmark_summary = run_cli(
            [
                "run-benchmark",
                "--manifest",
                str(examples / "benchmarks" / "local-smoke.yaml"),
                "--fail-on-unmet-expected",
            ]
        )
        benchmark_report = BenchmarkReport.model_validate_json(
            Path(str(benchmark_summary["output"])).read_text(encoding="utf-8")
        )
        assert benchmark_report.status == "passed"
        assert benchmark_report.cases_total == 2
        assert benchmark_report.cases_passed == 2
        assert all(case.expectation_met for case in benchmark_report.case_results)

        run_dir = implementation_report_path.parents[1]
        evidence_summary = run_cli(
            [
                "export-evidence",
                "--run-dir",
                str(run_dir),
                "--output-dir",
                str(evidence_bundle_dir),
                "--fail-on-failed-export",
            ]
        )
        evidence_bundle = EvidenceBundleReport.model_validate_json(
            Path(str(evidence_summary["output"])).read_text(encoding="utf-8")
        )
        assert evidence_bundle.status == "passed"
        assert (evidence_bundle_dir / "manifest.json").exists()
        assert (evidence_bundle_dir / "bundle.json").exists()
        artifact_paths = {artifact.relative_path for artifact in evidence_bundle.artifacts}
        assert "run.json" in artifact_paths
        assert "implementation/report.json" in artifact_paths
        assert any(path.startswith("commands/check-define-") for path in artifact_paths)

    print("compact end-to-end example check passed")
    return 0


def run_cli(args: list[str]) -> dict[str, Any]:
    env = os.environ.copy()
    src = str(ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src if not existing_pythonpath else f"{src}{os.pathsep}{existing_pythonpath}"
    )
    result = subprocess.run(
        [str(PYTHON), "-m", "rtl_agent", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "\n".join(
                [
                    f"command failed: rtl-agent {' '.join(args)}",
                    f"exit_code: {result.returncode}",
                    "stdout:",
                    result.stdout[-4000:],
                    "stderr:",
                    result.stderr[-4000:],
                ]
            )
        )
    return cast(dict[str, Any], json.loads(result.stdout))


if __name__ == "__main__":
    sys.exit(main())
