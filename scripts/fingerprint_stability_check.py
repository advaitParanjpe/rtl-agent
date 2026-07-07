"""Real Icarus-backed check for canonical failure-fingerprint stability.

For every design in the realistic failure corpus it produces two genuine
reproductions of the same seeded failure — one from the full baseline stimulus
and one from a shorter equivalent trace (the failing core with the warmup and
cooldown idles removed) — and asserts that both reproductions produce the same
canonical fingerprint even when the timing-sensitive exact fingerprint differs.
It also asserts that different failure mechanisms produce different canonical
fingerprints. This exercises canonicalization against benign variations
(differing absolute timestamps, differing stimulus lengths, equivalent reduced
traces) using the existing pipeline unchanged.

Gated: when Icarus Verilog is unavailable the check skips cleanly.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from _example_check import ROOT

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_fingerprint import fingerprint_run
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.stimulus import materialize_stimulus, parse_stimulus, subset_by_ids
from rtl_agent.stimulus_models import StructuredStimulus

CORPUS = ROOT / "examples" / "failure-corpus"


@dataclass
class _Fp:
    canonical: str
    exact: str
    family: str
    insufficient: bool


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("fingerprint stability check skipped (iverilog/vvp not available)")
        return 0

    manifest = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
    canonical_by_mechanism: dict[str, str] = {}

    for example in manifest["examples"]:
        canonical = _check_example(iverilog, vvp, example)
        canonical_by_mechanism[example["name"]] = canonical
        print(f"  '{example['name']}' canonical fingerprint stable across reproductions")

    distinct = set(canonical_by_mechanism.values())
    assert len(distinct) == len(canonical_by_mechanism), (
        f"different failure mechanisms must produce different canonical fingerprints: "
        f"{canonical_by_mechanism}"
    )
    print(f"fingerprint stability check passed ({len(canonical_by_mechanism)} mechanisms)")
    return 0


def _check_example(iverilog: str, vvp: str, example: dict[str, str]) -> str:
    source = CORPUS / example["name"]
    module = example["module"]
    full = parse_stimulus(source / example["stimulus"])
    core_ids = [item.id for item in full.items if not _is_padding(item.id)]
    core = subset_by_ids(full, core_ids)

    with TemporaryDirectory(prefix=f"rtl-agent-fpstab-{example['name']}-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_repo(workspace, source)
        full_fp = _fingerprint(iverilog, vvp, workspace, repo, module, full, "full")
        core_fp = _fingerprint(iverilog, vvp, workspace, repo, module, core, "core")

    assert not full_fp.insufficient, (example["name"], "full run insufficient evidence")
    assert not core_fp.insufficient, (
        example["name"],
        "the failing core did not reproduce with sufficient evidence",
    )
    # The canonical fingerprint is stable across the full and reduced reproduction.
    assert full_fp.canonical == core_fp.canonical, (
        f"{example['name']}: canonical fingerprint changed across reproductions "
        f"({full_fp.canonical[:12]} vs {core_fp.canonical[:12]})"
    )
    assert full_fp.canonical, f"{example['name']}: empty canonical fingerprint"
    return full_fp.canonical


def _is_padding(item_id: str) -> bool:
    return item_id.startswith("warmup") or item_id.startswith("cooldown")


def _build_repo(workspace: Path, source: Path) -> Path:
    repo = workspace / "target"
    for sub in ("rtl", "tb", "sim"):
        shutil.copytree(source / sub, repo / sub)
    shutil.copyfile(source / "rtl-agent.yaml", repo / "rtl-agent.yaml")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=fixture@local", "-c", "user.name=fixture", "commit", "-qm", "seed")
    return repo


def _fingerprint(
    iverilog: str,
    vvp: str,
    workspace: Path,
    repo: Path,
    module: str,
    stimulus: StructuredStimulus,
    tag: str,
) -> _Fp:
    materialize_stimulus(stimulus, repo)
    failing = workspace / f"failing-{tag}.vcd"
    passing = workspace / f"passing-{tag}.vcd"
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
    assert match, f"{module} ({tag}): the seeded fault did not reproduce"
    failure_time = int(match.group(1))

    _run([iverilog, "-g2012", "-o", "pass.vvp", *sources], cwd=repo)
    subprocess.run(
        [vvp, "pass.vvp", f"+vcd={passing}", "+stim=sim/stimulus.mem"],
        cwd=repo,
        capture_output=True,
        check=False,
    )

    store = RunStore(workspace / f"runs-{tag}", run_id="run")
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
    _git(repo, "checkout", "--", "sim/stimulus.mem")
    for name in ("sim/stimulus.json", "fail.vvp", "pass.vvp"):
        (repo / name).unlink(missing_ok=True)
    return _Fp(
        canonical=fingerprint.canonical_digest,
        exact=fingerprint.exact_digest,
        family=fingerprint.family_digest,
        insufficient=bool(fingerprint.insufficient_evidence),
    )


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")


def _run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\n{result.stdout[-1200:]}\n{result.stderr[-1200:]}"
        )


if __name__ == "__main__":
    sys.exit(main())
