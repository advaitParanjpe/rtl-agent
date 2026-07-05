from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rtl_agent.artifacts import RunStore
from rtl_agent.counterfactual import CounterfactualError, classify_outcome, run_counterfactual
from rtl_agent.counterfactual.service import _observable_differences
from rtl_agent.counterfactual_models import CounterfactualOutcome, FailureIdentity
from rtl_agent.failure_intelligence_run import run_failure_intelligence

AXI = Path("examples/axi-stream-router")
AXI_FAIL = AXI / "waveforms" / "failure.vcd"
AXI_PASS = AXI / "waveforms" / "passing.vcd"
AXI_RTL = AXI / "rtl"
FIXTURE_RTL = Path("examples/counterfactual-axi/rtl/axi_pipe.sv")

FAULT_LINE = "payload_reg <= 'x;"


# --------------------------------------------------------------------------- #
# Deterministic classifier unit tests (pure, no filesystem).
# --------------------------------------------------------------------------- #


def _identity(signals: list[str], time: int | None, present: bool | None = None) -> FailureIdentity:
    return FailureIdentity(
        signals=signals,
        failure_time=time,
        divergence_present=bool(signals) if present is None else present,
    )


def _classify(
    command_status: str, evidence: bool, baseline: FailureIdentity, intervention: FailureIdentity
) -> CounterfactualOutcome:
    return classify_outcome(
        command_status=command_status,
        intervention_evidence_valid=evidence,
        baseline=baseline,
        intervention=intervention,
    )[0]


BASE = _identity(["sig_a"], 40)


def test_classify_failure_removed() -> None:
    assert (
        _classify("passed", True, BASE, _identity([], None))
        == CounterfactualOutcome.FAILURE_REMOVED
    )


def test_classify_no_observable_effect() -> None:
    assert _classify("passed", True, BASE, _identity(["sig_a"], 40)) == (
        CounterfactualOutcome.NO_OBSERVABLE_EFFECT
    )


def test_classify_advanced_and_delayed() -> None:
    assert _classify("passed", True, BASE, _identity(["sig_a"], 30)) == (
        CounterfactualOutcome.FAILURE_ADVANCED
    )
    assert _classify("passed", True, BASE, _identity(["sig_a"], 55)) == (
        CounterfactualOutcome.FAILURE_DELAYED
    )


def test_classify_failure_changed_on_overlapping_signals() -> None:
    intervention = _identity(["sig_a", "sig_b"], 40)
    assert _classify("passed", True, BASE, intervention) == CounterfactualOutcome.FAILURE_CHANGED


def test_classify_new_failure_introduced_on_disjoint_signals() -> None:
    intervention = _identity(["sig_z"], 30)
    assert _classify("passed", True, BASE, intervention) == (
        CounterfactualOutcome.NEW_FAILURE_INTRODUCED
    )


def test_classify_experiment_failed_on_infra() -> None:
    assert _classify("timeout", False, BASE, _identity([], None)) == (
        CounterfactualOutcome.EXPERIMENT_FAILED
    )
    assert _classify("exec_error", False, BASE, _identity([], None)) == (
        CounterfactualOutcome.EXPERIMENT_FAILED
    )


def test_classify_insufficient_evidence() -> None:
    assert _classify("passed", False, BASE, _identity([], None)) == (
        CounterfactualOutcome.INSUFFICIENT_EVIDENCE
    )
    # A baseline with no localized divergence cannot be compared.
    assert _classify("passed", True, _identity([], None), _identity(["x"], 5)) == (
        CounterfactualOutcome.INSUFFICIENT_EVIDENCE
    )


def test_counterfactual_fingerprint_differences_for_removed_and_changed() -> None:
    baseline = FailureIdentity(
        signals=["sig_a"],
        failure_time=40,
        divergence_present=True,
        fingerprint_exact_digest="exact-a",
        fingerprint_family_digest="family-a",
    )
    removed = FailureIdentity(
        signals=[],
        failure_time=None,
        divergence_present=False,
        fingerprint_exact_digest=None,
        fingerprint_family_digest=None,
    )
    changed = FailureIdentity(
        signals=["sig_a", "sig_b"],
        failure_time=40,
        divergence_present=True,
        fingerprint_exact_digest="exact-b",
        fingerprint_family_digest="family-b",
    )

    assert _classify("passed", True, baseline, removed) == CounterfactualOutcome.FAILURE_REMOVED
    assert _classify("passed", True, baseline, changed) == CounterfactualOutcome.FAILURE_CHANGED
    removed_fields = {item.field for item in _observable_differences(baseline, removed)}
    changed_fields = {item.field for item in _observable_differences(baseline, changed)}

    assert "failure_fingerprint_exact_digest" in removed_fields
    assert "failure_fingerprint_family_digest" in removed_fields
    assert "failure_fingerprint_exact_digest" in changed_fields
    assert "failure_fingerprint_family_digest" in changed_fields


# --------------------------------------------------------------------------- #
# Service tests over a fake configured command (hermetic; no simulator).
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def baseline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("baseline")
    store = RunStore(root, run_id="baseline")
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=AXI_FAIL.resolve(),
        passing_vcd=AXI_PASS.resolve(),
        repository_root=AXI_RTL.resolve(),
        failure_time=40,
        before=15,
        after=15,
    )
    return store.run_dir


def _copy_command(vcd: Path) -> list[str]:
    script = (
        f'cp "{vcd.resolve()}" "$PWD/out.vcd" '
        f'&& echo "VCD info: dumpfile $PWD/out.vcd opened for output."'
    )
    return ["sh", "-c", script]


def _make_repo(tmp_path: Path, command_argv: list[str], *, timeout: int = 60) -> tuple[Path, Path]:
    repo = tmp_path / "target"
    (repo / "rtl").mkdir(parents=True)
    shutil.copyfile(FIXTURE_RTL, repo / "rtl" / "axi_pipe.sv")
    config = {
        "schema_version": 1,
        "repository_path": "rtl",
        "run_artifact_dir": ".rtl-agent/runs",
        "allowed_working_paths": ["."],
        "protected_paths": [],
        "execution": {"timeout_seconds": timeout},
        "commands": {"sim": {"argv": command_argv, "cwd": ".", "timeout_seconds": timeout}},
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


def _repo_state(repo: Path) -> tuple[str, str]:
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    rtl = (repo / "rtl" / "axi_pipe.sv").read_text(encoding="utf-8")
    return head, rtl


def test_failure_removed(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, _copy_command(AXI_PASS))
    before = _repo_state(repo)

    report = run_counterfactual(
        baseline_run=baseline,
        repo=repo,
        config_path=config,
        command="sim",
        output_run=tmp_path / "exp",
        allowed_files=["rtl/axi_pipe.sv"],
        replace_file="rtl/axi_pipe.sv",
        replace_old=FAULT_LINE,
        replace_new="payload_reg <= payload_reg;",
    )

    assert report.outcome == "failure_removed"
    assert report.intervention.applied is True
    assert report.intervention.target_files == ["rtl/axi_pipe.sv"]
    assert report.baseline_failure.signals == ["payload_out"]
    assert report.intervention_failure.divergence_present is False
    # The target repository is byte-for-byte unchanged and the worktree is gone.
    assert _repo_state(repo) == before
    assert report.worktree.removed is True
    assert not (tmp_path / "exp" / "worktrees" / "intervention").exists()
    # Intermediate evidence is preserved.
    roles = {artifact.role for artifact in report.generated_artifacts}
    assert {"command_stdout", "intervention_waveform", "intervention_failure_report"} <= roles
    assert (tmp_path / "exp" / "experiment-report.json").exists()
    assert (tmp_path / "exp" / "experiment-report.md").exists()
    assert "does not establish causality" in report.disclaimer


def test_no_observable_effect(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, _copy_command(AXI_FAIL))

    report = run_counterfactual(
        baseline_run=baseline,
        repo=repo,
        config_path=config,
        command="sim",
        output_run=tmp_path / "exp",
        allowed_files=["rtl/axi_pipe.sv"],
        replace_file="rtl/axi_pipe.sv",
        replace_old=FAULT_LINE,
        replace_new="payload_reg <= payload_reg;",
    )

    assert report.outcome == "no_observable_effect"
    assert report.intervention_failure.signals == ["payload_out"]
    assert report.intervention_failure.failure_time == 40


def test_patch_application_failure(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, _copy_command(AXI_PASS))
    bad_patch = tmp_path / "bad.diff"
    bad_patch.write_text(
        "diff --git a/rtl/axi_pipe.sv b/rtl/axi_pipe.sv\n"
        "--- a/rtl/axi_pipe.sv\n"
        "+++ b/rtl/axi_pipe.sv\n"
        "@@ -1,1 +1,1 @@\n"
        "-this line does not exist in the file at all\n"
        "+replacement\n",
        encoding="utf-8",
    )
    before = _repo_state(repo)

    with pytest.raises(CounterfactualError, match="patch does not apply"):
        run_counterfactual(
            baseline_run=baseline,
            repo=repo,
            config_path=config,
            command="sim",
            output_run=tmp_path / "exp",
            allowed_files=["rtl/axi_pipe.sv"],
            patch=bad_patch,
        )
    assert _repo_state(repo) == before


def test_command_timeout_is_experiment_failed(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, ["sh", "-c", "sleep 5"], timeout=1)

    report = run_counterfactual(
        baseline_run=baseline,
        repo=repo,
        config_path=config,
        command="sim",
        output_run=tmp_path / "exp",
        allowed_files=["rtl/axi_pipe.sv"],
        replace_file="rtl/axi_pipe.sv",
        replace_old=FAULT_LINE,
        replace_new="payload_reg <= payload_reg;",
    )

    assert report.outcome == "experiment_failed"
    assert report.execution is not None
    assert report.execution.status == "timeout"
    assert report.worktree.removed is True


def test_exec_error_is_experiment_failed(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, ["rtl-agent-missing-binary-xyz"])

    report = run_counterfactual(
        baseline_run=baseline,
        repo=repo,
        config_path=config,
        command="sim",
        output_run=tmp_path / "exp",
        allowed_files=["rtl/axi_pipe.sv"],
        replace_file="rtl/axi_pipe.sv",
        replace_old=FAULT_LINE,
        replace_new="payload_reg <= payload_reg;",
    )

    assert report.outcome == "experiment_failed"
    assert report.execution is not None
    assert report.execution.status == "exec_error"


def test_invalid_baseline_is_refused(tmp_path: Path, baseline: Path) -> None:
    corrupt = tmp_path / "corrupt-baseline"
    shutil.copytree(baseline, corrupt)
    (corrupt / "signal-source-map.json").write_text("corrupt", encoding="utf-8")
    repo, config = _make_repo(tmp_path, _copy_command(AXI_PASS))

    with pytest.raises(CounterfactualError, match="invalid baseline"):
        run_counterfactual(
            baseline_run=corrupt,
            repo=repo,
            config_path=config,
            command="sim",
            output_run=tmp_path / "exp",
            allowed_files=["rtl/axi_pipe.sv"],
            replace_file="rtl/axi_pipe.sv",
            replace_old=FAULT_LINE,
            replace_new="payload_reg <= payload_reg;",
        )


def test_disallowed_file_modification_is_refused(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, _copy_command(AXI_PASS))

    with pytest.raises(CounterfactualError, match="not in --allowed-file"):
        run_counterfactual(
            baseline_run=baseline,
            repo=repo,
            config_path=config,
            command="sim",
            output_run=tmp_path / "exp",
            allowed_files=["rtl/other.sv"],
            replace_file="rtl/axi_pipe.sv",
            replace_old=FAULT_LINE,
            replace_new="payload_reg <= payload_reg;",
        )


def test_dirty_target_repo_is_safe(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, _copy_command(AXI_PASS))
    (repo / "rtl" / "axi_pipe.sv").write_text(
        (repo / "rtl" / "axi_pipe.sv").read_text(encoding="utf-8") + "\n// local dirty edit\n",
        encoding="utf-8",
    )
    head_before = _repo_state(repo)[0]

    report = run_counterfactual(
        baseline_run=baseline,
        repo=repo,
        config_path=config,
        command="sim",
        output_run=tmp_path / "exp",
        allowed_files=["rtl/axi_pipe.sv"],
        replace_file="rtl/axi_pipe.sv",
        replace_old=FAULT_LINE,
        replace_new="payload_reg <= payload_reg;",
    )

    # The experiment still runs on an isolated worktree of the committed HEAD and
    # warns about the uncommitted changes; the committed history is untouched.
    assert report.outcome == "failure_removed"
    assert any("uncommitted changes" in warning for warning in report.warnings)
    assert _repo_state(repo)[0] == head_before


def test_report_serialization_is_stable(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, _copy_command(AXI_PASS))

    def run(output_name: str) -> dict[str, object]:
        report = run_counterfactual(
            baseline_run=baseline,
            repo=repo,
            config_path=config,
            command="sim",
            output_run=tmp_path / output_name,
            allowed_files=["rtl/axi_pipe.sv"],
            replace_file="rtl/axi_pipe.sv",
            replace_old=FAULT_LINE,
            replace_new="payload_reg <= payload_reg;",
        )
        return report.model_dump(mode="json")

    first = _stable(run("exp-a"))
    second = _stable(run("exp-b"))
    assert first == second


def _stable(report: dict[str, object]) -> dict[str, object]:
    """Drop documented volatile fields for a stable-content comparison."""

    return {
        "schema_version": report["schema_version"],
        "outcome": report["outcome"],
        "baseline_failure": report["baseline_failure"],
        "intervention_failure": report["intervention_failure"],
        "observable_differences": report["observable_differences"],
        "intervention_kind": report["intervention"]["kind"],  # type: ignore[index]
        "intervention_applied": report["intervention"]["applied"],  # type: ignore[index]
        "intervention_targets": report["intervention"]["target_files"],  # type: ignore[index]
        "disclaimer": report["disclaimer"],
    }
