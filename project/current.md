# Simulator-Generated AXI Failure Pilot

## Objective

Strengthen one AXI-router pilot by replacing its hand-authored VCD fixtures with waveforms produced by an actual open-source simulator run over the checked-in RTL and a small testbench, so the failing-vs-passing pair is genuinely simulator-generated rather than authored. Drive the existing failure-intelligence pipeline over the generated VCDs and assert the seeded divergence is still localized. The simulator is a fixture-generation/dev dependency only; its use must be gated so the default validation suite stays hermetic. No new analysis behaviour and no model providers.

## Scope

- Add a small synthesizable/simulatable RTL design plus a compact testbench (under `examples/`) that produces a passing run and a seeded-failing run of the same design (for example a parameter/define or a `+arg` that injects the seeded fault), each dumping a VCD over the observed signal hierarchy.
- Add a deterministic, checked-in generation script that runs an open-source simulator (for example Icarus Verilog `iverilog`/`vvp`, or Verilator) to compile the testbench and emit the passing and failing VCDs into a temporary or ignored location. The simulator is a fixture-generation/dev dependency, not a product runtime dependency.
- Gate the simulator use: detect whether the simulator binary is available and, when it is not, skip that generation/validation step cleanly (clearly reported as skipped) so `scripts/check.py` remains hermetic and green on machines without the tool. Do not add the simulator to the product's install/runtime dependencies.
- Add a scripted check (for example `scripts/axi_router_simulated_failure_check.py`) that — when the simulator is available — generates the VCD pair, drives the existing pipeline (`run-failure-intelligence` plus `inspect-run` and `export-failure-package`, reusing `scripts/_example_check.py`) over the generated VCDs in a temporary workspace, and asserts the seeded divergence is localized (earliest divergent signal/time, source mapping, driver/dependency evidence, failure report, portable package) using stable, schema-backed assertions only.
- Register the check in `scripts/check.py` such that it runs when the simulator is present and is skipped-with-notice otherwise.
- Add one concise README mention of the simulator-generated pilot and how it is gated.

## Acceptance Criteria

- When the simulator is available, the passing and failing VCDs are produced by the simulator (not hand-authored) from the checked-in RTL + testbench, and the existing pipeline localizes the seeded divergence over them.
- When the simulator is unavailable, the check is skipped cleanly and the default validation suite still passes hermetically; the simulator is never added as a product runtime dependency.
- The generation is deterministic and reproducible (fixed seed/inputs), and assertions are stable and schema-backed (no timestamps, hashes, durations, UUIDs, or absolute paths).
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes; no new analysis behaviour.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not integrate a simulator into the product runtime, the CLI, or the install dependencies; it is a gated fixture-generation/dev tool only.
- Do not add real model-provider integration, external/remote repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not add new analysis behavior, dependency-graph algorithms, semantic elaboration, causal claims, or root-cause conclusions beyond what the existing services already produce.
- Do not hard-code expected answers into product services or create a parallel analysis path; keep fixtures compact.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
