# Real AXI Router Repository Pilot

## Objective

Pilot the existing failure-intelligence pipeline against a larger, multi-file AXI-router-style RTL repository whose signal hierarchy spans several modules across files, proving the pipeline resolves cross-file signal-source mapping and cross-module driver/dependency evidence and still localizes a seeded divergence. Reuse the existing services and example-check helper; add no new analysis behavior, no simulator, and no model providers.

## Scope

- Add a compact but multi-file checked-in RTL repository under `examples/` (an AXI-router-style top module instantiating at least two distinct child modules across separate `.sv` files, with real continuous and procedural drivers and a signal hierarchy that crosses module boundaries) plus an rtl-agent config.
- Add a seeded failing-vs-passing VCD pair over that hierarchy's signals, differing deterministically on a divergent signal whose driver and dependencies live in a child module reached through the top module (so localization must resolve across files/modules).
- Add `scripts/axi_router_repository_pilot_check.py` that drives the existing pipeline (the `run-failure-intelligence` orchestrator plus `inspect-run` and `export-failure-package`, reusing the shared `scripts/_example_check.py` helper) over the checked-in fixtures in a temporary workspace, and register it in `scripts/check.py`.
- Assert, against the typed schemas, that the pipeline: identifies the expected earliest divergent signal and time; maps the divergent signal to the correct child module and file (not merely the top module); extracts real driver and dependency evidence spanning more than one module/file; produces a connected divergence graph with cited cross-file edges; surfaces the correct source location and textual driver evidence in the synthesized failure report; exports and validates a portable failure package; and preserves ambiguity without causal or root-cause claims — using stable, schema-backed assertions only (no timestamps, hashes, durations, UUIDs, or absolute paths).
- Add one concise README mention of the multi-file repository pilot.

## Acceptance Criteria

- The pilot exercises genuine cross-file and cross-module resolution (a signal declared/driven in a child module, reached through the top module), not just intra-file tracing.
- The seeded divergence is localized to the correct child module/file with cited driver and dependency evidence, and the divergence graph is connected across files.
- The check is local, deterministic, compact, independently runnable, and reuses the shared helper and existing services (no new product behavior, no simulator, no providers).
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add a simulator, waveform generation from RTL, real model-provider integration, external/remote repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not add new analysis behavior, dependency-graph algorithms, semantic elaboration, causal claims, or root-cause conclusions beyond what the existing services already produce.
- Do not hard-code expected answers into product services or create a parallel analysis path; keep fixtures compact.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
