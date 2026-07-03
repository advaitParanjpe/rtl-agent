# Passing-vs-Failing Waveform Comparison

## Objective

Deterministically compare a failing waveform slice against a passing (reference) waveform slice over their shared signals and time window, and emit a typed, versioned comparison artifact that reports per-signal value-timeline divergences. Report only observable differences; never interpret causal meaning or claim root cause.

## Scope

- Add a typed, versioned waveform-comparison report schema.
- Add a deterministic service that consumes two existing waveform-slice reports (a failing slice and a passing/reference slice) and, for each signal present in both, compares the ordered value timeline (initial value at window start plus in-window transitions).
- For each compared signal, report: whether timelines are identical, the first divergence time, the differing values at that point, and counts of differing transition points.
- Report signals present in only one slice (added/removed relative to the reference) and any window or timescale mismatch as explicit warnings.
- Add a CLI command such as `compare-waveforms`.
- Reuse the existing waveform-slice models and, where practical, the relevant-signal-reduction output as the signal set to compare; do not re-parse VCD or re-extract windows.
- Emit bounded, stably ordered output with deterministic serialization.
- Fail or warn honestly: no shared signals, empty slices, or incompatible windows yield clear warnings; never invent divergences.
- Add compact fixtures and tests covering identical timelines, first-divergence detection, added/removed signals, window/timescale mismatch, empty results, and deterministic output.
- Add one concise runnable README example.

## Acceptance Criteria

- Comparison is deterministic, bounded, and reports only observable value/timeline differences with explicit evidence (times and values).
- Signals compared are those present in both slices; added/removed signals are reported separately, not silently dropped.
- Output ordering and serialization are stable across repeated runs.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not make causal claims, trace signal dependencies, interpret waveform semantics, localize RTL source, perform model-based analysis, or minimize stimulus.
- Do not re-parse VCD or duplicate waveform-window extraction; consume the existing slice artifacts.
- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
