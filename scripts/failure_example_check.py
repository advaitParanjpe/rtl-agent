# ruff: noqa: E402

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtl_agent.evidence_bundle_models import EvidenceBundleReport
from rtl_agent.implementation_models import ImplementationReport
from rtl_agent.models import CommandResult
from rtl_agent.repository_map import RepositoryMap
from rtl_agent.review_models import ReviewReport
from rtl_agent.task_contract import TaskContract
from rtl_agent.triage_models import TriageReport
from rtl_agent.verification_strength_models import VerificationStrengthReport

VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
PYTHON = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rtl-agent-failure-example-") as raw_tmp:
        workspace = Path(raw_tmp)
        examples = workspace / "examples"
        shutil.copytree(ROOT / "examples", examples)

        repository_map_path = workspace / "repository-map.json"
        task_contract_path = workspace / "task-contract.json"

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
                "1",
            ],
            expected_exit=1,
        )
        assert implementation_summary["status"] == "failed"
        assert implementation_summary["failure_reason"] == (
            "validation command failed: check-define (assertion_or_test_failure)"
        )
        assert implementation_summary["validation_results"] == [
            {
                "command_name": "check-define",
                "status": "failed",
                "classification": "assertion_or_test_failure",
            }
        ]
        assert [item["decision"] for item in implementation_summary["retry_decisions"]] == ["stop"]

        implementation_report_path = Path(str(implementation_summary["output"]))
        implementation_report = ImplementationReport.model_validate_json(
            implementation_report_path.read_text(encoding="utf-8")
        )
        assert implementation_report.status == "failed"
        assert implementation_report.provider == "stub"
        assert implementation_report.iterations == 1
        assert implementation_report.applied_files == ["rtl/defs.svh"]
        assert implementation_report.failure_reason == implementation_summary["failure_reason"]
        assert implementation_report.retry_decisions[0].reason == "retry limit reached"
        assert implementation_report.diff_path is not None
        assert implementation_report.diff_path.exists()

        failed_validation = implementation_report.validation_results[0]
        assert failed_validation.command_name == "check-define"
        assert failed_validation.status == "failed"
        assert failed_validation.exit_code == 1
        assert failed_validation.classification.category == "assertion_or_test_failure"
        assert failed_validation.classification.stderr_excerpt
        assert "AssertionError" in "\n".join(failed_validation.classification.stderr_excerpt)

        failed_command_result = CommandResult.model_validate_json(
            failed_validation.result_path.read_text(encoding="utf-8")
        )
        assert failed_command_result.command_name == "check-define"
        assert failed_command_result.status == "failed"
        assert failed_command_result.exit_code == 1
        assert failed_command_result.stderr_path.exists()
        assert "AssertionError" in failed_command_result.stderr_path.read_text(encoding="utf-8")

        run_dir = implementation_report_path.parents[1]
        triage_report_path = run_dir / "triage" / "report.json"
        review_report_path = run_dir / "review" / "report.json"
        verification_strength_path = run_dir / "verification-strength" / "report.json"
        evidence_bundle_dir = workspace / "bundle"

        run_cli(
            [
                "triage-command",
                "--command-result",
                str(failed_validation.result_path),
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
        assert review_report.outcome == "unacceptable"
        assert {finding.finding_id for finding in review_report.deterministic_findings} >= {
            "det-status-not-proposed-diff",
            "det-validation-failed-1",
        }

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
        assert verification_strength.strength == "insufficient"
        assert verification_strength.validation_commands == ["check-define"]
        assert verification_strength.changed_files == ["rtl/defs.svh"]
        assert {pattern.pattern_id for pattern in verification_strength.weak_patterns} >= {
            "implementation-not-proposed-diff",
            "failed-validation-check-define",
            "failed-review",
        }

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
        artifacts_by_path = {
            artifact.relative_path: artifact for artifact in evidence_bundle.artifacts
        }
        assert "run.json" in artifacts_by_path
        assert "implementation/report.json" in artifacts_by_path
        assert "review/report.json" in artifacts_by_path
        assert "triage/report.json" in artifacts_by_path
        assert "verification-strength/report.json" in artifacts_by_path
        command_artifacts = [
            path for path in artifacts_by_path if path.startswith("commands/check-define-")
        ]
        assert any(path.endswith("/result.json") for path in command_artifacts)
        assert any(path.endswith("/stdout.log") for path in command_artifacts)
        assert any(path.endswith("/stderr.log") for path in command_artifacts)
        assert artifacts_by_path["implementation/report.json"].kind == "implementation_report"
        assert artifacts_by_path["review/report.json"].kind == "review_report"
        assert artifacts_by_path["verification-strength/report.json"].kind == (
            "verification_strength_report"
        )

    print("compact failure example check passed")
    return 0


def run_cli(args: list[str], expected_exit: int = 0) -> dict[str, Any]:
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
    if result.returncode != expected_exit:
        raise AssertionError(
            "\n".join(
                [
                    f"unexpected exit for: rtl-agent {' '.join(args)}",
                    f"expected_exit: {expected_exit}",
                    f"actual_exit: {result.returncode}",
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
