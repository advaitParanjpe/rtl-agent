# CLI Documentation Consistency Pass

## Objective

Reconcile README command examples with the current CLI surface and compact local examples so users can follow the deterministic workflow without stale commands.

## Scope

- Compare README command snippets against current Typer CLI commands and options.
- Update README examples only where they are stale, incomplete, or inconsistent with compact checked-in examples.
- Add focused tests for CLI help availability for documented commands where practical.
- Keep changes documentation-focused and local.

## Acceptance Criteria

- README documents the current deterministic CLI commands without stale command names or removed options.
- Documented compact local examples remain runnable from the source tree or clearly state the required installation context.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, verification-strength, benchmark, evidence-bundle, schema-example, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add CI automation, dashboards, databases, queues, a web UI, migration infrastructure, remote schema registries, or code generation.
- Do not add real model-provider integration, semantic waveform analysis, mutation execution, or unrelated workflow features.

## Completion State

Active.
