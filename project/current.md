# External AXI Router Repository Integration

## Objective

Validate that the existing discovery, signal-source mapping, and driver-tracing services scale to real-world, non-synthetic RTL by running them over an external, open-source AXI-router-style repository vendored into the fixtures at a pinned commit. This is a robustness/validation milestone against genuine hierarchical code; it introduces no new analysis behaviour, requires no network access during the default run, and adds no model providers.

## Scope

- Vendor a compact subset of a real, license-compatible open-source AXI-router-style RTL repository under `examples/` (or a clearly-labelled `third_party/`/`external/` location), pinned to a specific upstream commit and carrying its upstream license and provenance (source URL + commit) in a short NOTICE/README. Keep only the RTL needed for the pilot; do not vendor build systems, large testbenches, or unrelated files.
- Add a gated check (for example `scripts/external_axi_router_repo_check.py`) that, when the vendored source is present, drives the existing services over the real hierarchy: `inspect-repo` (discovery), then `map-signals` and `trace-drivers` against a set of real hierarchical signal names taken from the actual modules, reusing `scripts/_example_check.py`.
- Assert, against the typed schemas, that discovery indexes the real modules across their files; that signal-source mapping resolves representative real signals to their declaring modules/files (honestly reporting exact/probable/ambiguous, not a false-confident answer); and that driver tracing recovers real continuous/procedural driver evidence and dependency edges from the actual RTL — using stable, schema-backed assertions robust to reasonable upstream formatting.
- Gate on availability: when the vendored source is absent, skip cleanly (reported, returning success) so `scripts/check.py` stays hermetic; the default run must not perform any network access (no clone/fetch at check time — vendoring happens once, out of band).
- Register the check in `scripts/check.py`; add one concise README mention with the upstream attribution.

## Acceptance Criteria

- The existing services run unmodified over a real external RTL hierarchy and produce honest, schema-valid discovery, mapping, and driver-trace artifacts (ambiguity preserved where the real code is genuinely ambiguous).
- The vendored source is pinned (commit recorded), license-compatible, attributed, and minimal; no network access occurs during `scripts/check.py`.
- When the vendored source is unavailable, the check skips cleanly and the default suite still passes hermetically.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes; no new analysis behaviour.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not fetch/clone/download anything during the default validation run; no network access at check time.
- Do not add new analysis behavior, disambiguation heuristics, dependency-graph algorithms, semantic elaboration, causal claims, or root-cause conclusions.
- Do not add a simulator requirement for this milestone, real model-provider integration, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not vendor license-incompatible code or large/unrelated upstream files; keep the subset minimal and attributed.
- Do not hard-code expected answers into product services or create a parallel analysis path.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
