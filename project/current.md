# Static RTL Driver and Dependency Tracing

## Objective

For signals already mapped to declaring RTL files, deterministically extract static, textual driver and dependency evidence — the assignment and port-connection statements that reference each signal by name, plus the right-hand-side signal names they reference — and emit a typed, versioned artifact with source locations. Evidence is textual only; never elaborate, simulate, or claim semantic dataflow or causal meaning.

## Scope

- Add a typed, versioned driver/dependency evidence report schema.
- Add a deterministic service that consumes an existing signal-source-map report (and the repository map for file paths and `repository_root`) and, for each resolved/probable mapped signal, performs a bounded textual scan of the declaring RTL file(s) for statements referencing the signal's leaf name:
  - assignment drivers (`assign` and procedural `<=`/`=`) where the signal appears as the left-hand side;
  - port connections (`.port(signal)` style) that reference the signal;
  - and the right-hand-side identifiers referenced by those statements (candidate dependencies).
- Record, per matched statement: file path, line number, statement kind (continuous assign / procedural assign / port connection / other reference), the bounded statement text, and the referenced identifier names.
- Add a CLI command such as `trace-drivers`.
- Reuse the existing repository-map and signal-source-map models; read RTL files only for bounded textual scanning (no re-derivation of the repository map).
- Emit bounded, stably ordered output with deterministic serialization.
- Fail or warn honestly: unresolved/unmapped signals, missing files, and signals with no textual references are reported explicitly; matches are labeled as textual evidence, not proven drivers.
- Add compact fixtures and tests covering a continuous-assign driver, a procedural driver, a port connection, a signal with no drivers, a missing file, and deterministic output.
- Add one concise runnable README example.

## Acceptance Criteria

- Extraction is deterministic, bounded, and cites explicit source locations and statement text for every match.
- Referenced right-hand-side identifiers are recorded as textual candidates, not asserted dependencies.
- Output ordering and serialization are stable across repeated runs.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not elaborate, preprocess, expand macros/generates, resolve parameters, simulate, build a semantic dataflow graph, or make causal claims.
- Do not resolve instance-to-module-type connectivity beyond textual port-connection matches.
- Do not add source rewriting, patch generation, FST/FSDB support, model-based analysis, or stimulus minimization.
- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
