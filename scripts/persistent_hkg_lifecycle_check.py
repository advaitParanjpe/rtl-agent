"""Hermetic end-to-end check for persistent HKG lifecycle and MVP history reuse."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from _example_check import ROOT
from evidence_artifact_provenance_check import (
    ALLOWED_FILE,
    FAILING_VCD,
    PASSING_VCD,
    _build_target_repo,
    _generate_failure_run,
)

from rtl_agent.artifacts import RunStore
from rtl_agent.failure_intelligence_run import run_failure_intelligence
from rtl_agent.failure_package import export_failure_package
from rtl_agent.hkg.lifecycle import (
    HkgConflictError,
    build_hkg_store,
    inspect_hkg_store,
    update_hkg_store,
)
from rtl_agent.mvp_demo import run_mvp_demo


def main() -> int:
    with TemporaryDirectory(prefix="rtl-agent-persistent-hkg-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo = _build_target_repo(workspace)
        baseline = _generate_failure_run(workspace, repo)

        package = workspace / "failure-package"
        export_failure_package(baseline, package)
        relocated_package = workspace / "relocated-package"
        shutil.copytree(package, relocated_package)

        demo = workspace / "baseline-demo"
        run_mvp_demo(
            failure_run=baseline,
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

        store = workspace / ".rtl-agent/hkg"
        built = build_hkg_store(failure_packages=[package], output=store)
        assert built.source_count == 1
        original_graph = (store / "hkg.json").read_bytes()
        relocated = update_hkg_store(store=store, failure_packages=[relocated_package])
        assert relocated.changed is False
        assert (store / "hkg.json").read_bytes() == original_graph

        counterfactual = update_hkg_store(store=store, mvp_demos=[demo])
        assert counterfactual.changed is True
        assert counterfactual.intervention_count == 3
        assert counterfactual.experiment_count == 3

        later = _later_failure_run(workspace, repo)
        later_update = update_hkg_store(store=store, failure_runs=[later])
        assert later_update.changed is True
        inspection = inspect_hkg_store(store)
        assert inspection.valid and inspection.source_count == 3

        history_demo = workspace / "history-demo"
        history = run_mvp_demo(
            failure_run=later,
            repo=repo,
            config_path=repo / "rtl-agent.yaml",
            command="emit-vcd",
            stimulus=repo / "stimulus.json",
            allowed_files=[ALLOWED_FILE],
            output=history_demo,
            max_candidates=3,
            max_experiments=3,
            timeout=30,
            hkg_store=store,
        )
        assert history.historical_memory.status == "used"
        assert history.historical_memory.historical_match is True
        assert history.historical_memory.excluded_current_source_count == 1
        assert history.historical_memory.prior_failure_count == 1
        assert history.historical_memory.prior_intervention_count == 3
        assert any(
            "HKG memory found shared canonical fingerprint evidence" in basis
            for suggestion in history.repair_suggestions
            for basis in suggestion.evidence_basis
        )
        markdown = (history_demo / "mvp-demo-summary.md").read_text(encoding="utf-8")
        assert "## Historical evidence" in markdown
        assert "Historical canonical-fingerprint match: True" in markdown
        assert "not proof of a shared root cause" in markdown

        before_conflict = (
            (store / "hkg.json").read_bytes(),
            (store / "hkg-manifest.json").read_bytes(),
        )
        changed_demo = workspace / "changed-demo"
        shutil.copytree(demo, changed_demo)
        summary_path = changed_demo / "mvp-demo-summary.json"
        raw = json.loads(summary_path.read_text(encoding="utf-8"))
        raw["warnings"] = ["seeded same-identity content conflict"]
        summary_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            update_hkg_store(store=store, mvp_demos=[changed_demo])
        except HkgConflictError as exc:
            assert "source identity/content conflict" in str(exc)
        else:
            raise AssertionError("same-identity changed source was accepted")
        assert before_conflict == (
            (store / "hkg.json").read_bytes(),
            (store / "hkg-manifest.json").read_bytes(),
        )
        assert inspect_hkg_store(store).valid

        corrupted = workspace / "corrupted-store"
        shutil.copytree(store, corrupted)
        graph_path = corrupted / "hkg.json"
        graph_path.write_text(graph_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        corrupt_inspection = inspect_hkg_store(corrupted)
        assert not corrupt_inspection.valid
        assert any("hash mismatch" in warning for warning in corrupt_inspection.warnings)

        assert ROOT.exists()  # The check used only project-owned fixtures and temporary outputs.
        print(
            "persistent HKG lifecycle check passed "
            f"(sources={inspection.source_count}, nodes={inspection.node_count}, "
            f"edges={inspection.edge_count}, idempotent_update={not relocated.changed}, "
            f"history_match={history.historical_memory.historical_match}, "
            "self_excluded=1, source_conflict=rejected, graph_tamper=rejected)"
        )
    return 0


def _later_failure_run(workspace: Path, repo: Path) -> Path:
    store = RunStore(workspace / "later-runs", run_id="later")
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


if __name__ == "__main__":
    sys.exit(main())
