# Failure Intelligence Run Orchestration

## Objective

Add one bounded, deterministic CLI command that invokes the existing failure-intelligence stages in sequence and writes all artifacts under a single run directory, without duplicating any stage's implementation. The command is a thin orchestrator over the existing services; it adds no new analysis behavior.

## Scope

- Add a deterministic orchestration service and a CLI command (such as `run-failure-intelligence`) that runs the existing stages in order, reusing their service functions directly (not by shelling out and not by reimplementing them):
  - waveform extraction of a failing slice and a passing/reference slice;
  - passing/failing comparison;
  - repository discovery;
  - signal-source mapping of the compared signals;
  - static driver tracing;
  - failure-divergence graph composition;
  - relevant-signal reduction;
  - failure-report synthesis (JSON + Markdown).
- Create a run directory (via the existing `RunStore`) and write every stage artifact under it with stable, documented relative paths; append run events where the existing run-artifact conventions apply.
- Accept the failing and passing VCD inputs, the repository and config, and the failure window parameters; expose only bounded, existing options (no new analysis knobs).
- Emit a small orchestration summary (the run directory, the produced artifact paths, and per-stage status) plus the existing per-stage artifacts.
- Reuse the existing typed models and services; do not re-parse VCD, re-scan RTL, or recompute any stage.
- Fail or warn honestly: a stage error is surfaced with its originating stage; partial runs record what completed.
- Add compact fixtures and tests (reusing the checked-in waveform and RTL fixtures) covering a successful end-to-end run, artifact placement under the run directory, and deterministic artifact contents.
- Add one concise runnable README example, and register any scripted check as appropriate.

## Acceptance Criteria

- The orchestrator reuses the existing stage services with no duplicated stage logic and no new analysis behavior.
- All stage artifacts are written under a single run directory with stable relative paths and validate through the existing schemas.
- The command is deterministic and bounded; repeated runs over identical inputs produce identical stage artifact contents (excluding inherently volatile run metadata).
- No existing artifact schema, provider behavior, or product workflow changes beyond adding the orchestration command.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not duplicate or reimplement any stage; invoke the existing services.
- Do not add new waveform, dependency, or semantic analysis, causal claims, or root-cause conclusions.
- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
