# Failure Intelligence Run Resume and Replay

## Objective

Extend the failure-intelligence run orchestration so a previously-started run directory can be resumed (skipping stages whose valid artifacts already exist) or replayed from a chosen stage, reusing the existing stage services and run manifest. The behavior is deterministic and bounded and honestly reports which stages were skipped, reused, or re-run; it adds no new analysis behavior.

## Scope

- Extend the existing orchestration service (do not fork it) to support:
  - resume: given an existing run directory, skip each stage whose expected output artifact already exists and validates through its typed model, and run only the remaining stages in the fixed sequence;
  - replay-from: re-run the sequence starting at an explicitly named stage, discarding and regenerating that stage and every stage after it while reusing earlier valid artifacts.
- Reuse the existing stage services, run manifest schema, and artifact layout; do not duplicate any stage or introduce a second run format. Extend the run manifest only as needed to record per-stage disposition (executed / reused / skipped / regenerated) without breaking the existing schema version contract (bump the schema version if fields change).
- Add CLI options to the existing `run-failure-intelligence` command (such as `--resume` and `--replay-from <stage>`) rather than adding a parallel command, unless a separate thin command reads more clearly; either way, reuse the orchestration service.
- Validate reused artifacts before trusting them; if a reused artifact is missing or invalid, honestly fall back to re-running that stage and record why.
- Preserve honest failure handling: a terminal error still stops the run, preserves completed artifacts, and writes the manifest.
- Add compact fixtures and tests covering a clean resume (all reused), a partial resume (some stages re-run), replay-from a chosen stage, invalid-artifact fallback, and deterministic stage artifacts.
- Add one concise runnable README example.

## Acceptance Criteria

- Resume and replay reuse the existing stage services with no duplicated stage logic and no new analysis behavior.
- Reused stages are validated before being trusted; skipped/reused/regenerated dispositions are recorded in the run manifest.
- Stage artifact contents remain deterministic for identical inputs (excluding volatile run metadata).
- No existing artifact schema is broken; if the run-manifest schema changes, its schema version is bumped and existing readers/tests are updated.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not duplicate or reimplement any stage; reuse the existing services and orchestration.
- Do not add new waveform, dependency, or semantic analysis, causal claims, or root-cause conclusions.
- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
