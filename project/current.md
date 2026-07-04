# AXI Router Seeded-Failure Validation

## Objective

Validate the end-to-end failure-intelligence pipeline on a compact, checked-in AXI-router-style RTL example with a seeded, deterministic failure, proving the pipeline localizes the seeded divergence to real RTL driver evidence. Reuse the existing services and example-check helper; add no new analysis behavior, no simulator, and no model providers.

## Scope

- Add a compact checked-in AXI-router-style RTL example under `examples/` (a small SystemVerilog design and an rtl-agent config) whose top module actually declares and drives the waveform signals (continuous and/or procedural assignments), so repository discovery, signal-source mapping, and driver tracing produce real declarations and driver edges.
- Add a seeded failing-vs-passing VCD pair over that design's hierarchical signals, differing deterministically on one seeded output signal (for example an unexpected `x`/wrong value), with the other signals identical, so the comparison yields a clear diverging signal.
- Add `scripts/axi_router_seeded_failure_check.py` that drives the existing pipeline over the checked-in fixtures (reusing the shared `scripts/_example_check.py` helper and the existing CLI/services — `extract-waveform-window`, `compare-waveforms`, `inspect-repo`, `map-signals`, `trace-drivers`, `divergence-graph`, `reduce-signals`, and the failure report), in a temporary workspace.
- Assert the pipeline localizes the seeded failure: the seeded signal is among the diverging signals with the expected first divergence, it maps to the AXI-router module source (file/line), driver tracing finds the driver statement(s) for the seeded signal, the divergence graph roots at it with real dependency edges, and the synthesized failure report surfaces it — all via stable, schema-backed assertions (not timestamps, hashes, durations, UUIDs, or absolute paths).
- Register the new check in `scripts/check.py`; keep generated outputs in temporary or ignored directories.
- Add one concise README mention of the AXI-router validation example.

## Acceptance Criteria

- The check is local, deterministic, compact, and independently runnable, and reuses the shared helper and existing services (no new product behavior, no simulator, no providers).
- The seeded design drives the waveform signals so driver tracing and the divergence graph produce real driver evidence for the seeded signal.
- Assertions are stable and schema-backed (diverging-signal set, mapped source location, driver statement presence, failure-report content), not volatile values.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add a simulator, waveform generation from RTL, real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not add new analysis behavior, causal claims, or root-cause conclusions beyond what the existing services already produce.
- Do not add large generated artifacts under tracked paths; keep the RTL and VCD fixtures compact.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
