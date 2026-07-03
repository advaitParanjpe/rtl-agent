# Failure Divergence Graph

## Objective

Deterministically compose existing waveform-comparison divergences and static driver/dependency evidence into a single typed, versioned graph artifact rooted at the diverging signals. The graph is a compositional view over prior artifacts; it makes no causal or root-cause claims and performs no new analysis.

## Scope

- Add a typed, versioned failure-divergence-graph report schema.
- Add a deterministic service that consumes an existing waveform-comparison report, a signal-source-map report, and a driver-trace report, and builds a bounded directed graph:
  - root nodes are the diverging signals from the comparison (with their first divergence time, values, and divergence score attached);
  - nodes carry attributes composed from prior artifacts only: divergence info (if any), mapping status/declaration location (if any), and driver-resolution status (resolved / unresolved);
  - edges are the driver-trace dependency edges (`textual` / `inferred_textual`), each citing its prior-artifact evidence (file, line, statement kind).
- Bound the graph by a configurable maximum depth from the roots and a maximum node count; record truncation explicitly.
- Add a CLI command such as `divergence-graph`.
- Reuse the existing comparison, signal-source-map, and driver-trace models; do not re-scan RTL, re-parse VCD, or recompute divergences or drivers.
- Emit bounded, stably ordered output with deterministic serialization.
- Fail or warn honestly: no diverging signals, missing cross-references between artifacts, and unresolved identifiers are reported explicitly; ambiguity is preserved.
- Add compact fixtures and tests covering root selection from divergences, edge composition from driver evidence, unresolved/leaf nodes, depth/node bounding, empty input, and deterministic output.
- Add one concise runnable README example.

## Acceptance Criteria

- The graph is deterministic, bounded, and composed strictly from prior-artifact evidence; every edge cites its source artifact location.
- Divergence roots, node attributes, and edges are derived from the input reports without new RTL scanning or semantic inference.
- Nodes and edges are stably ordered and serialization is stable across repeated runs.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not make causal or root-cause claims, rank nodes as causes, or infer semantic dataflow.
- Do not re-scan RTL, re-parse VCD, elaborate, preprocess, or recompute comparison/driver evidence; compose only.
- Do not add source rewriting, patch generation, FST/FSDB support, model-based analysis, or stimulus minimization.
- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
