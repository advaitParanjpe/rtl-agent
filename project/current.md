# Cross-Module Ambiguity and Multi-Instance Robustness Pilot

## Objective

Validate that the existing failure-intelligence pipeline handles genuinely ambiguous hierarchical RTL honestly — reporting ambiguous signal-source mappings and preserved multi-candidate evidence rather than a false-confident single answer — while still localizing a seeded divergence. This milestone stresses the current architecture on ambiguity; it introduces no new analysis behaviour.

## Scope

- Extend the checked-in multi-file RTL fixtures with a case that legitimately creates ambiguity, such as: the same child module instantiated more than once, and/or a leaf signal name that appears in more than one module across separate files.
- Add a passing and a seeded-failing VCD pair over that hierarchy with a deterministic divergence on a signal whose source-mapping is genuinely ambiguous (matches more than one declaration/module) or whose leaf name is non-unique.
- Add a scripted check (for example `scripts/axi_router_ambiguity_pilot_check.py`) that drives the existing pipeline (the `run-failure-intelligence` orchestrator plus `inspect-run` and `export-failure-package`, reusing `scripts/_example_check.py`) over the fixtures in a temporary workspace, and register it in `scripts/check.py`.
- Assert, against the typed schemas, that the pipeline: identifies the expected earliest divergence; reports the ambiguous signal with an `ambiguous` (or multi-candidate) mapping status and preserves all candidate declarations/locations rather than collapsing to one; keeps the corresponding driver/dependency evidence multi-valued or explicitly unresolved where the RTL is genuinely ambiguous; still surfaces the divergence and its cited candidate locations in the failure report; exports and validates a portable failure package; and makes no causal or root-cause claim — using stable, schema-backed assertions only.
- Add one concise README mention of the ambiguity/multi-instance pilot.

## Acceptance Criteria

- The fixture creates real ambiguity (duplicate module instantiation and/or a non-unique leaf signal name across files), and the pipeline reports it honestly (ambiguous status and preserved multiple candidates), not a single false-confident mapping.
- The seeded divergence is still localized and its candidate source locations are cited; ambiguity is preserved end-to-end into the failure report.
- The check is local, deterministic, compact, independently runnable, and reuses the shared helper and existing services (no new product behavior, no simulator, no providers).
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add a simulator, waveform generation from RTL, real model-provider integration, external/remote repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not add new analysis behavior, disambiguation heuristics, dependency-graph algorithms, semantic elaboration, causal claims, or root-cause conclusions beyond what the existing services already produce.
- Do not hard-code expected answers into product services or create a parallel analysis path; keep fixtures compact.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
