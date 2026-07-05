"""Validate the pipeline services against a real external AXI-router codebase.

This pilot drives the existing repository-discovery, signal-source-mapping, and
static driver-tracing services over a vendored, pinned subset of
alexforencich/verilog-axis (MIT): the arbitrated AXI-stream mux router path
(``axis_arb_mux`` -> ``arbiter`` -> ``priority_encoder``) plus ``axis_demux``.
The upstream RTL is checked in verbatim under
``examples/external/verilog-axis/upstream/`` so canonical validation performs no
network access; before any analysis runs, this check verifies provenance (pinned
commit, license, attribution, and per-file sha256 digests from
``PROVENANCE.json``) so the vendored snapshot cannot silently drift.

Assertions target honest behaviour on real code: real module discovery and
hierarchy, exact mapping where the scope names the module, preserved
multi-candidate evidence on nested instance paths, honest unresolved results,
real procedural and continuous driver statements at their actual source lines,
and bounded artifact sizes. Known limitations discovered here (declaration
line-number skew from leading blank lines, shallow-scope primary preference on
nested paths, cross-file conflation of same-named identifiers) are recorded in
project history rather than papered over with fixture-specific assertions.

If the vendored snapshot is absent the check skips cleanly, keeping the default
suite hermetic. No new analysis behaviour is added.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

from _example_check import ROOT, run_cli

from rtl_agent.repository_map import RepositoryMap
from rtl_agent.rtl_driver_trace_models import RtlDriverTraceReport
from rtl_agent.signal_source_map_models import SignalSourceMapReport

FIXTURE = ROOT / "examples" / "external" / "verilog-axis"
UPSTREAM = FIXTURE / "upstream"
RTL_DIR = UPSTREAM / "rtl"
PROVENANCE = FIXTURE / "PROVENANCE.json"

EXPECTED_MODULES = {
    "arbiter.v": "arbiter",
    "axis_arb_mux.v": "axis_arb_mux",
    "axis_demux.v": "axis_demux",
    "priority_encoder.v": "priority_encoder",
}
MAX_ARTIFACT_BYTES = 256 * 1024

SIGNALS = [
    "tb.axis_arb_mux.m_axis_tdata",
    "tb.axis_arb_mux.m_axis_tdata_reg",
    "tb.axis_arb_mux.arbiter.grant_reg",
    "tb.axis_demux.m_axis_tvalid_reg",
    "tb.monitor.debug_count",
]


def main() -> int:
    if not PROVENANCE.exists() or not RTL_DIR.is_dir():
        print("external axi router repo check skipped (vendored snapshot not present)")
        return 0

    _check_provenance()

    with tempfile.TemporaryDirectory(prefix="rtl-agent-ext-axis-") as raw_tmp:
        workspace = Path(raw_tmp)
        repo_map_path = workspace / "repository-map.json"
        signal_map_path = workspace / "signal-source-map.json"
        trace_path = workspace / "driver-trace.json"

        run_cli(["inspect-repo", "--repo", str(RTL_DIR), "--output", str(repo_map_path)])
        _check_discovery(repo_map_path)

        run_cli(
            [
                "map-signals",
                "--repository-map",
                str(repo_map_path),
                *[arg for name in SIGNALS for arg in ("--signal", name)],
                "--output",
                str(signal_map_path),
            ]
        )
        _check_mapping(signal_map_path)

        run_cli(
            [
                "trace-drivers",
                "--signal-source-map",
                str(signal_map_path),
                "--repository-map",
                str(repo_map_path),
                "--output",
                str(trace_path),
            ]
        )
        _check_driver_trace(trace_path)

        for artifact in (repo_map_path, signal_map_path, trace_path):
            assert artifact.stat().st_size <= MAX_ARTIFACT_BYTES, artifact

    print("external axi router repo check passed")
    return 0


def _check_provenance() -> None:
    """The pinned commit, source paths, license, and digests must not drift."""

    record = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    assert record["upstream_url"] == "https://github.com/alexforencich/verilog-axis"
    assert re.fullmatch(r"[0-9a-f]{40}", record["upstream_commit"])
    assert record["license"] == "MIT"
    assert "Alex Forencich" in record["copyright"]

    files: dict[str, str] = record["files"]
    for relative, expected_sha in files.items():
        path = FIXTURE / relative
        assert path.exists(), f"vendored file missing: {relative}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == expected_sha, f"vendored file drifted from pinned upstream: {relative}"

    license_text = (FIXTURE / record["license_file"]).read_text(encoding="utf-8")
    assert "Permission is hereby granted" in license_text
    assert "Alex Forencich" in license_text

    # Every file under upstream/ must be accounted for in the provenance record.
    actual = {
        path.relative_to(FIXTURE).as_posix() for path in UPSTREAM.rglob("*") if path.is_file()
    }
    assert actual == set(files), f"unlisted or missing upstream files: {actual ^ set(files)}"


def _check_discovery(repo_map_path: Path) -> None:
    repository_map = RepositoryMap.model_validate_json(repo_map_path.read_text(encoding="utf-8"))
    modules_by_file: dict[str, list[str]] = {}
    for record in repository_map.files:
        assert "rtl_source" in [str(c) for c in record.categories], record.path
        if record.source is not None:
            modules_by_file[record.path] = [d.name for d in record.source.declarations]
            for declaration in record.source.declarations:
                assert str(declaration.kind) == "module"
                # NOTE: exact line numbers are deliberately not asserted; on this
                # real code discovery currently reports the declaration a few
                # lines early (recorded limitation: leading blank lines are
                # swallowed by the declaration regex).
                assert declaration.line >= 1
    assert {path: names[0] for path, names in modules_by_file.items()} == EXPECTED_MODULES

    hierarchy = repository_map.hierarchy
    # The real instantiation hierarchy: axis_arb_mux instantiates arbiter, which
    # instantiates priority_encoder; the two entry modules are uninstantiated.
    assert set(hierarchy.instantiated_types) == {"arbiter", "priority_encoder"}
    assert set(hierarchy.uninstantiated_modules) == {"axis_arb_mux", "axis_demux"}


def _check_mapping(signal_map_path: Path) -> None:
    signal_map = SignalSourceMapReport.model_validate_json(
        signal_map_path.read_text(encoding="utf-8")
    )
    mappings = {mapping.signal: mapping for mapping in signal_map.mappings}

    # Scope naming the module directly -> exact, single-file candidates.
    tdata = mappings["tb.axis_arb_mux.m_axis_tdata_reg"]
    assert tdata.status == "exact"
    assert {c.file_path for c in tdata.candidates} == {"axis_arb_mux.v"}

    demux = mappings["tb.axis_demux.m_axis_tvalid_reg"]
    assert demux.status == "exact"
    assert {c.file_path for c in demux.candidates} == {"axis_demux.v"}

    # Nested instance path: both the outer and inner module files are preserved
    # as candidates. (Recorded limitation: the primary candidate is currently
    # the shallower scope component, axis_arb_mux, not the declaring arbiter.)
    nested = mappings["tb.axis_arb_mux.arbiter.grant_reg"]
    assert {c.file_path for c in nested.candidates} == {"arbiter.v", "axis_arb_mux.v"}

    # A path with no matching declaration stays honestly unresolved.
    assert mappings["tb.monitor.debug_count"].status == "unresolved"
    assert mappings["tb.monitor.debug_count"].candidates == []
    assert signal_map.unresolved_count == 1


def _check_driver_trace(trace_path: Path) -> None:
    trace = RtlDriverTraceReport.model_validate_json(trace_path.read_text(encoding="utf-8"))
    traced = {signal.signal: signal for signal in trace.traced_signals}

    # Real continuous driver evidence at its actual source line.
    tdata_port = traced["tb.axis_arb_mux.m_axis_tdata"]
    assert tdata_port.status == "traced"
    assert any(
        str(d.kind) == "continuous_assign"
        and d.file_path == "axis_arb_mux.v"
        and d.line == 231
        and "assign m_axis_tdata" in (d.statement_text or "")
        for d in tdata_port.drivers
    )

    # Real procedural driver evidence in the arbitrated mux output register.
    tdata_reg = traced["tb.axis_arb_mux.m_axis_tdata_reg"]
    assert tdata_reg.status == "traced"
    assert any(
        str(d.kind) == "procedural_assign"
        and d.file_path == "axis_arb_mux.v"
        and "m_axis_tdata_reg <= m_axis_tdata_int;" in (d.statement_text or "")
        for d in tdata_reg.drivers
    )

    # The nested arbiter register is traced to its true declaring file because
    # tracing searches every preserved candidate file.
    grant = traced["tb.axis_arb_mux.arbiter.grant_reg"]
    assert grant.status == "traced"
    assert any(
        str(d.kind) == "procedural_assign"
        and d.file_path == "arbiter.v"
        and d.line == 144
        and "grant_reg <= grant_next;" in (d.statement_text or "")
        for d in grant.drivers
    )
    edge_files = {
        edge.evidence_file
        for edge in trace.dependency_edges
        if edge.source_signal == "grant_reg" or edge.depends_on == "grant_reg"
    }
    assert "arbiter.v" in edge_files

    # Unmapped input stays honestly untraced, and expansion stays bounded.
    assert traced["tb.monitor.debug_count"].status == "unmapped"
    assert trace.truncated is False
    assert trace.unresolved_identifiers, "real code should leave some identifiers unresolved"


if __name__ == "__main__":
    sys.exit(main())
