# Simulator Failure Triage Integration Pilot

## Objective

Connect the simulator-generated failure flow to the existing execution and triage path, proving the end-to-end story: a real failing simulation run is captured and triaged into the existing structured command result, and the same failure is then localized by the failure-intelligence pipeline over the simulator-generated VCDs. Reuse existing services throughout; the simulator stays a gated fixture-generation/dev dependency. No new analysis behaviour and no model providers.

## Scope

- Reuse a checked-in simulatable design + testbench (the existing `examples/axi-router-sim*` fixtures, or a compact addition) whose seeded-failing build both dumps a VCD and exits/reports failure in a way the existing command runner and triage service can capture (for example a non-zero exit or a `$fatal`/assertion, and a VCD dump).
- Add a gated check (for example `scripts/axi_router_simulated_triage_check.py`) that, when Icarus Verilog is available: runs the failing simulation through the existing execution + triage path (the configured command runner / `triage-command` service) to produce the existing structured triage/command-result artifact; generates the passing-vs-failing VCD pair; drives the existing failure-intelligence pipeline over the generated VCDs; and asserts both the triage artifact (failure captured, classified into the existing structured result) and the localized divergence (earliest divergence, cross-file/source mapping, failure report) are produced and mutually consistent (they refer to the same failing run/design).
- Reuse the existing execution, triage, orchestration, inspection, and packaging services and the `scripts/_example_check.py` helper; do not add a new execution or triage path.
- Gate the simulator: when `iverilog`/`vvp` are unavailable, skip cleanly (reported, returning success) so `scripts/check.py` stays hermetic; never add the simulator to product install/runtime dependencies.
- Register the check in `scripts/check.py`; add one concise README mention.

## Acceptance Criteria

- When the simulator is available, a real failing simulation run is captured and triaged into the existing structured result, and the failure-intelligence pipeline localizes the same seeded divergence over the simulator-generated VCDs; the two are asserted to be consistent.
- The integration reuses existing services only — no new execution, triage, analysis, or orchestration path, and no product code changes beyond what is strictly necessary to wire the fixture.
- When the simulator is unavailable, the check is skipped cleanly and the default suite still passes hermetically; the simulator is never a product runtime dependency.
- Generation is deterministic; assertions are stable and schema-backed (no timestamps, hashes, durations, UUIDs, or absolute paths).
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not integrate a simulator into the product runtime, the CLI, or install dependencies; it is a gated fixture-generation/dev tool only.
- Do not add a new triage/classification path, new analysis behavior, dependency-graph algorithms, semantic elaboration, causal claims, or root-cause conclusions.
- Do not add real model-provider integration, external/remote repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not hard-code expected answers into product services or create a parallel analysis path; keep fixtures compact.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
