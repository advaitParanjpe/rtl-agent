from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rtl_agent.artifacts import RunStore
from rtl_agent.experiment_matrix import ExperimentMatrixError, run_experiment_matrix
from rtl_agent.experiment_matrix_models import ExperimentMatrixReport, MatrixRow
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.stimulus import parse_stimulus, stimulus_digest

CORE_SV = """module core (
    input  logic       clk,
    output logic [7:0] payload_out,
    output logic       valid_out
);
    // FAULT_ACTIVE
    // BENIGN_LINE
endmodule
"""

_VCD_HEADER = (
    "$timescale 1ns $end\n"
    "$scope module tb $end\n"
    "$scope module core $end\n"
    "$var reg 8 ! payload_out [7:0] $end\n"
    '$var reg 1 " valid_out $end\n'
    "$upscope $end\n$upscope $end\n$enddefinitions $end\n"
    '$dumpvars\nb00000000 !\n0"\n$end\n'
    '#30\nb10101010 !\n1"\n'
)


def _make_vcd(path: Path, *, payload_x: bool, valid_x: bool, at: int = 40) -> Path:
    body = _VCD_HEADER + f"#{at}\n"
    if payload_x:
        body += "bxxxxxxxx !\n"
    if valid_x:
        body += 'x"\n'
    body += f"#{at + 10}\n"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def waveforms(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("waveforms")
    return {
        "fam_a": _make_vcd(root / "fam_a.vcd", payload_x=True, valid_x=False),
        "fam_a_late": _make_vcd(root / "fam_a_late.vcd", payload_x=True, valid_x=False, at=50),
        "fam_b": _make_vcd(root / "fam_b.vcd", payload_x=False, valid_x=True),
        "clean": _make_vcd(root / "clean.vcd", payload_x=False, valid_x=False),
    }


@pytest.fixture(scope="module")
def baseline(tmp_path_factory: pytest.TempPathFactory, waveforms: dict[str, Path]) -> Path:
    rtl = tmp_path_factory.mktemp("baseline-rtl")
    (rtl / "rtl").mkdir()
    (rtl / "rtl" / "core.sv").write_text(CORE_SV, encoding="utf-8")
    store = RunStore(tmp_path_factory.mktemp("baseline-run"), run_id="baseline")
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=waveforms["fam_a"],
        passing_vcd=waveforms["clean"],
        repository_root=rtl / "rtl",
        failure_time=40,
        before=15,
        after=15,
    )
    return store.run_dir


def _command(waveforms: dict[str, Path]) -> list[str]:
    a, a_late, b, clean = (
        waveforms["fam_a"],
        waveforms["fam_a_late"],
        waveforms["fam_b"],
        waveforms["clean"],
    )
    core = "rtl/core.sv"
    script = (
        f"if grep -q SLOWDOWN {core}; then sleep 5; fi; "
        f"if grep -q BOOM {core}; then echo boom >&2; exit 7; fi; "
        f"if grep -q FAULT_DIFFERENT {core}; then F='{b}'; "
        f"elif grep -q FAULT_LATE {core}; then F='{a_late}'; "
        f"elif grep -q FAULT_ACTIVE {core}; then F='{a}'; "
        f"else F='{clean}'; fi; "
        f"cp \"$F\" failing.vcd; cp '{clean}' passing.vcd; "
        f'echo "VCD info: dumpfile failing.vcd opened"'
    )
    return ["sh", "-c", script]


def _make_repo(tmp_path: Path, argv: list[str], *, timeout: int = 60) -> tuple[Path, Path]:
    repo = tmp_path / "target"
    (repo / "rtl").mkdir(parents=True)
    (repo / "sim").mkdir(parents=True)
    (repo / "rtl" / "core.sv").write_text(CORE_SV, encoding="utf-8")
    (repo / "sim" / "stimulus.mem").write_text("0000\n", encoding="utf-8")
    config = {
        "schema_version": 1,
        "repository_path": "rtl",
        "run_artifact_dir": ".rtl-agent/runs",
        "allowed_working_paths": ["."],
        "protected_paths": [],
        "execution": {"timeout_seconds": timeout},
        "commands": {"sim": {"argv": argv, "cwd": ".", "timeout_seconds": timeout}},
    }
    config_path = repo / "rtl-agent.yaml"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        check=True,
    )
    return repo, config_path


def _reduction(tmp_path: Path) -> Path:
    reduction_dir = tmp_path / "min"
    reduction_dir.mkdir(parents=True)
    stimulus = {
        "schema_version": 1,
        "items": [{"id": "s0", "index": 0, "kind": "stall", "payload": {}}],
    }
    stim_path = reduction_dir / "minimized-stimulus.json"
    stim_path.write_text(json.dumps(stimulus), encoding="utf-8")
    digest = stimulus_digest(parse_stimulus(stim_path))
    report = {"schema_version": 1, "minimized_stimulus_digest": digest}
    report_path = reduction_dir / "reduction-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path


def _manifest(tmp_path: Path, interventions: list[dict[str, object]]) -> Path:
    path = tmp_path / "interventions.json"
    path.write_text(
        json.dumps({"schema_version": 1, "interventions": interventions}), encoding="utf-8"
    )
    return path


def _replace(id_: str, old: str, new: str, **kw: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": id_,
        "allowed_files": ["rtl/core.sv"],
        "replace": {"file": "rtl/core.sv", "old": old, "new": new},
    }
    entry.update(kw)
    return entry


def _run(
    baseline: Path,
    repo: Path,
    config: Path,
    reduction: Path,
    manifest: Path,
    tmp_path: Path,
    max_experiments: int = 12,
) -> ExperimentMatrixReport:
    return run_experiment_matrix(
        baseline_run=baseline,
        reduction_report=reduction,
        repo=repo,
        config_path=config,
        command="sim",
        interventions=manifest,
        output=tmp_path / "out",
        max_experiments=max_experiments,
    )


def _rows(report: ExperimentMatrixReport) -> dict[str, MatrixRow]:
    return {row.intervention_id: row for row in report.rows}


# --------------------------------------------------------------------------- #
# Manifest validation.
# --------------------------------------------------------------------------- #


def test_duplicate_intervention_ids_rejected(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, ["true"])
    reduction = _reduction(tmp_path)
    manifest = _manifest(
        tmp_path,
        [
            _replace("dup", "// FAULT_ACTIVE", "// FAULT_REMOVED"),
            _replace("dup", "// BENIGN_LINE", "// BENIGN_EDIT"),
        ],
    )
    with pytest.raises(ExperimentMatrixError, match="duplicate intervention id"):
        _run(baseline, repo, config, reduction, manifest, tmp_path)


def test_intervention_requires_patch_or_replace(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, ["true"])
    reduction = _reduction(tmp_path)
    manifest = _manifest(tmp_path, [{"id": "x", "allowed_files": ["rtl/core.sv"]}])
    with pytest.raises(ExperimentMatrixError, match="exactly one of patch or replace"):
        _run(baseline, repo, config, reduction, manifest, tmp_path)


def test_malformed_baseline_rejected(tmp_path: Path, baseline: Path) -> None:
    corrupt = tmp_path / "corrupt"
    shutil.copytree(baseline, corrupt)
    (corrupt / "signal-source-map.json").write_text("corrupt", encoding="utf-8")
    repo, config = _make_repo(tmp_path, ["true"])
    reduction = _reduction(tmp_path)
    manifest = _manifest(tmp_path, [_replace("a", "// FAULT_ACTIVE", "// FAULT_REMOVED")])
    with pytest.raises(ExperimentMatrixError, match="invalid baseline"):
        _run(corrupt, repo, config, reduction, manifest, tmp_path)


def test_stimulus_reduction_mismatch_rejected(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, ["true"])
    reduction = _reduction(tmp_path)
    # Corrupt the recorded digest so it no longer matches the stimulus.
    report = json.loads((reduction).read_text(encoding="utf-8"))
    report["minimized_stimulus_digest"] = "0" * 64
    reduction.write_text(json.dumps(report), encoding="utf-8")
    manifest = _manifest(tmp_path, [_replace("a", "// FAULT_ACTIVE", "// FAULT_REMOVED")])
    with pytest.raises(ExperimentMatrixError, match="does not match the reduction report digest"):
        _run(baseline, repo, config, reduction, manifest, tmp_path)


# --------------------------------------------------------------------------- #
# Execution and classification.
# --------------------------------------------------------------------------- #


def test_outcomes_and_ordering(tmp_path: Path, baseline: Path, waveforms: dict[str, Path]) -> None:
    repo, config = _make_repo(tmp_path, _command(waveforms))
    reduction = _reduction(tmp_path)
    before = _repo_state(repo)
    manifest = _manifest(
        tmp_path,
        [
            _replace("remove", "// FAULT_ACTIVE", "// FAULT_REMOVED", tags=["fix"]),
            _replace("benign", "// BENIGN_LINE", "// BENIGN_EDIT"),
            _replace("late", "// FAULT_ACTIVE", "// FAULT_LATE"),
            _replace("different", "// FAULT_ACTIVE", "// FAULT_DIFFERENT"),
            _replace("disabled", "// BENIGN_LINE", "// OFF", enabled=False),
        ],
    )
    report = _run(baseline, repo, config, reduction, manifest, tmp_path, max_experiments=12)

    # Row ordering follows the manifest, not filesystem enumeration.
    assert [r.intervention_id for r in report.rows] == [
        "remove",
        "benign",
        "late",
        "different",
        "disabled",
    ]
    rows = _rows(report)
    assert rows["remove"].failure_removed is True
    assert rows["remove"].counterfactual_outcome == "failure_removed"
    assert rows["benign"].counterfactual_outcome == "no_observable_effect"
    assert rows["benign"].fingerprint_relation == "exact"
    assert rows["benign"].family_preserved is True
    # A later divergence on the same signal is classified as a timing shift.
    assert rows["late"].failure_time_shifted is True
    assert rows["late"].counterfactual_outcome == "failure_delayed"
    assert rows["late"].result_failure_signals == rows["benign"].result_failure_signals
    assert rows["different"].different_failure is True
    assert rows["disabled"].execution_status == "skipped"
    # The source repository is unchanged.
    assert _repo_state(repo) == before


def test_disallowed_file_is_invalid_row(
    tmp_path: Path, baseline: Path, waveforms: dict[str, Path]
) -> None:
    repo, config = _make_repo(tmp_path, _command(waveforms))
    reduction = _reduction(tmp_path)
    manifest = _manifest(
        tmp_path,
        [
            {
                "id": "escape",
                "allowed_files": ["rtl/core.sv"],
                "replace": {"file": "rtl/other.sv", "old": "a", "new": "b"},
            }
        ],
    )
    report = _run(baseline, repo, config, reduction, manifest, tmp_path)
    assert _rows(report)["escape"].execution_status == "invalid"


def test_patch_application_failure_is_invalid_row(
    tmp_path: Path, baseline: Path, waveforms: dict[str, Path]
) -> None:
    repo, config = _make_repo(tmp_path, _command(waveforms))
    reduction = _reduction(tmp_path)
    bad_patch = "--- a/rtl/core.sv\n+++ b/rtl/core.sv\n@@ -1 +1 @@\n-nonexistent line\n+x\n"
    manifest = _manifest(
        tmp_path, [{"id": "bad", "allowed_files": ["rtl/core.sv"], "patch": bad_patch}]
    )
    report = _run(baseline, repo, config, reduction, manifest, tmp_path)
    assert _rows(report)["bad"].execution_status == "invalid"


def test_reference_failure_aborts(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, ["sh", "-c", "exit 5"])
    reduction = _reduction(tmp_path)
    manifest = _manifest(tmp_path, [_replace("x", "// BENIGN_LINE", "// BENIGN_EDIT")])
    # The reference run itself fails to produce a fingerprint, so the whole matrix errors.
    with pytest.raises(ExperimentMatrixError, match="did not reproduce"):
        _run(baseline, repo, config, reduction, manifest, tmp_path)


def test_intervention_execution_failure_row(
    tmp_path: Path, baseline: Path, waveforms: dict[str, Path]
) -> None:
    repo, config = _make_repo(tmp_path, _command(waveforms))
    reduction = _reduction(tmp_path)
    manifest = _manifest(tmp_path, [_replace("boom", "// BENIGN_LINE", "// BOOM")])
    report = _run(baseline, repo, config, reduction, manifest, tmp_path)
    row = _rows(report)["boom"]
    assert row.execution_status == "executed"
    assert row.command_status == "failed"
    assert row.result_family_digest is None
    assert row.counterfactual_outcome in {"experiment_failed", "insufficient_evidence"}


def test_intervention_timeout_row(
    tmp_path: Path, baseline: Path, waveforms: dict[str, Path]
) -> None:
    repo, config = _make_repo(tmp_path, _command(waveforms), timeout=1)
    reduction = _reduction(tmp_path)
    manifest = _manifest(tmp_path, [_replace("slow", "// BENIGN_LINE", "// SLOWDOWN")])
    report = run_experiment_matrix(
        baseline_run=baseline,
        reduction_report=reduction,
        repo=repo,
        config_path=config,
        command="sim",
        interventions=manifest,
        output=tmp_path / "out",
        timeout=1,
    )
    row = _rows(report)["slow"]
    assert row.command_status == "timeout"
    assert row.result_family_digest is None


def test_maximum_experiment_bound(
    tmp_path: Path, baseline: Path, waveforms: dict[str, Path]
) -> None:
    repo, config = _make_repo(tmp_path, _command(waveforms))
    reduction = _reduction(tmp_path)
    manifest = _manifest(
        tmp_path,
        [
            _replace("a", "// FAULT_ACTIVE", "// FAULT_DIFFERENT"),
            _replace("b", "// BENIGN_LINE", "// BENIGN_EDIT"),
            _replace("c", "// FAULT_ACTIVE", "// FAULT_REMOVED"),
        ],
    )
    report = _run(baseline, repo, config, reduction, manifest, tmp_path, max_experiments=1)
    assert report.summary.executed == 1
    statuses = [r.execution_status for r in report.rows]
    assert statuses == ["executed", "skipped", "skipped"]
    assert "budget" in (report.rows[1].detail or "")


def test_semantic_duplicate_caching(
    tmp_path: Path, baseline: Path, waveforms: dict[str, Path]
) -> None:
    repo, config = _make_repo(tmp_path, _command(waveforms))
    reduction = _reduction(tmp_path)
    manifest = _manifest(
        tmp_path,
        [
            _replace("first", "// FAULT_ACTIVE", "// FAULT_REMOVED"),
            _replace("second", "// FAULT_ACTIVE", "// FAULT_REMOVED"),
        ],
    )
    report = _run(baseline, repo, config, reduction, manifest, tmp_path)
    rows = _rows(report)
    assert rows["first"].from_cache is False
    assert rows["second"].from_cache is True
    assert report.summary.cache_hits == 1
    assert report.summary.executed == 1


def test_stable_serialization(tmp_path: Path, baseline: Path, waveforms: dict[str, Path]) -> None:
    repo, config = _make_repo(tmp_path, _command(waveforms))
    reduction = _reduction(tmp_path)
    manifest = _manifest(
        tmp_path,
        [
            _replace("remove", "// FAULT_ACTIVE", "// FAULT_REMOVED"),
            _replace("different", "// FAULT_ACTIVE", "// FAULT_DIFFERENT"),
        ],
    )

    def normalized(name: str) -> list[tuple[object, ...]]:
        report = run_experiment_matrix(
            baseline_run=baseline,
            reduction_report=reduction,
            repo=repo,
            config_path=config,
            command="sim",
            interventions=manifest,
            output=tmp_path / name,
            max_experiments=12,
        )
        return [
            (
                r.intervention_id,
                r.execution_status,
                r.counterfactual_outcome,
                r.fingerprint_relation,
                r.result_family_digest,
                r.failure_removed,
                r.different_failure,
            )
            for r in report.rows
        ]

    assert normalized("a") == normalized("b")


def _repo_state(repo: Path) -> tuple[str, dict[str, str]]:
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    files = {
        p.relative_to(repo).as_posix(): p.read_bytes().hex()
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git" not in p.parts
    }
    return head, files
