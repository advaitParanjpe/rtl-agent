# Failure Family Clustering Across Regression Runs

## Objective

Build a deterministic, read-only grouping/reporting affordance over existing failure-fingerprint JSON files from multiple regression runs so recurring observed failure families can be summarized without relying on volatile run metadata or conversation history.

## Scope

- Add a typed, versioned clustering/report model that consumes existing failure-fingerprint JSON files and never recomputes waveform, RTL, driver, or semantic analysis.
- Group fingerprints by `family_digest`, preserve exact-fingerprint distinctions within each family, and list run/fingerprint inputs using stable relative or user-supplied labels rather than volatile absolute paths where practical.
- For each family, emit a representative component summary plus deterministic per-member differences using the existing fingerprint comparison semantics.
- Report insufficient-evidence fingerprints separately or inside each group with explicit reasons; do not force weak evidence into a confident family.
- Add a small read-only CLI command that writes the cluster report and concise human-readable summary.
- Add deterministic tests for repeated exact fingerprints, shifted-time same-family grouping, materially different family separation, insufficient evidence handling, stable ordering/serialization, and malformed input.

## Acceptance Criteria

- Multiple fingerprint files can be grouped deterministically by observed failure family, with exact identities and component differences preserved.
- Ambiguous or insufficient evidence remains explicit and never becomes a confident cluster.
- The command is read-only with respect to source runs/fingerprints and depends only on existing fingerprint artifacts.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No clustering infrastructure beyond deterministic local grouping over provided files.
- No databases, remote indexes, machine learning, semantic causal inference, automatic patch generation, stimulus minimization, or new waveform analysis.
- No changes to public fingerprint semantics unless a gap is proven by tests or real evidence.

## Completion State

Active.
