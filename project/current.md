# Compact Failure Intelligence Example Check

## Objective

Add a compact, deterministic local scripted example check that exercises the full failure-intelligence pipeline over checked-in fixtures, validating that the commands compose end-to-end and emit stable, schema-backed artifacts. Assert only stable fields; introduce no new product behavior.

## Scope

- Add `scripts/failure_intelligence_example_check.py` that, in a temporary workspace, chains the real CLI:
  - `extract-waveform-window` for a failing slice (the checked-in `examples/waveforms/failure.vcd`) and a passing/reference slice (a checked-in or generated variant);
  - `compare-waveforms` over the two slices;
  - `inspect-repo` on `examples/simple-rtl`;
  - `map-signals` for the diverging signals (from the comparison);
  - `trace-drivers` from the signal-source map;
  - `divergence-graph` composing comparison + signal-source map + driver trace;
  - `reduce-signals` on the failing slice.
- Reuse the shared `scripts/_example_check.py` helper for repository root, interpreter selection, and `run_cli`.
- Validate emitted artifacts through the existing typed models, asserting stable schema versions, statuses, and structural fields (not volatile timestamps, hashes, durations, UUIDs, or absolute paths).
- Register the new check in `scripts/check.py` and mention it in the README's example-check summary where the other example checks are described.
- Add a compact checked-in passing-waveform fixture under `examples/waveforms/` if one is needed for a deterministic comparison.
- Keep generated outputs in temporary or ignored artifact directories.

## Acceptance Criteria

- The example check is local, deterministic, compact, and independently runnable.
- It reuses the shared helper without adding new dependencies or a framework.
- It asserts on stable schema versions, statuses, identifiers, and structural fields rather than volatile values.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not change generated artifact schemas, CLI behavior, provider behavior, or product workflow features.
- Do not add semantic waveform interpretation, dependency-tracing beyond existing textual evidence, model-based analysis, causal claims, or large generated artifacts under tracked paths.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
