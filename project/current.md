# Automatic Relevant-Signal Reduction

## Objective

Deterministically reduce a waveform slice's signal set to a bounded, evidence-ranked "relevant" subset for a failure, using only explicit textual and transition evidence already present in existing artifacts. Never interpret causal meaning, trace signal dependencies, or claim root cause.

## Scope

- Add a typed, versioned relevant-signal-reduction report schema.
- Add a deterministic service that consumes an existing waveform-slice report (and optionally the assertion-link and/or triage report for context) and ranks each slice signal by explicit, evidence-cited criteria:
  - the signal name or label appears in the selected assertion summary/`signal_or_label`;
  - the signal has one or more value transitions inside the window;
  - the signal carries unknown (`x`) or high-impedance (`z`) values inside the window;
  - the signal shares a hierarchical scope prefix with the assertion's named signal.
- Emit a bounded, stably ordered reduced signal set, each entry citing which criteria matched and a deterministic score, plus the signals excluded with reasons summarized.
- Add a CLI command such as `reduce-signals`.
- Reuse existing waveform-slice, assertion-link, and triage models; do not re-parse VCD or re-extract windows.
- Fail or warn honestly: no candidate signals, an empty slice, or no matching evidence yields an empty reduced set with a clear warning; never silently invent relevance.
- Add compact fixtures and tests covering assertion-name matches, transition-only signals, `x`/`z` signals, hierarchical-prefix matches, empty results, and deterministic output.
- Add one concise runnable README example.

## Acceptance Criteria

- Reduction is deterministic, bounded, and cites explicit evidence per retained signal.
- The reduced set is a strict subset of the input slice's signals; nothing is invented.
- Output ordering and serialization are stable across repeated runs.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add signal-dependency tracing, semantic waveform interpretation, model-based analysis, source localization, stimulus minimization, or patch generation.
- Do not re-parse VCD or duplicate waveform-window extraction; consume the existing slice artifact.
- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
