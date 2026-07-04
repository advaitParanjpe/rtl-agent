# Failure Intelligence Run Portability and Relative Provenance

## Objective

Make a failure-intelligence run directory portable: record run-relative (not absolute) provenance so a completed run can be inspected, resumed, or replayed after the run directory is moved or copied. Reuse the existing orchestration and stage services; add no new analysis behavior.

## Scope

- Record run-relative artifact provenance in the run manifest: store artifact locations, and the run inputs where they live under the run directory, as paths relative to the run directory rather than absolute paths, so the manifest does not depend on the run directory's absolute location.
- Resolve run-relative provenance against the current run directory when reading the manifest for resume/replay, so validation works after the directory is relocated.
- Keep resume/replay artifact validation working across relocation: existence, recorded SHA-256, typed-model validation, supported schema version, and run-input matching must all still hold when the run directory has moved (compare on run-relative terms for run-internal inputs; keep external inputs such as the source VCDs and repository absolute since they live outside the run).
- Where the underlying stage artifacts embed absolute run-internal paths that defeat portability, record enough run-relative provenance in the manifest to resume/replay without depending on those absolute values; do not change the stage artifact schemas.
- Bump the run-manifest schema version if fields change, and update existing readers and tests accordingly; do not add automatic migration of unsupported schemas.
- Add compact tests covering: a run directory that is moved/copied and then resumed (all reused), replayed from a stage after relocation, and validation that still regenerates on tampered artifacts after relocation.
- Add one concise runnable README note on portability.

## Acceptance Criteria

- A completed run directory can be copied to a new location and resumed or replayed with correct dispositions (reused where valid) using only run-relative provenance.
- Resume/replay validation (existence, SHA-256, model, schema version, inputs) continues to hold after relocation and still regenerates on tampered or stale artifacts.
- The run remains deterministic and bounded; reuse the existing orchestration with no duplicated stage logic and no new analysis behavior.
- No existing artifact schema is broken; if the run-manifest schema changes, its version is bumped and readers/tests are updated.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not duplicate or reimplement any stage; reuse the existing services and orchestration.
- Do not add new waveform, dependency, or semantic analysis, causal claims, or root-cause conclusions.
- Do not add automatic migration of unsupported manifest schemas, distributed execution, remote caching, model providers, databases, CI, or UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
