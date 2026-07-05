# Simulator-Generated Multi-Module Failure Pilot

## Objective

Combine the two validated threads — simulator-generated waveforms and hierarchical multi-file RTL — into one pilot: use a real open-source simulator to produce the passing-vs-failing VCD pair over a top module that instantiates child modules across separate files, and prove the existing pipeline resolves cross-file source mapping and reconstructs the cross-module driver/dependency chain to localize the seeded divergence. The simulator stays a gated fixture-generation/dev dependency; no new analysis behaviour and no model providers.

## Scope

- Add a small, simulatable hierarchical RTL design under `examples/` (a top module instantiating at least two child modules from separate `.sv` files, with real drivers and a signal that propagates across a module boundary) plus a compact testbench that dumps a VCD over the observed hierarchy.
- Select the seeded fault with a compile-time define (or equivalent) so the same deterministic stimulus yields a passing run and a failing run in which a child-module-driven signal diverges and propagates across the boundary.
- Add a gated check (for example `scripts/axi_router_simulated_multimodule_check.py`) that detects the simulator (Icarus Verilog `iverilog`/`vvp`), and when present compiles + runs the two builds to generate the VCD pair, drives the existing pipeline (`run-failure-intelligence` plus `inspect-run` and `export-failure-package`, reusing `scripts/_example_check.py`) over the generated VCDs, and asserts: the seeded divergence's earliest signal/time; cross-file source mapping to the correct child module/file; cross-module driver/dependency edges cited to more than one file; a connected divergence graph; failure-report source locations; and portable-package export — using stable, schema-backed assertions only.
- When the simulator is unavailable, skip cleanly (reported as skipped, returning success) so `scripts/check.py` stays hermetic; never add the simulator to product install/runtime dependencies.
- Register the check in `scripts/check.py` and add one concise README mention.

## Acceptance Criteria

- When the simulator is available, the passing and failing VCDs are simulator-generated from the checked-in hierarchical RTL + testbench, and the pipeline localizes the seeded divergence to the correct child file with cross-module driver/dependency evidence cited across more than one file.
- When the simulator is unavailable, the check is skipped cleanly and the default suite still passes hermetically; the simulator is never a product runtime dependency.
- The generation is deterministic; assertions are stable and schema-backed (no timestamps, hashes, durations, UUIDs, or absolute paths).
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes; no new analysis behaviour.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not integrate a simulator into the product runtime, the CLI, or install dependencies; it is a gated fixture-generation/dev tool only.
- Do not add real model-provider integration, external/remote repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not add new analysis behavior, dependency-graph algorithms, semantic elaboration, causal claims, or root-cause conclusions beyond what the existing services already produce.
- Do not hard-code expected answers into product services or create a parallel analysis path; keep fixtures compact.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
