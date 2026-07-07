"""Real Icarus-backed check that the pipeline generalizes across the failure corpus.

It runs the existing rtl-agent pipeline (via the MVP demo driver) unchanged on
every design in `examples/failure-corpus/`, each of which seeds a different
failure mechanism (FSM transition bug, FIFO underflow, counter/state-update bug).
For each example it builds a target Git repository, produces a genuine baseline
failure-intelligence run from the failing regression, and runs the full
demonstration, asserting the pipeline completes with generated intervention
candidates and classified observed-effect outcomes while leaving the source
repository byte-for-byte unchanged. No example-specific logic is used — the
corpus manifest drives everything.

Gated: when Icarus Verilog is unavailable the check skips cleanly.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from _example_check import ROOT

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_fingerprint import fingerprint_run
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.mvp_demo import run_mvp_demo
from rtl_agent.stimulus import materialize_stimulus, parse_stimulus

CORPUS = ROOT / "examples" / "failure-corpus"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("failure corpus check skipped (iverilog/vvp not available)")
        return 0

    manifest = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
    examples = manifest["examples"]
    assert len(examples) >= 3, "the corpus must contain at least three examples"

    for example in examples:
        _run_example(iverilog, vvp, example)
        print(f"  corpus example '{example['name']}' ({example['failure_class']}) passed")

    print(f"failure corpus check passed ({len(examples)} examples)")
    return 0


def _run_example(iverilog: str, vvp: str, example: dict[str, str]) -> None:
    source = CORPUS / example["name"]
    module = example["module"]
    with TemporaryDirectory(prefix=f"rtl-agent-corpus-{example['name']}-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_repo(workspace, source)
        before_head, before_hashes = _repo_snapshot(repo)

        baseline = _build_baseline(iverilog, vvp, workspace, repo, source, module)

        summary = run_mvp_demo(
            failure_run=baseline,
            repo=repo,
            config_path=repo / "rtl-agent.yaml",
            command=example["command"],
            stimulus=source / example["stimulus"],
            allowed_files=[example["allowed_file"]],
            output=workspace / "demo",
            max_candidates=8,
            max_experiments=12,
            timeout=60,
        )

        _check_summary(summary, example)
        after_head, after_hashes = _repo_snapshot(repo)
        assert after_head == before_head, f"{example['name']}: repository commit changed"
        assert after_hashes == before_hashes, f"{example['name']}: repository files changed"


def _build_repo(workspace: Path, source: Path) -> Path:
    repo = workspace / "target"
    for sub in ("rtl", "tb", "sim"):
        shutil.copytree(source / sub, repo / sub)
    shutil.copyfile(source / "rtl-agent.yaml", repo / "rtl-agent.yaml")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=fixture@local", "-c", "user.name=fixture", "commit", "-qm", "seed")
    return repo


def _build_baseline(
    iverilog: str, vvp: str, workspace: Path, repo: Path, source: Path, module: str
) -> Path:
    stimulus = parse_stimulus(source / "failing-stimulus.json")
    materialize_stimulus(stimulus, repo)
    failing = workspace / "failing.vcd"
    passing = workspace / "passing.vcd"
    sources = [f"rtl/{module}.sv", f"tb/{module}_tb.sv"]

    _run([iverilog, "-g2012", "-DINJECT_FAULT", "-o", "fail.vvp", *sources], cwd=repo)
    fault_run = subprocess.run(
        [vvp, "fail.vvp", f"+vcd={failing}", "+stim=sim/stimulus.mem"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"time=(\d+)", fault_run.stdout)
    assert match, f"{module}: the seeded fault did not reproduce\n{fault_run.stdout[-800:]}"
    failure_time = int(match.group(1))

    _run([iverilog, "-g2012", "-o", "pass.vvp", *sources], cwd=repo)
    subprocess.run(
        [vvp, "pass.vvp", f"+vcd={passing}", "+stim=sim/stimulus.mem"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert failing.exists() and passing.exists()

    store = RunStore(workspace / "baselines", run_id="baseline")
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=failing,
        passing_vcd=passing,
        repository_root=repo / "rtl",
        failure_time=failure_time,
        before=20,
        after=20,
    )
    fingerprint = fingerprint_run(store.run_dir)
    assert not fingerprint.insufficient_evidence, (module, fingerprint.insufficient_evidence)

    _git(repo, "checkout", "--", "sim/stimulus.mem")
    for name in ("sim/stimulus.json", "fail.vvp", "pass.vvp"):
        (repo / name).unlink(missing_ok=True)
    return store.run_dir


def _check_summary(summary: object, example: dict[str, str]) -> None:
    from rtl_agent.mvp_demo_models import MvpDemoSummary

    assert isinstance(summary, MvpDemoSummary)
    name = example["name"]
    stages = {s.stage: s.status for s in summary.stages}
    assert stages.get("inspect-run") == "valid", name
    assert stages.get("run-experiment-matrix") == "executed", name
    assert summary.minimization.minimized_item_count < summary.minimization.original_item_count, (
        name
    )
    assert summary.generated_candidates, f"{name}: no intervention candidates generated"
    assert summary.experiment_outcomes, f"{name}: no experiment outcomes"
    assert summary.observed_effect_counts, f"{name}: no observed-effect labels"
    # Every experiment carries a classified, auditable observed-effect label.
    valid = {
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
        assert outcome.observed_effect in valid, (name, outcome.observed_effect)
    assert summary.next_debug_checks, f"{name}: no synthesized next-debug checks"
    assert summary.repair_suggestions, f"{name}: no repair-direction suggestions"
    for suggestion in summary.repair_suggestions:
        assert suggestion.supporting_interventions, (name, suggestion.suggestion_id)
        assert suggestion.supporting_outcomes, (name, suggestion.suggestion_id)
        assert suggestion.evidence_basis, (name, suggestion.suggestion_id)
        text = suggestion.suggested_area.lower()
        assert text.startswith(("inspect", "review", "check")), (name, suggestion.suggested_area)
        assert "fix" not in text and "root cause" not in text, (name, suggestion.suggested_area)

    # Interventions are ranked deterministically by informativeness.
    assert summary.intervention_rankings, f"{name}: no intervention rankings"
    assert len(summary.intervention_rankings) == len(summary.experiment_outcomes), name
    ranked = [r for r in summary.intervention_rankings if r.ranked]
    assert ranked, f"{name}: no ranked interventions"
    assert [r.rank for r in ranked] == list(range(1, len(ranked) + 1)), name
    assert [r.score for r in ranked] == sorted((r.score for r in ranked), reverse=True), name
    assert all(r.explanation and r.evidence_refs for r in ranked), name

    blob = summary.model_dump_json().lower()
    assert "root cause of" not in blob
    assert "caused by" not in blob


def _repo_snapshot(repo: Path) -> tuple[str, dict[str, str]]:
    head = _git(repo, "rev-parse", "HEAD").strip()
    hashes: dict[str, str] = {}
    for path in sorted(repo.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            hashes[path.relative_to(repo).as_posix()] = _sha(path)
    return head, hashes


def _sha(path: Path) -> str:
    from hashlib import sha256

    return sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\n{result.stdout[-1500:]}\n{result.stderr[-1500:]}"
        )


if __name__ == "__main__":
    sys.exit(main())
