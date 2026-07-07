"""Real Icarus-backed integration check for multi-failure clustering.

For every design in the realistic failure corpus it produces two genuine
reproductions of the seeded failure — a full-stimulus run and a minimized-core
run — and clusters all of them together with the deterministic clustering layer.
It asserts that the two manifestations of each mechanism land in the same cluster
(they share a canonical fingerprint) and that the three mechanisms stay in three
separate clusters, demonstrating clustering over the corpus using the existing
fingerprint infrastructure unchanged.

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
from rtl_agent.failure_clustering import cluster_failures, member_from_fingerprint
from rtl_agent.failure_clustering_models import FailureClusterMember
from rtl_agent.failure_fingerprint import fingerprint_run
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.stimulus import materialize_stimulus, parse_stimulus, subset_by_ids

CORPUS = ROOT / "examples" / "failure-corpus"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("failure clustering check skipped (iverilog/vvp not available)")
        return 0

    manifest = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
    members: list[FailureClusterMember] = []
    expected_pairs: dict[str, list[str]] = {}

    for example in manifest["examples"]:
        for tag, member_id in (
            ("full", f"{example['name']}:full"),
            ("core", f"{example['name']}:core"),
        ):
            member = _member(iverilog, vvp, example, tag, member_id)
            members.append(member)
            expected_pairs.setdefault(example["name"], []).append(member_id)

    report = cluster_failures(members)

    # Two manifestations of each mechanism share a cluster; three mechanisms stay
    # in three separate canonical clusters.
    assert report.canonical_cluster_count == len(manifest["examples"]), (
        f"expected {len(manifest['examples'])} clusters, got {report.canonical_cluster_count}"
    )
    assert report.insufficient_count == 0, report.unclustered_member_ids
    for name, ids in expected_pairs.items():
        assignments = {report.assignments[i] for i in ids}
        assert len(assignments) == 1, f"{name}: manifestations did not cluster together ({ids})"
    # Distinct mechanisms occupy distinct clusters.
    all_clusters = {report.assignments[m.member_id] for m in members}
    assert len(all_clusters) == len(manifest["examples"])

    for cluster in report.clusters:
        print(
            f"  cluster {cluster.cluster_id} size={cluster.size} "
            f"members={cluster.members} rep={cluster.representative_id}"
        )
    print(f"failure clustering check passed ({report.canonical_cluster_count} clusters)")
    return 0


def _member(
    iverilog: str, vvp: str, example: dict[str, str], tag: str, member_id: str
) -> FailureClusterMember:
    source = CORPUS / example["name"]
    module = example["module"]
    full = parse_stimulus(source / example["stimulus"])
    if tag == "core":
        core_ids = [item.id for item in full.items if not _is_padding(item.id)]
        stimulus = subset_by_ids(full, core_ids)
    else:
        stimulus = full

    with TemporaryDirectory(prefix=f"rtl-agent-cluster-{example['name']}-{tag}-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_repo(workspace, source)
        materialize_stimulus(stimulus, repo)
        sources = [f"rtl/{module}.sv", f"tb/{module}_tb.sv"]
        _run([iverilog, "-g2012", "-DINJECT_FAULT", "-o", "fail.vvp", *sources], cwd=repo)
        fault_run = subprocess.run(
            [vvp, "fail.vvp", f"+vcd={workspace}/failing.vcd", "+stim=sim/stimulus.mem"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        match = re.search(r"time=(\d+)", fault_run.stdout)
        assert match, f"{member_id}: the seeded fault did not reproduce"
        failure_time = int(match.group(1))
        _run([iverilog, "-g2012", "-o", "pass.vvp", *sources], cwd=repo)
        subprocess.run(
            [vvp, "pass.vvp", f"+vcd={workspace}/passing.vcd", "+stim=sim/stimulus.mem"],
            cwd=repo,
            capture_output=True,
            check=False,
        )
        store = RunStore(workspace / "runs", run_id="run")
        store.create()
        run_failure_intelligence(
            store,
            failing_vcd=workspace / "failing.vcd",
            passing_vcd=workspace / "passing.vcd",
            repository_root=repo / "rtl",
            failure_time=failure_time,
            before=20,
            after=20,
        )
        fingerprint = fingerprint_run(store.run_dir)

    return member_from_fingerprint(
        member_id,
        fingerprint,
        observed_outcome=example["failure_class"],
        artifact_ref=f"{example['name']}/{tag}",
    )


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
