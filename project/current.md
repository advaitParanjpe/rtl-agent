# Example Script Helper Consolidation

## Objective

Consolidate duplicated local example-check helper code while preserving existing workflow behavior and validation coverage.

## Scope

- Identify duplicated helper logic across local example-check scripts, especially CLI invocation and Python path setup.
- Extract only a small shared helper if it reduces duplication without obscuring each example's assertions.
- Preserve the existing example scripts as runnable entry points.
- Do not change generated artifact schemas, CLI behavior, provider behavior, or product workflow features.
- Keep generated outputs in temporary or ignored artifact directories.

## Acceptance Criteria

- The example checks remain local, deterministic, compact, and independently runnable.
- Shared helper code does not introduce new dependencies or a framework.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, verification-strength, benchmark, evidence-bundle, schema-example, CLI-doc, packaging-smoke, e2e-example, failure-example, tool-failure-example, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not add broad orchestration features, publishing automation, semantic waveform analysis, mutation execution, product behavior changes, or large generated artifacts under tracked paths.

## Completion State

Active.
