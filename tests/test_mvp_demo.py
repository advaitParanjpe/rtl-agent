from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.mvp_demo import MvpDemoError, run_mvp_demo

CORE_SV = """module core (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [7:0] din,
    input  logic       ready,
    output logic [7:0] dout
);
    logic [7:0] hold;
    logic       locked;
    assign dout = hold;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            hold   <= '0;
            locked <= 1'b0;
        end else if (din != 8'd0 && !locked) begin
            hold   <= din;
            locked <= 1'b1;
        end else if (locked && !ready) begin
            hold <= 'x;
        end else if (locked && ready) begin
            locked <= 1'b0;
        end
    end
endmodule
"""

_VCD_HEAD = (
    "$timescale 1ns $end\n"
    "$scope module tb $end\n$scope module core $end\n"
    "$var reg 8 ! dout [7:0] $end\n"
    '$var reg 8 " hold [7:0] $end\n'
    "$var reg 1 # locked $end\n"
    "$upscope $end\n$upscope $end\n$enddefinitions $end\n"
    '$dumpvars\nb00000000 !\nb00000000 "\n0#\n$end\n'
    '#30\nb10101010 !\nb10101010 "\n1#\n'
)


@dataclass
class _Fixture:
    run_dir: Path
    repo: Path
    config: Path
    stimulus: Path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def fixture(tmp_path: Path) -> _Fixture:
    failing = tmp_path / "failing.vcd"
    passing = tmp_path / "passing.vcd"
    failing.write_text(_VCD_HEAD + '#40\nbxxxxxxxx !\nbxxxxxxxx "\n#50\n', encoding="utf-8")
    passing.write_text(_VCD_HEAD + "#50\n", encoding="utf-8")

    repo = tmp_path / "repo"
    (repo / "rtl").mkdir(parents=True)
    (repo / "sim").mkdir(parents=True)
    (repo / "rtl" / "core.sv").write_text(CORE_SV, encoding="utf-8")
    (repo / "sim" / "stimulus.mem").write_text("0000\n", encoding="utf-8")
    # A fake simulator that reproduces the family-A failure only while both the
    # stall stimulus item and the fault assignment are present (so minimization
    # and the intervention experiments both behave meaningfully).
    script = (
        f'if grep -q \'"stall"\' sim/stimulus.json && grep -q "hold <= \'x;" rtl/core.sv; '
        f"then cp '{failing}' failing.vcd; cp '{passing}' passing.vcd; "
        f"else cp '{passing}' failing.vcd; cp '{passing}' passing.vcd; fi; echo done"
    )
    config = {
        "schema_version": 1,
        "repository_path": "rtl",
        "run_artifact_dir": ".rtl-agent/runs",
        "allowed_working_paths": ["."],
        "protected_paths": [],
        "execution": {"timeout_seconds": 60},
        "commands": {"sim": {"argv": ["sh", "-c", script], "cwd": ".", "timeout_seconds": 60}},
    }
    config_path = repo / "rtl-agent.yaml"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")

    stimulus = tmp_path / "stimulus.json"
    stimulus.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "items": [
                    {"id": "warm-0", "index": 0, "kind": "idle", "payload": {}},
                    {"id": "warm-1", "index": 1, "kind": "idle", "payload": {}},
                    {"id": "trigger", "index": 2, "kind": "stall", "payload": {}},
                    {"id": "cool-0", "index": 3, "kind": "idle", "payload": {}},
                ],
            }
        ),
        encoding="utf-8",
    )

    store = RunStore(tmp_path / "runs", run_id="failure")
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=failing,
        passing_vcd=passing,
        repository_root=repo / "rtl",
        failure_time=40,
        before=15,
        after=15,
    )
    return _Fixture(store.run_dir, repo, config_path, stimulus)


def _run(fixture: _Fixture, tmp_path: Path, name: str = "demo"):  # type: ignore[no-untyped-def]
    return run_mvp_demo(
        failure_run=fixture.run_dir,
        repo=fixture.repo,
        config_path=fixture.config,
        command="sim",
        stimulus=fixture.stimulus,
        allowed_files=["rtl/core.sv"],
        output=tmp_path / name,
        max_candidates=8,
        max_experiments=12,
    )


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


def test_full_workflow_composes(fixture: _Fixture, tmp_path: Path) -> None:
    before = _repo_state(fixture.repo)
    summary = _run(fixture, tmp_path)

    # Every stage ran, in order.
    assert [s.stage for s in summary.stages] == [
        "inspect-run",
        "export-failure-package",
        "minimize-stimulus",
        "generate-interventions",
        "run-experiment-matrix",
    ]

    # 1. Original failure section.
    assert summary.original_failure.run_valid
    assert summary.original_failure.family_digest
    assert summary.original_failure.failure_package_files >= 1

    # Minimization actually reduced the stimulus.
    assert summary.minimization.minimized_item_count < summary.minimization.original_item_count

    # 2. Generated candidates + 3. experiment outcomes.
    assert summary.generated_candidates
    assert summary.experiment_outcomes
    assert len(summary.experiment_outcomes) == len(summary.generated_candidates)

    # 4. Evidence-backed observations, at least one measured effect.
    assert any(o.category == "experiment_result" for o in summary.observations)
    assert any(o.failure_removed for o in summary.experiment_outcomes)

    # Deterministic observed-effect labels are emitted and auditable.
    valid_labels = {
        "failure_removed",
        "failure_delayed",
        "failure_advanced",
        "failure_changed",
        "no_observable_effect",
        "new_failure",
        "experiment_invalid",
        "unknown",
    }
    for outcome in summary.experiment_outcomes:
        assert outcome.observed_effect in valid_labels
        assert outcome.observed_effect_rationale
    assert any(o.observed_effect == "failure_removed" for o in summary.experiment_outcomes)
    assert summary.observed_effect_counts
    assert sum(summary.observed_effect_counts.values()) == len(summary.experiment_outcomes)

    # The source repository is never modified.
    assert _repo_state(fixture.repo) == before


def test_outputs_written(fixture: _Fixture, tmp_path: Path) -> None:
    _run(fixture, tmp_path)
    out = tmp_path / "demo"
    assert (out / "mvp-demo-summary.json").exists()
    assert (out / "mvp-demo-summary.md").exists()
    assert (out / "failure-package").is_dir()
    assert (out / "minimization" / "reduction-report.json").exists()
    assert (out / "generated" / "interventions.json").exists()
    assert (out / "matrix" / "experiment-matrix.json").exists()
    text = (out / "mvp-demo-summary.md").read_text(encoding="utf-8")
    for heading in (
        "Original failure",
        "intervention candidates",
        "Experiment outcomes",
        "observations",
    ):
        assert heading in text


def test_no_causal_language(fixture: _Fixture, tmp_path: Path) -> None:
    summary = _run(fixture, tmp_path)
    blob = summary.model_dump_json().lower()
    assert "root cause of" not in blob
    assert "caused by" not in blob
    assert "does not establish causality" in summary.disclaimer


def test_invalid_failure_run_rejected(fixture: _Fixture, tmp_path: Path) -> None:
    (fixture.run_dir / "signal-source-map.json").write_text("corrupt", encoding="utf-8")
    with pytest.raises(MvpDemoError, match="invalid failure run"):
        _run(fixture, tmp_path, "demo2")


def test_cli_run_mvp_demo(fixture: _Fixture, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from rtl_agent.cli import app

    output = tmp_path / "cli-demo"
    result = CliRunner().invoke(
        app,
        [
            "run-mvp-demo",
            "--failure-run",
            str(fixture.run_dir),
            "--repo",
            str(fixture.repo),
            "--config",
            str(fixture.config),
            "--command",
            "sim",
            "--stimulus",
            str(fixture.stimulus),
            "--allowed-file",
            "rtl/core.sv",
            "--output",
            str(output),
            "--max-candidates",
            "8",
            "--max-experiments",
            "12",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary_json"].endswith("mvp-demo-summary.json")
    assert {s["stage"] for s in payload["stages"]} >= {
        "inspect-run",
        "run-experiment-matrix",
    }
    assert (output / "mvp-demo-summary.json").exists()
    assert (output / "mvp-demo-summary.md").exists()


def test_cli_invalid_failure_run_exits_2(fixture: _Fixture, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from rtl_agent.cli import app

    (fixture.run_dir / "signal-source-map.json").write_text("corrupt", encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "run-mvp-demo",
            "--failure-run",
            str(fixture.run_dir),
            "--repo",
            str(fixture.repo),
            "--config",
            str(fixture.config),
            "--command",
            "sim",
            "--stimulus",
            str(fixture.stimulus),
            "--allowed-file",
            "rtl/core.sv",
            "--output",
            str(tmp_path / "cli-demo2"),
        ],
    )
    assert result.exit_code == 2
    assert "error:" in result.output
