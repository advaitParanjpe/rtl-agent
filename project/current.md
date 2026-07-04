# Compact Failure Report Synthesis

## Objective

Deterministically compose the existing failure-intelligence artifacts into a single typed, versioned failure-report artifact: a compact, evidence-cited summary of the observed failure signature. The report is a compositional view over prior artifacts; it makes no causal or root-cause claims and performs no new analysis.

## Scope

- Add a typed, versioned failure-report schema.
- Add a deterministic service that consumes an existing failure-divergence-graph report plus its upstream artifacts (waveform comparison, signal-source map, driver trace, relevant-signal reduction, and optionally triage and verification-strength reports) and produces a compact summary:
  - the observed failure signature: diverging signals with first divergence time and values, and the global earliest divergence;
  - per-signal mapped source locations (declaration file/line/kind) and driver-resolution status, composed from the prior reports;
  - referenced upstream artifact paths (with recorded provenance) for every cited fact;
  - counts of resolved / unresolved identifiers and any cross-artifact warnings.
- Add a CLI command such as `synthesize-failure-report`.
- Reuse the existing comparison, signal-source-map, driver-trace, divergence-graph, reduction, triage, and verification-strength models; do not re-scan RTL, re-parse VCD, or recompute divergences, mappings, or drivers.
- Emit bounded, stably ordered output with deterministic serialization.
- Fail or warn honestly: missing optional inputs, empty divergences, and cross-artifact inconsistencies are reported explicitly; ambiguity and unresolved identifiers are preserved.
- Add compact fixtures and tests covering signature summarization, source-location composition, optional-input handling, empty input, and deterministic output.
- Add one concise runnable README example.

## Acceptance Criteria

- The failure report is deterministic, bounded, and composed strictly from prior-artifact evidence; every cited fact references its source artifact.
- Diverging signals, source locations, and driver/unresolved status are derived from the input reports without new RTL scanning or semantic inference.
- Output ordering and serialization are stable across repeated runs.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not make causal or root-cause claims, rank signals as causes, or infer semantic dataflow.
- Do not re-scan RTL, re-parse VCD, elaborate, or recompute comparison/mapping/driver evidence; compose only.
- Do not add source rewriting, patch generation, FST/FSDB support, model-based analysis, or stimulus minimization.
- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
