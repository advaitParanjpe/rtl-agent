"""Icarus-backed check that the failure corpus builds a deterministic HKG.

For every design in `examples/failure-corpus/`, this produces one existing
failure-intelligence run, fingerprints it, clusters the resulting failures using
the existing canonical clustering service, then builds and writes one HKG JSON
artifact from those typed reports. The HKG layer does not execute commands,
query, infer, patch, or parse Markdown; this script only prepares the already
supported structured evidence artifacts used as HKG input.

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
from rtl_agent.hkg import (
    FailureBundle,
    Provenance,
    build_hkg,
    load_failure_bundle,
    serialize_graph,
    write_graph,
)
from rtl_agent.stimulus import materialize_stimulus, parse_stimulus

CORPUS = ROOT / "examples" / "failure-corpus"


def main() -> int:
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if iverilog is None or vvp is None:
        print("HKG failure corpus check skipped (iverilog/vvp not available)")
        return 0

    manifest = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="rtl-agent-hkg-corpus-") as raw_tmp:
        workspace = Path(raw_tmp)
        bundles: list[FailureBundle] = []
        members: list[FailureClusterMember] = []

        for example in manifest["examples"]:
            failure_id = example["name"]
            run_dir = _build_failure_run(iverilog, vvp, workspace, example)
            fingerprint = fingerprint_run(run_dir)
            assert fingerprint.canonical_digest, f"{failure_id}: missing canonical fingerprint"
            bundles.append(load_failure_bundle(failure_id, run_dir))
            members.append(
                member_from_fingerprint(
                    failure_id,
                    fingerprint,
                    observed_outcome=example["failure_class"],
                    artifact_ref=failure_id,
                )
            )

        cluster_report = cluster_failures(members)
        graph = build_hkg(
            bundles,
            graph_id="failure-corpus-hkg-v0",
            cluster_report=cluster_report,
            cluster_report_prov=Provenance(
                artifact_id="failure_clustering",
                schema_version=cluster_report.schema_version,
            ),
        )
        output = workspace / "hkg.json"
        write_graph(graph, output)
        assert output.read_text(encoding="utf-8") == serialize_graph(graph)
        repeat = build_hkg(
            list(reversed(bundles)),
            graph_id="failure-corpus-hkg-v0",
            cluster_report=cluster_report,
            cluster_report_prov=Provenance(
                artifact_id="failure_clustering",
                schema_version=cluster_report.schema_version,
            ),
        )
        assert serialize_graph(graph) == serialize_graph(repeat)
        assert graph.node_count == len(graph.nodes)
        assert graph.edge_count == len(graph.edges)
        assert all(node.provenance for node in graph.nodes)
        assert all(edge.provenance for edge in graph.edges)
        assert graph.node_type_counts.get("failure") == len(manifest["examples"])
        assert graph.node_type_counts.get("canonical_fingerprint") == len(manifest["examples"])
        assert graph.node_type_counts.get("failure_cluster") == len(manifest["examples"])
        assert graph.edge_type_counts.get("belongs_to_cluster") == len(manifest["examples"]) * 2
        assert cluster_report.canonical_cluster_count == len(manifest["examples"])

        print(
            "HKG failure corpus check passed "
            f"({graph.node_count} nodes, {graph.edge_count} edges, "
            f"{cluster_report.canonical_cluster_count} clusters)"
        )
    return 0


def _build_failure_run(iverilog: str, vvp: str, workspace: Path, example: dict[str, str]) -> Path:
    source = CORPUS / example["name"]
    module = example["module"]
    repo = _build_repo(workspace / example["name"], source)
    stimulus = parse_stimulus(source / example["stimulus"])
    materialize_stimulus(stimulus, repo)
    failing = workspace / f"{example['name']}-failing.vcd"
    passing = workspace / f"{example['name']}-passing.vcd"
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
    assert match, f"{example['name']}: seeded fault did not reproduce"
    failure_time = int(match.group(1))

    _run([iverilog, "-g2012", "-o", "pass.vvp", *sources], cwd=repo)
    subprocess.run(
        [vvp, "pass.vvp", f"+vcd={passing}", "+stim=sim/stimulus.mem"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failing.exists() and passing.exists()

    store = RunStore(workspace / "runs" / example["name"], run_id=example["name"])
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
    return store.run_dir


def _build_repo(workspace: Path, source: Path) -> Path:
    repo = workspace / "target"
    for sub in ("rtl", "tb", "sim"):
        shutil.copytree(source / sub, repo / sub)
    shutil.copyfile(source / "rtl-agent.yaml", repo / "rtl-agent.yaml")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=fixture@local", "-c", "user.name=fixture", "commit", "-qm", "seed")
    return repo


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
