from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.reduction import StimulusReductionError, ddmin, minimize_stimulus
from rtl_agent.reduction.ddmin import BudgetExhausted
from rtl_agent.reduction_models import StimulusReductionReport, TerminationReason

FIXTURE_RTL = Path("examples/counterexample-axi/rtl/axi_pipe.sv").resolve()

_VCD_HEADER = (
    "$timescale 1ns $end\n"
    "$scope module axi_pipe_tb $end\n"
    "$scope module axi_pipe $end\n"
    "$var reg 8 ! payload_out [7:0] $end\n"
    '$var reg 1 " valid_out $end\n'
    "$upscope $end\n$upscope $end\n$enddefinitions $end\n"
    '$dumpvars\nb00000000 !\n0"\n$end\n'
    '#30\nb10101010 !\n1"\n'
)


def _make_vcd(path: Path, *, payload_x: bool, valid_x: bool) -> Path:
    """Write a minimal VCD whose signals resolve to the axi_pipe module."""

    body = _VCD_HEADER + "#40\n"
    if payload_x:
        body += "bxxxxxxxx !\n"
    if valid_x:
        body += 'x"\n'
    body += "#50\n"
    path.write_text(body, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# ddmin unit tests (pure oracle, no filesystem).
# --------------------------------------------------------------------------- #


def test_ddmin_reduces_to_minimal_core() -> None:
    def oracle(subset: list[str]) -> bool:
        return "X" in subset

    result, reason = ddmin(["a", "X", "b", "c", "d"], oracle)
    assert result == ["X"]
    assert reason == TerminationReason.NO_FURTHER_REDUCTION


def test_ddmin_preserves_relative_order() -> None:
    def oracle(subset: list[str]) -> bool:
        return "P" in subset and "Q" in subset

    result, _ = ddmin(["a", "P", "b", "Q", "c"], oracle)
    assert result == ["P", "Q"]


def test_ddmin_is_deterministic() -> None:
    calls_a: list[tuple[str, ...]] = []
    calls_b: list[tuple[str, ...]] = []

    def make(record: list[tuple[str, ...]]) -> Callable[[list[str]], bool]:
        def oracle(subset: list[str]) -> bool:
            record.append(tuple(subset))
            return "X" in subset

        return oracle

    items = ["a", "b", "X", "c", "d", "e"]
    result_a, _ = ddmin(items, make(calls_a))
    result_b, _ = ddmin(items, make(calls_b))
    assert result_a == result_b == ["X"]
    assert calls_a == calls_b


def test_ddmin_irreducible() -> None:
    def oracle(subset: list[str]) -> bool:
        return len(subset) == 3

    result, reason = ddmin(["a", "b", "c"], oracle)
    assert result == ["a", "b", "c"]
    assert reason == TerminationReason.NO_FURTHER_REDUCTION


def test_ddmin_budget_exhaustion() -> None:
    calls = 0

    def oracle(subset: list[str]) -> bool:
        nonlocal calls
        calls += 1
        if calls > 2:
            raise BudgetExhausted
        return "X" in subset

    result, reason = ddmin(["a", "X", "b", "c", "d", "e"], oracle)
    assert reason == TerminationReason.BUDGET_EXHAUSTED
    assert "X" in result


# --------------------------------------------------------------------------- #
# minimize_stimulus integration tests (hermetic fake simulator command).
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def waveforms(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("waveforms")
    return {
        "fam_a_failing": _make_vcd(root / "fam_a.vcd", payload_x=True, valid_x=False),
        "fam_b_failing": _make_vcd(root / "fam_b.vcd", payload_x=False, valid_x=True),
        "clean": _make_vcd(root / "clean.vcd", payload_x=False, valid_x=False),
    }


@pytest.fixture(scope="module")
def baseline(tmp_path_factory: pytest.TempPathFactory, waveforms: dict[str, Path]) -> Path:
    rtl = tmp_path_factory.mktemp("baseline-rtl")
    (rtl / "rtl").mkdir()
    shutil.copyfile(FIXTURE_RTL, rtl / "rtl" / "axi_pipe.sv")
    store = RunStore(tmp_path_factory.mktemp("baseline-run"), run_id="baseline")
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=waveforms["fam_a_failing"],
        passing_vcd=waveforms["clean"],
        repository_root=rtl / "rtl",
        failure_time=40,
        before=15,
        after=15,
    )
    return store.run_dir


def _family_command(waveforms: dict[str, Path]) -> list[str]:
    failing, clean = waveforms["fam_a_failing"], waveforms["clean"]
    script = (
        f"if grep -q '\"stall\"' sim/stimulus.json; then "
        f'cp "{failing}" failing.vcd; cp "{clean}" passing.vcd; '
        f'echo "assertion payload_stable failed at time=40 ns"; '
        f'else cp "{clean}" failing.vcd; cp "{clean}" passing.vcd; fi; '
        f'echo "VCD info: dumpfile failing.vcd opened"'
    )
    return ["sh", "-c", script]


def _static_command(failing: Path, passing: Path) -> list[str]:
    script = (
        f'cp "{failing}" failing.vcd; cp "{passing}" passing.vcd; '
        f'echo "VCD info: dumpfile failing.vcd opened"'
    )
    return ["sh", "-c", script]


def _make_repo(tmp_path: Path, argv: list[str], *, timeout: int = 60) -> tuple[Path, Path]:
    repo = tmp_path / "target"
    (repo / "rtl").mkdir(parents=True)
    (repo / "sim").mkdir(parents=True)
    shutil.copyfile(FIXTURE_RTL, repo / "rtl" / "axi_pipe.sv")
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


def _write_stimulus(tmp_path: Path, kinds: list[str]) -> Path:
    items = []
    for i, kind in enumerate(kinds):
        payload = {"data": "AA"} if kind == "send" else {}
        items.append({"id": f"i{i}-{kind}", "index": i, "kind": kind, "payload": payload})
    path = tmp_path / "stimulus.json"
    path.write_text(json.dumps({"schema_version": 1, "items": items}), encoding="utf-8")
    return path


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


def _minimize(
    baseline: Path, repo: Path, config: Path, tmp_path: Path, stimulus: Path, **kw: object
) -> StimulusReductionReport:
    return minimize_stimulus(
        baseline_run=baseline,
        repo=repo,
        config_path=config,
        command="sim",
        stimulus_path=stimulus,
        output=tmp_path / "out",
        **kw,  # type: ignore[arg-type]
    )


def test_successful_reduction(tmp_path: Path, baseline: Path, waveforms: dict[str, Path]) -> None:
    repo, config = _make_repo(tmp_path, _family_command(waveforms))
    stimulus = _write_stimulus(tmp_path, ["idle", "idle", "stall", "idle"])
    before = _repo_state(repo)

    report = _minimize(baseline, repo, config, tmp_path, stimulus, max_evaluations=40)

    assert report.final_classification in {"same_failure_exact", "same_failure_family"}
    assert report.minimized_item_count < report.original_item_count
    assert "i2-stall" in report.retained_item_ids
    assert any(item.endswith("idle") for item in report.removed_item_ids)
    # The source repository is unchanged.
    assert _repo_state(repo) == before
    assert (tmp_path / "out" / "reduction-report.json").exists()
    assert (tmp_path / "out" / "candidates").is_dir()


def test_failure_removed_baseline_not_preserved(
    tmp_path: Path, baseline: Path, waveforms: dict[str, Path]
) -> None:
    repo, config = _make_repo(tmp_path, _static_command(waveforms["clean"], waveforms["clean"]))
    stimulus = _write_stimulus(tmp_path, ["idle", "stall"])
    report = _minimize(baseline, repo, config, tmp_path, stimulus)
    assert report.termination_reason == "baseline_not_preserved"
    assert report.evaluation_history[0].classification == "failure_removed"
    assert report.minimized_item_count == report.original_item_count


def test_changed_failure_family_not_preserved(
    tmp_path: Path, baseline: Path, waveforms: dict[str, Path]
) -> None:
    repo, config = _make_repo(
        tmp_path, _static_command(waveforms["fam_b_failing"], waveforms["clean"])
    )
    stimulus = _write_stimulus(tmp_path, ["idle", "stall"])
    report = _minimize(baseline, repo, config, tmp_path, stimulus)
    assert report.termination_reason == "baseline_not_preserved"
    assert report.evaluation_history[0].classification == "different_failure"


def test_command_failure(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, ["sh", "-c", "exit 3"])
    stimulus = _write_stimulus(tmp_path, ["idle", "stall"])
    report = _minimize(baseline, repo, config, tmp_path, stimulus)
    assert report.evaluation_history[0].classification == "execution_failed"
    assert report.termination_reason == "baseline_not_preserved"


def test_timeout(tmp_path: Path, baseline: Path) -> None:
    repo, config = _make_repo(tmp_path, ["sh", "-c", "sleep 5"], timeout=1)
    stimulus = _write_stimulus(tmp_path, ["idle", "stall"])
    report = _minimize(baseline, repo, config, tmp_path, stimulus, timeout=1)
    assert report.evaluation_history[0].classification == "timed_out"


def test_evaluation_caching(tmp_path: Path, baseline: Path, waveforms: dict[str, Path]) -> None:
    repo, config = _make_repo(tmp_path, _family_command(waveforms))
    stimulus = _write_stimulus(tmp_path, ["idle", "idle", "idle", "send", "stall", "idle", "idle"])
    report = _minimize(baseline, repo, config, tmp_path, stimulus, max_evaluations=40)
    # Repeated candidates are served from cache rather than re-simulated: the
    # unique evaluation count equals the number of distinct candidate digests,
    # and the surplus history entries are cache hits.
    assert report.cache_hits >= 1
    unique_digests = {e.candidate_digest for e in report.evaluation_history}
    assert report.total_evaluations == len(unique_digests)
    assert report.cache_hits == len(report.evaluation_history) - report.total_evaluations
    assert all(e.from_cache for e in report.evaluation_history if e.from_cache)


def test_budget_exhaustion(tmp_path: Path, baseline: Path, waveforms: dict[str, Path]) -> None:
    repo, config = _make_repo(tmp_path, _family_command(waveforms))
    stimulus = _write_stimulus(tmp_path, ["idle", "idle", "stall", "idle"])
    report = _minimize(baseline, repo, config, tmp_path, stimulus, max_evaluations=1)
    assert report.termination_reason == "budget_exhausted"
    assert report.total_evaluations == 1


def test_invalid_baseline_rejected(
    tmp_path: Path, baseline: Path, waveforms: dict[str, Path]
) -> None:
    corrupt = tmp_path / "corrupt"
    shutil.copytree(baseline, corrupt)
    (corrupt / "signal-source-map.json").write_text("corrupt", encoding="utf-8")
    repo, config = _make_repo(tmp_path, _family_command(waveforms))
    stimulus = _write_stimulus(tmp_path, ["stall"])
    with pytest.raises(StimulusReductionError, match="invalid baseline"):
        _minimize(corrupt, repo, config, tmp_path, stimulus)


def test_stable_serialization(tmp_path: Path, baseline: Path, waveforms: dict[str, Path]) -> None:
    repo, config = _make_repo(tmp_path, _family_command(waveforms))
    stimulus = _write_stimulus(tmp_path, ["idle", "idle", "stall", "idle"])

    def normalized(name: str) -> dict[str, object]:
        report = minimize_stimulus(
            baseline_run=baseline,
            repo=repo,
            config_path=config,
            command="sim",
            stimulus_path=stimulus,
            output=tmp_path / name,
            max_evaluations=40,
        ).model_dump(mode="json")
        return {
            "final_classification": report["final_classification"],
            "retained": report["retained_item_ids"],
            "removed": report["removed_item_ids"],
            "termination_reason": report["termination_reason"],
            "minimized_item_count": report["minimized_item_count"],
            "history": [
                (e["item_count"], e["classification"], e["retained_item_ids"])
                for e in report["evaluation_history"]
            ],
        }

    assert normalized("a") == normalized("b")
