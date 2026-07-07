from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from rtl_agent.artifacts import RunStore
from rtl_agent.experiment_matrix import run_experiment_matrix
from rtl_agent.experiment_matrix_models import InterventionManifest
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.intervention_template_models import ConfidenceLevel, TemplateKind
from rtl_agent.intervention_templates import (
    InterventionTemplateError,
    generate_interventions,
)
from rtl_agent.intervention_templates.templates import (
    block_transition_edit,
    extract_guard_expression,
    hold_edit,
    override_condition_edit,
    parse_assignment,
    suppress_edit,
)

# --------------------------------------------------------------------------- #
# Pure template unit tests.
# --------------------------------------------------------------------------- #


def test_exact_assignment_extraction() -> None:
    a = parse_assignment("payload_reg <= 'x;", "procedural_assign")
    assert a is not None and a.lhs == "payload_reg" and a.rhs == "'x" and a.operator == "<="
    c = parse_assignment("assign dout = hold;", "continuous_assign")
    assert c is not None and c.lhs == "dout" and c.rhs == "hold" and c.operator == "assign="


def test_procedural_versus_continuous_hold() -> None:
    proc = parse_assignment("hold <= 'x;", "procedural_assign")
    cont = parse_assignment("assign dout = hold;", "continuous_assign")
    assert proc is not None and cont is not None
    # Hold only applies to a sequential (nonblocking) register update.
    assert hold_edit("hold <= 'x;", proc) == ("hold <= 'x;", "hold <= hold;")
    assert hold_edit("assign dout = hold;", cont) is None


def test_suppress_and_self_hold_skip() -> None:
    a = parse_assignment("hold <= 'x;", "procedural_assign")
    assert a is not None
    assert suppress_edit("hold <= 'x;", a) == ("hold <= 'x;", "hold <= '0;")
    self_hold = parse_assignment("hold <= hold;", "procedural_assign")
    assert self_hold is not None
    assert suppress_edit("hold <= hold;", self_hold) is None


def test_guard_override_generation() -> None:
    assert override_condition_edit("end else if (locked && !ready) begin") == (
        "locked && !ready",
        "1'b0",
    )
    assert extract_guard_expression("`else") is None
    assert override_condition_edit("if (1'b1) begin") is None  # already constant


def test_block_transition_only_for_constants() -> None:
    const = parse_assignment("locked <= 1'b1;", "procedural_assign")
    dynamic = parse_assignment("hold <= din;", "procedural_assign")
    assert const is not None and dynamic is not None
    assert block_transition_edit("locked <= 1'b1;", const) == (
        "locked <= 1'b1;",
        "locked <= locked;",
    )
    assert block_transition_edit("hold <= din;", dynamic) is None


# --------------------------------------------------------------------------- #
# Integration on a hermetic failure-intelligence run (no simulator).
# --------------------------------------------------------------------------- #

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


def _write_vcds(root: Path) -> tuple[Path, Path]:
    failing = root / "failing.vcd"
    passing = root / "passing.vcd"
    failing.write_text(_VCD_HEAD + '#40\nbxxxxxxxx !\nbxxxxxxxx "\n#50\n', encoding="utf-8")
    passing.write_text(_VCD_HEAD + "#50\n", encoding="utf-8")
    return failing, passing


@dataclass
class _Fixture:
    run_dir: Path
    repo: Path
    failing_vcd: Path
    passing_vcd: Path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _build_repo(tmp_path: Path, core_source: str = CORE_SV) -> Path:
    repo = tmp_path / "repo"
    (repo / "rtl").mkdir(parents=True)
    (repo / "rtl" / "core.sv").write_text(core_source, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    return repo


def _build_run(tmp_path: Path, repo: Path) -> _Fixture:
    failing, passing = _write_vcds(tmp_path)
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
    return _Fixture(store.run_dir, repo, failing, passing)


@pytest.fixture
def fixture(tmp_path: Path) -> _Fixture:
    repo = _build_repo(tmp_path)
    return _build_run(tmp_path, repo)


def _generate(fixture: _Fixture, tmp_path: Path, name: str = "gen", **kw: object):  # type: ignore[no-untyped-def]
    return generate_interventions(
        failure_run=fixture.run_dir,
        repo=fixture.repo,
        allowed_files=kw.pop("allowed_files", ["rtl/core.sv"]),  # type: ignore[arg-type]
        output=tmp_path / name,
        **kw,  # type: ignore[arg-type]
    )


def test_generates_expected_kinds(fixture: _Fixture, tmp_path: Path) -> None:
    report = _generate(fixture, tmp_path, max_candidates=12)
    kinds = {str(c.template_kind) for c in report.candidates}
    assert TemplateKind.SUPPRESS_ASSIGNMENT in kinds
    assert TemplateKind.HOLD_REGISTER in kinds
    assert kinds & {str(TemplateKind.OVERRIDE_CONDITION), str(TemplateKind.BLOCK_STATE_TRANSITION)}
    # The fault line yields the strongest evidence.
    fault = [c for c in report.candidates if c.source_span_text == "hold <= 'x;"]
    assert fault and all(c.confidence == ConfidenceLevel.HIGH_EVIDENCE for c in fault)
    # Bounded-signal-override is honestly recorded as unsupported.
    assert any(u.template_kind == TemplateKind.BOUNDED_SIGNAL_OVERRIDE for u in report.unsupported)


def test_deterministic_ordering_and_digests(fixture: _Fixture, tmp_path: Path) -> None:
    a = _generate(fixture, tmp_path, "a", max_candidates=12)
    b = _generate(fixture, tmp_path, "b", max_candidates=12)
    assert [c.candidate_id for c in a.candidates] == [c.candidate_id for c in b.candidates]
    assert [c.semantic_digest for c in a.candidates] == [c.semantic_digest for c in b.candidates]


def test_candidate_bound(fixture: _Fixture, tmp_path: Path) -> None:
    report = _generate(fixture, tmp_path, max_candidates=2)
    assert len(report.candidates) == 2
    assert any("maximum candidate count" in s.reason for s in report.skipped)


def test_disallowed_file_rejected(fixture: _Fixture, tmp_path: Path) -> None:
    report = _generate(fixture, tmp_path, allowed_files=["rtl/other.sv"])
    assert report.candidates == []
    assert any("allowed-file policy" in s.reason for s in report.skipped)


def test_manifest_is_matrix_compatible(fixture: _Fixture, tmp_path: Path) -> None:
    report = _generate(fixture, tmp_path, "gen", max_candidates=12)
    manifest = InterventionManifest.model_validate_json(
        (tmp_path / "gen" / "interventions.json").read_text(encoding="utf-8")
    )
    assert len(manifest.interventions) == len(report.candidates)
    for entry in manifest.interventions:
        assert entry.replace is not None
        assert entry.allowed_files == ["rtl/core.sv"]
        assert entry.metadata["template_kind"]


def test_repository_immutable(fixture: _Fixture, tmp_path: Path) -> None:
    before = _repo_state(fixture.repo)
    _generate(fixture, tmp_path, max_candidates=12)
    assert _repo_state(fixture.repo) == before


def test_ambiguous_span_rejected(tmp_path: Path) -> None:
    # Two identical fault assignments make the span ambiguous.
    doubled = CORE_SV.replace(
        "        end else if (locked && ready) begin\n            locked <= 1'b0;\n        end",
        "        end else if (locked && ready) begin\n            hold <= 'x;\n        end",
    )
    repo = _build_repo(tmp_path, doubled)
    fixture = _build_run(tmp_path, repo)
    report = _generate(fixture, tmp_path, max_candidates=12)
    assert any("ambiguous" in s.reason for s in report.skipped)
    assert all(c.source_span_text != "hold <= 'x;" for c in report.candidates)


def test_stale_commit_source_mismatch(fixture: _Fixture, tmp_path: Path) -> None:
    # Rewrite the fault line and commit, so the evidence no longer matches HEAD.
    core = fixture.repo / "rtl" / "core.sv"
    core.write_text(core.read_text().replace("hold <= 'x;", "hold <= 8'hEE;"), encoding="utf-8")
    _git(fixture.repo, "commit", "-aqm", "change")
    report = _generate(fixture, tmp_path, max_candidates=12)
    assert all(c.source_span_text != "hold <= 'x;" for c in report.candidates)


def test_malformed_evidence_rejected(fixture: _Fixture, tmp_path: Path) -> None:
    # Tampering with an evidence artifact is caught by the run inspector (hash
    # mismatch), so the whole run is refused before any generation.
    (fixture.run_dir / "driver-trace.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(InterventionTemplateError, match="invalid failure run|unreadable"):
        _generate(fixture, tmp_path)


def test_invalid_failure_run_rejected(fixture: _Fixture, tmp_path: Path) -> None:
    (fixture.run_dir / "signal-source-map.json").write_text("corrupt", encoding="utf-8")
    with pytest.raises(InterventionTemplateError):
        _generate(fixture, tmp_path)


def test_serialization_written(fixture: _Fixture, tmp_path: Path) -> None:
    _generate(fixture, tmp_path, "gen", max_candidates=12)
    out = tmp_path / "gen"
    assert (out / "intervention-templates.json").exists()
    assert (out / "intervention-templates.md").exists()
    assert (out / "interventions.json").exists()
    assert any((out / "diffs").glob("*.diff"))
    text = (out / "intervention-templates.md").read_text(encoding="utf-8")
    assert "Experiment proposal" in text or "experiment proposals" in text


def test_generated_manifest_drives_matrix(fixture: _Fixture, tmp_path: Path) -> None:
    _generate(fixture, tmp_path, "gen", max_candidates=12)
    # A fake simulator keyed on the presence of the fault literal in core.sv.
    fail, clean = fixture.failing_vcd, fixture.passing_vcd
    script = (
        f"if grep -q \"hold <= 'x;\" rtl/core.sv; then cp '{fail}' failing.vcd; "
        f"cp '{clean}' passing.vcd; else cp '{clean}' failing.vcd; cp '{clean}' passing.vcd; fi; "
        f"echo done"
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
    config_path = fixture.repo / "rtl-agent.yaml"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    _git(fixture.repo, "add", "-A")
    _git(fixture.repo, "commit", "-qm", "config")

    reduction = _minimal_reduction(tmp_path)
    report = run_experiment_matrix(
        baseline_run=fixture.run_dir,
        reduction_report=reduction,
        repo=fixture.repo,
        config_path=config_path,
        command="sim",
        interventions=tmp_path / "gen" / "interventions.json",
        output=tmp_path / "matrix",
        max_experiments=12,
    )
    assert report.rows
    assert any(r.failure_removed for r in report.rows)


def _minimal_reduction(tmp_path: Path) -> Path:
    from rtl_agent.stimulus import parse_stimulus, stimulus_digest

    reduction_dir = tmp_path / "min"
    reduction_dir.mkdir(parents=True)
    stim_path = reduction_dir / "minimized-stimulus.json"
    stim_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "items": [{"id": "s0", "index": 0, "kind": "stall", "payload": {}}],
            }
        ),
        encoding="utf-8",
    )
    digest = stimulus_digest(parse_stimulus(stim_path))
    (reduction_dir / "reduction-report.json").write_text(
        json.dumps({"schema_version": 1, "minimized_stimulus_digest": digest}), encoding="utf-8"
    )
    return reduction_dir / "reduction-report.json"


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
