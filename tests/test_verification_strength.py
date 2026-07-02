from __future__ import annotations

import json
from pathlib import Path

from test_review import make_review_inputs

from rtl_agent.review import review_implementation, write_review_report
from rtl_agent.verification_strength import (
    assess_verification_strength,
    write_verification_strength_report,
)


def test_strength_report_is_stable_json_for_same_inputs(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path
    )
    review_report = review_implementation(
        task_contract_path, repository_map_path, implementation_report_path
    )
    review_report_path = tmp_path / "review.json"
    write_review_report(review_report, review_report_path)
    report = assess_verification_strength(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
        review_report_path=review_report_path,
    )
    first = tmp_path / "first-strength.json"
    second = tmp_path / "second-strength.json"

    write_verification_strength_report(report, first)
    write_verification_strength_report(report, second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == 1


def test_failed_validation_is_insufficient(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path, validation_assertion="'missing_signal' in Path('rtl/top.sv').read_text()"
    )

    report = assess_verification_strength(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
    )

    assert report.strength == "insufficient"
    assert any(
        pattern.pattern_id.startswith("failed-validation") for pattern in report.weak_patterns
    )


def test_unacceptable_review_is_insufficient(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path, validation_assertion="'missing_signal' in Path('rtl/top.sv').read_text()"
    )
    review_report = review_implementation(
        task_contract_path, repository_map_path, implementation_report_path
    )
    review_report_path = tmp_path / "review.json"
    write_review_report(review_report, review_report_path)

    report = assess_verification_strength(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
        review_report_path=review_report_path,
    )

    assert report.strength == "insufficient"
    assert any(pattern.pattern_id == "failed-review" for pattern in report.weak_patterns)


def test_relevant_passing_validation_scores_above_smoke_only(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, _repo = make_review_inputs(
        tmp_path
    )
    relevant = assess_verification_strength(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
    )
    data = json.loads(implementation_report_path.read_text(encoding="utf-8"))
    result_path = Path(data["validation_results"][0]["result_path"])
    command_result = json.loads(result_path.read_text(encoding="utf-8"))
    command_result["command_name"] = "smoke"
    command_result["argv"] = ["python3", "-c", "pass"]
    result_path.write_text(json.dumps(command_result), encoding="utf-8")
    data["validation_results"][0]["command_name"] = "smoke"
    data["validation_results"][0]["classification"]["summary"] = "passed"
    data["validation_results"][0]["classification"]["evidence"] = []
    implementation_report_path.write_text(json.dumps(data), encoding="utf-8")

    smoke = assess_verification_strength(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
    )

    assert relevant.score > smoke.score
    assert any(pattern.pattern_id == "only-smoke-validation" for pattern in smoke.weak_patterns)


def test_assessment_does_not_mutate_source_files(tmp_path: Path) -> None:
    task_contract_path, repository_map_path, implementation_report_path, repo = make_review_inputs(
        tmp_path
    )
    source_path = repo / "rtl" / "top.sv"
    before = source_path.read_text(encoding="utf-8")

    assess_verification_strength(
        task_contract_path=task_contract_path,
        repository_map_path=repository_map_path,
        implementation_report_path=implementation_report_path,
    )

    assert source_path.read_text(encoding="utf-8") == before
