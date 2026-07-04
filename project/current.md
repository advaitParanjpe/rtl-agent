# Failure Intelligence Run Inspection and Validation

## Objective

Add a read-only command that inspects an existing failure-intelligence run directory and validates it against its run manifest without re-running any stage. Reuse the existing manifest and validation helpers; add no new analysis behavior.

## Scope

- Add a deterministic, read-only inspection service and a CLI command (such as `inspect-run`) that reads a run directory's `run-manifest.json` and validates the run against it.
- Resolve run-relative artifact references against the actual run directory (using the existing safe run-relative resolution that rejects traversal/escaping paths), independent of the manifest's recorded absolute `run_dir`.
- For each recorded artifact, validate: existence, recorded SHA-256 (recompute and compare), typed-model validation for known kinds, and supported schema version. Report per-artifact validity with a clear reason on failure.
- Report per-stage validity derived from its outputs, the overall run status from the manifest, and findings for missing artifacts, unsafe recorded paths, and missing or non-existent external inputs.
- Emit a typed, versioned inspection report (or reuse existing typed structures where practical) summarizing valid / invalid / missing artifacts and stages, and exit non-zero when the run is invalid.
- Reuse the existing run-manifest models, the safe-path resolver, and the artifact typed models; do not re-run stages, re-parse VCD, or recompute any stage output.
- Fail or warn honestly: an unreadable or unsupported-version manifest, missing artifacts, hash mismatches, unsafe paths, and missing external inputs are all reported explicitly.
- Add compact tests covering a valid run, a run with a tampered/corrupted artifact, a moved run directory, an unsafe recorded path, a missing external input, and an unsupported manifest version.
- Add one concise runnable README example.

## Acceptance Criteria

- Inspection is read-only and deterministic: it never re-runs a stage, re-parses VCD, or mutates the run directory.
- Every recorded artifact is validated (existence, SHA-256, typed model, schema version) and reported with a clear per-artifact result.
- Run-relative references resolve against the actual run directory, so a moved/copied run inspects correctly; unsafe recorded paths and missing external inputs are reported, not silently resolved.
- The command exits non-zero when the run is invalid.
- No existing artifact schema, provider behavior, or product workflow changes beyond adding the inspection command; if a new report schema is added it is typed and versioned.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not re-run, re-parse, recompute, or mutate any stage or artifact; inspection is read-only.
- Do not add new waveform, dependency, or semantic analysis, causal claims, or root-cause conclusions.
- Do not add automatic migration of unsupported manifest schemas, remote artifact storage, cloud synchronization, databases, distributed execution, model providers, CI, or UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
