# Signal-to-RTL Source Mapping

## Objective

Deterministically map hierarchical waveform signal names to their declaring RTL source locations using the existing repository map's declaration evidence, and emit a typed, versioned mapping report. Report only declaration-evidence matches; never elaborate semantics, infer connectivity, or claim causal meaning.

## Scope

- Add a typed, versioned signal-to-source mapping report schema.
- Add a deterministic service that consumes an existing repository-map artifact plus a set of hierarchical signal names (supplied directly, or read from a reduced waveform-slice or a waveform-comparison report) and, for each signal, resolves candidate RTL source locations from `FileRecord.source.declarations` (declaration name, kind, file path, line).
- Match by the signal's leaf name against declaration names, and use the signal's scope components (module hierarchy) to disambiguate where the repository map provides module/declaration evidence.
- For each signal report: resolved status (resolved / unresolved / ambiguous), the candidate declaration location(s) with kind and line, and the basis for the match.
- Add a CLI command such as `map-signals`.
- Reuse the existing repository-map, reduced-slice, and comparison models; do not re-scan the repository or re-parse RTL.
- Emit bounded, stably ordered output with deterministic serialization.
- Fail or warn honestly: signals with no matching declaration are unresolved; signals matching multiple declarations are ambiguous and never silently collapsed to one.
- Add compact fixtures and tests covering a resolved signal, an unresolved signal, an ambiguous (multi-declaration) signal, scope-based disambiguation, empty input, and deterministic output.
- Add one concise runnable README example.

## Acceptance Criteria

- Mapping is deterministic, bounded, and cites explicit declaration evidence (path, line, kind) for each resolved signal.
- Unresolved and ambiguous signals are reported explicitly, not dropped or guessed.
- Output ordering and serialization are stable across repeated runs.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not perform semantic elaboration, parameter resolution, generate expansion, connectivity/dependency tracing, model-based analysis, stimulus minimization, patch generation, or causal claims.
- Do not re-scan the repository or re-parse RTL; consume the existing repository-map artifact.
- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
