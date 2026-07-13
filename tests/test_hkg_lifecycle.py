from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rtl_agent.artifacts import RunStore
from rtl_agent.cli import app
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.failure_package import export_failure_package
from rtl_agent.hkg.lifecycle import (
    HkgConflictError,
    HkgLifecycleError,
    build_hkg_store,
    inspect_hkg_store,
    load_hkg_store,
    merge_graphs,
    update_hkg_store,
)
from rtl_agent.hkg.models import EdgeType, HkgEdge, HkgGraph, HkgNode, NodeType
from rtl_agent.hkg.source_adapters import (
    load_failure_package_source,
    load_mvp_demo_sources,
)
from rtl_agent.mvp_demo import run_mvp_demo

ROOT = Path(__file__).resolve().parents[1]
AXI_FIXTURE = ROOT / "examples" / "axi-stream-router"
FAILING_VCD = AXI_FIXTURE / "waveforms" / "failure.vcd"
PASSING_VCD = AXI_FIXTURE / "waveforms" / "passing.vcd"
ALLOWED_FILE = "rtl/axi_stream_router.sv"


@dataclass(frozen=True)
class _Artifacts:
    root: Path
    repo: Path
    run: Path
    second_run: Path
    package: Path
    demo: Path


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory) -> _Artifacts:
    root = tmp_path_factory.mktemp("persistent-hkg")
    repo = _build_repo(root)
    run = _failure_run(root / "runs-a", repo, "baseline")
    second_run = _failure_run(root / "runs-b", repo, "later")
    package = root / "failure-package"
    export_failure_package(run, package)
    demo = root / "demo"
    run_mvp_demo(
        failure_run=run,
        repo=repo,
        config_path=repo / "rtl-agent.yaml",
        command="emit-vcd",
        stimulus=repo / "stimulus.json",
        allowed_files=[ALLOWED_FILE],
        output=demo,
        max_candidates=3,
        max_experiments=3,
        timeout=30,
    )
    return _Artifacts(root, repo, run, second_run, package, demo)


def test_build_load_inspect_and_real_counterfactual_ingestion(
    artifacts: _Artifacts, tmp_path: Path
) -> None:
    store = tmp_path / "hkg"
    summary = build_hkg_store(
        failure_packages=[artifacts.package], mvp_demos=[artifacts.demo], output=store
    )
    graph, manifest = load_hkg_store(store)
    inspection = inspect_hkg_store(store)

    assert summary.changed is True
    assert manifest.graph_sha256 == summary.graph_sha256
    assert inspection.valid and inspection.manifest_valid
    assert inspection.source_count == 2
    assert inspection.intervention_count == 3
    assert inspection.experiment_count == 3
    assert inspection.observed_effect_count >= 1
    assert all(source.source_id for source in graph.sources)
    elements: list[HkgNode | HkgEdge] = [*graph.nodes, *graph.edges]
    assert all(
        provenance.source_id and provenance.path and not Path(provenance.path).is_absolute()
        for element in elements
        for provenance in element.provenance
    )
    assert not any(node.type == "repair_suggestion" for node in graph.nodes)
    failure = next(node for node in graph.nodes if node.type == "failure")
    intervention = next(node for node in graph.nodes if node.type == "intervention")
    experiment = next(node for node in graph.nodes if node.type == "experiment")
    generated = {(edge.source, edge.target) for edge in graph.edges if edge.type == "generated"}
    tested = {
        (edge.source, edge.target)
        for edge in graph.edges
        if edge.attributes.get("role") == "tested"
    }
    assert (failure.node_id, intervention.node_id) in generated
    assert any(source == experiment.node_id for source, _target in tested)


def test_build_is_order_and_relocation_independent(artifacts: _Artifacts, tmp_path: Path) -> None:
    relocated = tmp_path / "relocated-package"
    shutil.copytree(artifacts.package, relocated)
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_hkg_store(
        failure_runs=[artifacts.run],
        failure_packages=[relocated],
        mvp_demos=[artifacts.demo],
        output=first,
    )
    build_hkg_store(
        mvp_demos=[artifacts.demo],
        failure_packages=[artifacts.package],
        output=second,
    )
    assert (first / "hkg.json").read_bytes() == (second / "hkg.json").read_bytes()
    assert (first / "hkg-manifest.json").read_bytes() == (second / "hkg-manifest.json").read_bytes()
    assert (
        load_failure_package_source(relocated).record
        == load_failure_package_source(artifacts.package).record
    )

    incremental = tmp_path / "incremental"
    complete = tmp_path / "complete"
    build_hkg_store(failure_packages=[artifacts.package], output=incremental)
    update_hkg_store(store=incremental, mvp_demos=[artifacts.demo])
    update_hkg_store(store=incremental, failure_runs=[artifacts.second_run])
    build_hkg_store(
        failure_runs=[artifacts.second_run],
        failure_packages=[artifacts.package],
        mvp_demos=[artifacts.demo],
        output=complete,
    )
    assert (incremental / "hkg.json").read_bytes() == (complete / "hkg.json").read_bytes()
    assert (incremental / "hkg-manifest.json").read_bytes() == (
        complete / "hkg-manifest.json"
    ).read_bytes()


def test_update_idempotence_and_source_conflict_preserve_store(
    artifacts: _Artifacts, tmp_path: Path
) -> None:
    store = tmp_path / "hkg"
    build_hkg_store(failure_packages=[artifacts.package], output=store)
    changed = update_hkg_store(store=store, mvp_demos=[artifacts.demo])
    graph_before = (store / "hkg.json").read_bytes()
    manifest_before = (store / "hkg-manifest.json").read_bytes()
    no_op = update_hkg_store(store=store, mvp_demos=[artifacts.demo])
    assert changed.changed is True
    assert no_op.changed is False
    assert (store / "hkg.json").read_bytes() == graph_before
    assert (store / "hkg-manifest.json").read_bytes() == manifest_before

    changed_demo = tmp_path / "changed-demo"
    shutil.copytree(artifacts.demo, changed_demo)
    summary_path = changed_demo / "mvp-demo-summary.json"
    raw = json.loads(summary_path.read_text(encoding="utf-8"))
    raw["warnings"] = ["content changed under the same logical MVP source"]
    _write_json(summary_path, raw)
    with pytest.raises(HkgConflictError, match="source identity/content conflict"):
        update_hkg_store(store=store, mvp_demos=[changed_demo])
    assert (store / "hkg.json").read_bytes() == graph_before
    assert (store / "hkg-manifest.json").read_bytes() == manifest_before


def test_same_canonical_runs_keep_source_scoped_occurrences(
    artifacts: _Artifacts, tmp_path: Path
) -> None:
    store = tmp_path / "hkg"
    build_hkg_store(failure_runs=[artifacts.second_run, artifacts.run], output=store)
    graph, _manifest = load_hkg_store(store)
    failures = [node for node in graph.nodes if node.type == "failure"]
    signals = [
        node for node in graph.nodes if node.type == "signal" and node.label == "payload_out"
    ]
    modules = [node for node in graph.nodes if node.type == "module"]
    locations = [node for node in graph.nodes if node.type == "source_location"]
    assert len(failures) == 2
    assert len({node.attributes["source_id"] for node in failures}) == 2
    assert len(signals) == 2
    assert len({node.node_id.split(":", 2)[1] for node in modules}) == 2
    assert len({node.node_id.split(":", 2)[1] for node in locations}) == 2
    clusters = [node for node in graph.nodes if node.type == "failure_cluster"]
    shared = [node for node in clusters if node.attributes.get("size") == "2"]
    assert len(shared) == 1


def test_invalid_sources_and_graph_corruption_are_rejected(
    artifacts: _Artifacts, tmp_path: Path
) -> None:
    tampered = tmp_path / "tampered-package"
    shutil.copytree(artifacts.package, tampered)
    target = tampered / "run/waveform/comparison.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(HkgLifecycleError, match="hash mismatch"):
        build_hkg_store(failure_packages=[tampered], output=tmp_path / "bad-store")

    missing = tmp_path / "missing-demo"
    shutil.copytree(artifacts.demo, missing)
    (missing / "matrix/experiment-matrix.json").unlink()
    with pytest.raises(HkgLifecycleError, match="missing: matrix"):
        build_hkg_store(mvp_demos=[missing], output=tmp_path / "missing-store")

    unsafe = tmp_path / "unsafe-demo"
    shutil.copytree(artifacts.demo, unsafe)
    matrix_path = unsafe / "matrix/experiment-matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix["rows"][0]["artifact_dir"] = "../escape"
    _write_json(matrix_path, matrix)
    with pytest.raises(HkgLifecycleError, match="unsafe source-relative path"):
        build_hkg_store(mvp_demos=[unsafe], output=tmp_path / "unsafe-store")

    store = tmp_path / "valid-store"
    build_hkg_store(failure_runs=[artifacts.run], output=store)
    graph_path = store / "hkg.json"
    graph_path.write_text(graph_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(HkgLifecycleError, match="graph hash mismatch"):
        load_hkg_store(store)
    assert inspect_hkg_store(store).valid is False

    manifest_store = tmp_path / "manifest-store"
    build_hkg_store(failure_runs=[artifacts.run], output=manifest_store)
    manifest_path = manifest_store / "hkg-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_count"] += 1
    _write_json(manifest_path, manifest)
    with pytest.raises(HkgLifecycleError, match="manifest metadata does not agree"):
        load_hkg_store(manifest_store)


def test_legacy_graph_requires_rebuild(tmp_path: Path) -> None:
    store = tmp_path / "legacy"
    store.mkdir()
    _write_json(store / "hkg.json", {"schema_version": 1, "graph_id": "legacy"})
    with pytest.raises(HkgLifecycleError, match="legacy HKG schema 1.*rebuild"):
        load_hkg_store(store)


def test_atomic_manifest_failure_restores_previous_store(
    artifacts: _Artifacts, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rtl_agent.hkg.lifecycle as lifecycle

    store = tmp_path / "hkg"
    build_hkg_store(failure_runs=[artifacts.run], output=store)
    graph_before = (store / "hkg.json").read_bytes()
    manifest_before = (store / "hkg-manifest.json").read_bytes()
    original = lifecycle._atomic_replace
    failed = False

    def fail_manifest_once(path: Path, content: bytes) -> None:
        nonlocal failed
        if path.name == "hkg-manifest.json" and not failed:
            failed = True
            raise OSError("seeded manifest write failure")
        original(path, content)

    monkeypatch.setattr(lifecycle, "_atomic_replace", fail_manifest_once)
    with pytest.raises(HkgLifecycleError, match="atomic write failed"):
        update_hkg_store(store=store, mvp_demos=[artifacts.demo])
    assert (store / "hkg.json").read_bytes() == graph_before
    assert (store / "hkg-manifest.json").read_bytes() == manifest_before
    assert inspect_hkg_store(store).valid is True


def test_incompatible_node_and_edge_collisions_reject() -> None:
    left = _collision_graph(
        HkgNode(node_id="signal:s", type=NodeType.SIGNAL, label="s"),
        HkgEdge(
            edge_id="references|signal:s|signal:t|",
            type=EdgeType.REFERENCES,
            source="signal:s",
            target="signal:t",
        ),
    )
    right_node = _collision_graph(
        HkgNode(node_id="signal:s", type=NodeType.SIGNAL, label="different"),
        HkgEdge(
            edge_id="references|signal:s|signal:t|",
            type=EdgeType.REFERENCES,
            source="signal:s",
            target="signal:t",
        ),
    )
    with pytest.raises(HkgConflictError, match="incompatible node collision"):
        merge_graphs(left, right_node)

    right_edge = _collision_graph(
        HkgNode(node_id="signal:s", type=NodeType.SIGNAL, label="s"),
        HkgEdge(
            edge_id="references|signal:s|signal:t|",
            type=EdgeType.REFERENCES,
            source="signal:s",
            target="signal:t",
            attributes={"role": "different"},
        ),
    )
    with pytest.raises(HkgConflictError, match="incompatible edge collision"):
        merge_graphs(left, right_edge)


def test_cli_build_update_and_inspect(artifacts: _Artifacts, tmp_path: Path) -> None:
    store = tmp_path / "cli-hkg"
    runner = CliRunner()
    build = runner.invoke(
        app,
        ["hkg-build", "--failure-package", str(artifacts.package), "--output", str(store)],
    )
    assert build.exit_code == 0, build.output
    assert json.loads(build.output)["source_count"] == 1

    update = runner.invoke(
        app, ["hkg-update", "--store", str(store), "--mvp-demo", str(artifacts.demo)]
    )
    assert update.exit_code == 0, update.output
    assert json.loads(update.output)["changed"] is True
    no_op = runner.invoke(
        app, ["hkg-update", "--store", str(store), "--mvp-demo", str(artifacts.demo)]
    )
    assert no_op.exit_code == 0
    assert json.loads(no_op.output)["changed"] is False

    changed_demo = tmp_path / "cli-changed-demo"
    shutil.copytree(artifacts.demo, changed_demo)
    summary_path = changed_demo / "mvp-demo-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["warnings"] = ["CLI conflict control"]
    _write_json(summary_path, summary)
    conflict = runner.invoke(
        app, ["hkg-update", "--store", str(store), "--mvp-demo", str(changed_demo)]
    )
    assert conflict.exit_code == 1
    assert "source identity/content conflict" in conflict.output

    human = runner.invoke(app, ["hkg-inspect", "--store", str(store)])
    assert human.exit_code == 0
    assert "HKG valid:" in human.output
    machine = runner.invoke(app, ["hkg-inspect", "--store", str(store), "--json"])
    assert machine.exit_code == 0
    assert json.loads(machine.output)["valid"] is True

    (store / "hkg.json").write_text("{}\n", encoding="utf-8")
    corrupt = runner.invoke(app, ["hkg-inspect", "--store", str(store), "--json"])
    assert corrupt.exit_code == 1
    assert json.loads(corrupt.output)["valid"] is False


def test_mvp_ingestion_index_is_deterministic_after_relocation(
    artifacts: _Artifacts, tmp_path: Path
) -> None:
    relocated = tmp_path / "relocated-demo"
    shutil.copytree(artifacts.demo, relocated)
    original = {
        payload.record.source_id: payload.record
        for payload in load_mvp_demo_sources(artifacts.demo)
    }
    moved = {
        payload.record.source_id: payload.record for payload in load_mvp_demo_sources(relocated)
    }
    assert moved == original


def _collision_graph(node: HkgNode, edge: HkgEdge) -> HkgGraph:
    target = HkgNode(node_id="signal:t", type=NodeType.SIGNAL, label="t")
    return HkgGraph(
        graph_id="persistent-hkg-v1",
        node_count=2,
        edge_count=1,
        node_type_counts={"signal": 2},
        edge_type_counts={"references": 1},
        nodes=sorted([node, target], key=lambda item: item.node_id),
        edges=[edge],
    )


def _build_repo(root: Path) -> Path:
    repo = root / "target"
    (repo / "rtl").mkdir(parents=True)
    (repo / "sim").mkdir()
    shutil.copyfile(AXI_FIXTURE / "rtl/axi_stream_router.sv", repo / ALLOWED_FILE)
    shutil.copyfile(FAILING_VCD, repo / "sim/failing-template.vcd")
    shutil.copyfile(PASSING_VCD, repo / "sim/passing-template.vcd")
    (repo / "sim/emit_vcd.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import shutil",
                "root = Path.cwd()",
                "shutil.copyfile(root / 'sim/failing-template.vcd', root / 'failing.vcd')",
                "shutil.copyfile(root / 'sim/passing-template.vcd', root / 'passing.vcd')",
                "print('assertion payload_stable failed at time=40 ns')",
                "raise SystemExit(1)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    config = {
        "schema_version": 1,
        "repository_path": "rtl",
        "run_artifact_dir": ".rtl-agent/runs",
        "allowed_working_paths": ["."],
        "protected_paths": [],
        "execution": {"timeout_seconds": 30, "max_output_bytes": 1048576},
        "commands": {
            "emit-vcd": {
                "argv": [sys.executable, "sim/emit_vcd.py"],
                "cwd": ".",
                "timeout_seconds": 30,
            }
        },
    }
    _write_json(repo / "rtl-agent.yaml", config)
    _write_json(
        repo / "stimulus.json",
        {
            "schema_version": 1,
            "items": [
                {"id": "warmup", "index": 0, "kind": "idle", "payload": {}},
                {"id": "send", "index": 1, "kind": "send", "payload": {"data": "AA"}},
                {"id": "stall", "index": 2, "kind": "stall", "payload": {}},
            ],
        },
    )
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=fixture@local", "-c", "user.name=fixture", "commit", "-qm", "seed")
    return repo


def _failure_run(root: Path, repo: Path, run_id: str) -> Path:
    store = RunStore(root, run_id=run_id)
    store.create()
    run_failure_intelligence(
        store,
        failing_vcd=FAILING_VCD,
        passing_vcd=PASSING_VCD,
        repository_root=repo / "rtl",
        failure_time=40,
        before=15,
        after=15,
    )
    return store.run_dir


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
