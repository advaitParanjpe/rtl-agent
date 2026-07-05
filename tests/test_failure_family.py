from __future__ import annotations

import json
from pathlib import Path

import pytest

from rtl_agent.failure_family import (
    FailureFamilyError,
    cluster_fingerprints,
    render_family_markdown,
    write_family_report,
)
from rtl_agent.failure_fingerprint import write_fingerprint_report
from rtl_agent.failure_fingerprint_models import (
    FailureFingerprintReport,
    FingerprintDigest,
)


def make_fp(
    directory: Path,
    name: str,
    *,
    family: str,
    exact: str,
    earliest: list[str] | None = None,
    assertion: list[str] | None = None,
    mapped: list[str] | None = None,
    time: list[str] | None = None,
    driver: list[str] | None = None,
    relevant: list[str] | None = None,
    insufficient: list[str] | None = None,
) -> Path:
    report = FailureFingerprintReport(
        exact_digest=exact,
        family_digest=family,
        digest=FingerprintDigest(exact=exact, family=family),
        assertion_identity=assertion or [],
        earliest_divergent_signals=earliest or [],
        ranked_relevant_signals=relevant or [],
        mapped_sources=mapped or [],
        failure_time_characteristics=time or [],
        driver_dependency_shape=driver or [],
        graph_shape=["node|x"] if not insufficient else [],
        insufficient_evidence=insufficient or [],
    )
    path = directory / name
    write_fingerprint_report(report, path)
    return path


def test_multiple_exact_duplicates(tmp_path: Path) -> None:
    paths = [
        make_fp(
            tmp_path, f"d{i}.json", family="FAM", exact="EX", earliest=["s"], mapped=["m|k|d|f|x"]
        )
        for i in range(3)
    ]
    report = cluster_fingerprints(fingerprint_paths=paths)
    assert report.input_summary.family_count == 1
    family = report.families[0]
    assert family.size == 3
    assert family.exact_duplicate_subgroups[0].size == 3
    assert report.input_summary.exact_duplicate_count == 2
    assert family.is_outlier is False


def test_time_shifted_members_one_family(tmp_path: Path) -> None:
    a = make_fp(
        tmp_path, "a.json", family="FAM", exact="EX40", earliest=["s"], time=["earliest=40"]
    )
    b = make_fp(
        tmp_path, "b.json", family="FAM", exact="EX55", earliest=["s"], time=["earliest=55"]
    )
    report = cluster_fingerprints(fingerprint_paths=[a, b])
    assert report.input_summary.family_count == 1
    family = report.families[0]
    assert family.size == 2
    assert family.observed_time_range == ["earliest_min=40", "earliest_max=55"]
    assert len(family.exact_duplicate_subgroups) == 2


def test_multiple_distinct_families(tmp_path: Path) -> None:
    a = make_fp(tmp_path, "a.json", family="FAM_A", exact="A", earliest=["sa"])
    b = make_fp(tmp_path, "b.json", family="FAM_B", exact="B", earliest=["sb"])
    report = cluster_fingerprints(fingerprint_paths=[a, b])
    assert report.input_summary.family_count == 2
    assert sorted(f.family_digest for f in report.families) == ["FAM_A", "FAM_B"]
    # Both are single-member unique outliers.
    assert report.input_summary.outlier_count == 2
    assert set(report.outliers) == {"FAM_A", "FAM_B"}


def test_changed_assertion_identity_separates_family(tmp_path: Path) -> None:
    a = make_fp(tmp_path, "a.json", family="FAM_A", exact="A", earliest=["s"], assertion=["chk_a"])
    b = make_fp(tmp_path, "b.json", family="FAM_B", exact="B", earliest=["s"], assertion=["chk_b"])
    report = cluster_fingerprints(fingerprint_paths=[a, b])
    assert report.input_summary.family_count == 2


def test_changed_earliest_divergence_mechanism_separates_family(tmp_path: Path) -> None:
    a = make_fp(tmp_path, "a.json", family="FAM_A", exact="A", earliest=["payload_out"])
    b = make_fp(tmp_path, "b.json", family="FAM_B", exact="B", earliest=["state"])
    report = cluster_fingerprints(fingerprint_paths=[a, b])
    assert report.input_summary.family_count == 2


def test_insufficient_evidence_reported_separately(tmp_path: Path) -> None:
    good = make_fp(
        tmp_path, "good.json", family="FAM", exact="EX", earliest=["s"], mapped=["m|k|d|f|x"]
    )
    weak = make_fp(
        tmp_path,
        "weak.json",
        family="WEAK",
        exact="W",
        insufficient=["missing mapped source evidence"],
    )
    report = cluster_fingerprints(fingerprint_paths=[good, weak])
    assert report.input_summary.family_count == 1
    assert report.input_summary.insufficient_evidence_count == 1
    assert report.insufficient_evidence[0].source_path.endswith("weak.json")
    assert report.insufficient_evidence[0].reasons == ["missing mapped source evidence"]


def test_related_but_nonidentical_families(tmp_path: Path) -> None:
    shared = ["lane|exact|module|rtl/lane.sv|True"]
    a = make_fp(tmp_path, "a.json", family="FAM_A", exact="A", earliest=["sa"], mapped=shared)
    b = make_fp(tmp_path, "b.json", family="FAM_B", exact="B", earliest=["sb"], mapped=shared)
    report = cluster_fingerprints(fingerprint_paths=[a, b])
    assert report.input_summary.family_count == 2
    assert len(report.related_family_links) == 1
    link = report.related_family_links[0]
    assert link.match_kind == "related_but_materially_different_failure"
    assert "mapped_sources" in link.shared_components
    assert "earliest_divergent_signals" in link.differing_components


def test_duplicate_input_files_ignored(tmp_path: Path) -> None:
    a = make_fp(tmp_path, "a.json", family="FAM", exact="EX", earliest=["s"])
    report = cluster_fingerprints(fingerprint_paths=[a, a])
    assert report.input_summary.total_inputs == 1
    assert report.input_summary.duplicate_paths_ignored == 1
    assert report.families[0].size == 1


def test_malformed_and_incompatible_input(tmp_path: Path) -> None:
    good = make_fp(tmp_path, "good.json", family="FAM", exact="EX", earliest=["s"])
    not_json = tmp_path / "bad.json"
    not_json.write_text("this is not json", encoding="utf-8")
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    wrong_version = tmp_path / "wrong.json"
    wrong_version.write_text(
        json.dumps({"family_digest": "F", "exact_digest": "E", "schema_version": 99}),
        encoding="utf-8",
    )

    report = cluster_fingerprints(
        fingerprint_paths=[good, not_json, unrelated, wrong_version], strict=False
    )
    assert report.input_summary.valid_fingerprints == 1
    assert report.input_summary.excluded_invalid == 3
    excluded_names = {Path(e.source_path).name for e in report.excluded_inputs}
    assert excluded_names == {"bad.json", "unrelated.json", "wrong.json"}


def test_strict_mode_fails_on_invalid(tmp_path: Path) -> None:
    good = make_fp(tmp_path, "good.json", family="FAM", exact="EX", earliest=["s"])
    bad = tmp_path / "bad.json"
    bad.write_text("nope", encoding="utf-8")
    with pytest.raises(FailureFamilyError):
        cluster_fingerprints(fingerprint_paths=[good, bad], strict=True)


def test_input_order_independence(tmp_path: Path) -> None:
    paths = [
        make_fp(tmp_path, "a.json", family="FAM_A", exact="A", earliest=["sa"]),
        make_fp(tmp_path, "b.json", family="FAM_A", exact="B", earliest=["sa"]),
        make_fp(tmp_path, "c.json", family="FAM_B", exact="C", earliest=["sb"]),
    ]
    forward = cluster_fingerprints(fingerprint_paths=paths).model_dump(mode="json")
    reverse = cluster_fingerprints(fingerprint_paths=list(reversed(paths))).model_dump(mode="json")
    assert forward == reverse


def test_deterministic_representative_selection(tmp_path: Path) -> None:
    complete = make_fp(
        tmp_path,
        "complete.json",
        family="FAM",
        exact="COMPLETE",
        earliest=["s"],
        assertion=["chk"],
        mapped=["m|k|d|f|x"],
        driver=["s|d|l|k|f"],
        relevant=["s|1|c"],
    )
    sparse = make_fp(tmp_path, "sparse.json", family="FAM", exact="SPARSE", earliest=["s"])
    report = cluster_fingerprints(fingerprint_paths=[sparse, complete])
    rep = report.families[0].representative
    assert rep.exact_digest == "COMPLETE"
    assert "highest evidence completeness" in rep.selection_reason


def test_stable_json_and_markdown_output(tmp_path: Path) -> None:
    paths = [
        make_fp(
            tmp_path, "a.json", family="FAM_A", exact="A", earliest=["sa"], time=["earliest=40"]
        ),
        make_fp(
            tmp_path, "b.json", family="FAM_A", exact="B", earliest=["sa"], time=["earliest=50"]
        ),
        make_fp(tmp_path, "c.json", family="FAM_B", exact="C", earliest=["sb"]),
    ]
    first = cluster_fingerprints(fingerprint_paths=paths)
    second = cluster_fingerprints(fingerprint_paths=paths)
    j1, j2 = tmp_path / "1.json", tmp_path / "2.json"
    m1, m2 = tmp_path / "1.md", tmp_path / "2.md"
    write_family_report(first, j1)
    write_family_report(second, j2)
    render_family_markdown(first, m1)
    render_family_markdown(second, m2)
    assert j1.read_text() == j2.read_text()
    assert m1.read_text() == m2.read_text()


def test_empty_input_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FailureFamilyError, match="no fingerprint inputs"):
        cluster_fingerprints(fingerprint_paths=[])


def test_fingerprint_dir_input(tmp_path: Path) -> None:
    d = tmp_path / "collected"
    d.mkdir()
    make_fp(d, "a.json", family="FAM", exact="A", earliest=["s"])
    make_fp(d, "b.json", family="FAM", exact="B", earliest=["s"])
    report = cluster_fingerprints(fingerprint_paths=[], fingerprint_dir=d)
    assert report.input_summary.total_inputs == 2
    assert report.input_summary.family_count == 1


def test_larger_synthetic_regression_set(tmp_path: Path) -> None:
    # Twenty runs across three observed mechanisms (repeated seeds) reduce to three families.
    paths: list[Path] = []
    for i in range(20):
        family = ["FAM_A", "FAM_B", "FAM_C"][i % 3]
        paths.append(
            make_fp(
                tmp_path,
                f"seed-{i:02d}.json",
                family=family,
                exact=f"{family}-{i}",
                earliest=[family.lower()],
                time=[f"earliest={40 + i}"],
            )
        )
    report = cluster_fingerprints(fingerprint_paths=paths)
    assert report.input_summary.valid_fingerprints == 20
    assert report.input_summary.family_count == 3
    assert report.input_summary.family_count < report.input_summary.valid_fingerprints


def test_counterfactual_report_participates(tmp_path: Path) -> None:
    from datetime import datetime

    from rtl_agent.artifacts import RunStore
    from rtl_agent.counterfactual_models import (
        BaselineReference,
        CounterfactualExperimentReport,
        CounterfactualOutcome,
        FailureIdentity,
        InterventionKind,
        InterventionSpec,
        WorktreeProvenance,
    )
    from rtl_agent.failure_intelligence_run import run_failure_intelligence

    axi = Path("examples/axi-stream-router")

    def build_run(root: Path, run_id: str) -> Path:
        store = RunStore(root, run_id=run_id)
        store.create()
        run_failure_intelligence(
            store,
            failing_vcd=(axi / "waveforms" / "failure.vcd").resolve(),
            passing_vcd=(axi / "waveforms" / "passing.vcd").resolve(),
            repository_root=(axi / "rtl").resolve(),
            failure_time=40,
            before=15,
            after=15,
        )
        return store.run_dir

    baseline_dir = build_run(tmp_path / "baselines", "baseline")
    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()
    build_run(experiment_dir, "intervention-run")

    report = CounterfactualExperimentReport(
        experiment_id="exp",
        created_at=datetime(2026, 7, 5),
        target_repo="repo",
        baseline=BaselineReference(run_dir=str(baseline_dir)),
        intervention=InterventionSpec(
            kind=InterventionKind.PATCH, artifact_relative_path="intervention/x.patch"
        ),
        worktree=WorktreeProvenance(source_repo="repo", worktree_path="wt"),
        baseline_failure=FailureIdentity(),
        intervention_failure=FailureIdentity(),
        outcome=CounterfactualOutcome.NO_OBSERVABLE_EFFECT,
    )
    experiment_report_path = experiment_dir / "experiment-report.json"
    experiment_report_path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")

    clustered = cluster_fingerprints(fingerprint_paths=[experiment_report_path])
    # Both the baseline run and the intervention-run were fingerprinted.
    assert clustered.input_summary.derived_from_counterfactual == 2
    assert clustered.input_summary.valid_fingerprints == 2
    # The two identical runs share one observed failure family.
    assert clustered.input_summary.family_count == 1
