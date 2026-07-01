# Verification Execution and Failure Iteration

## Objective

Run configured verification commands for a bounded implementation report, classify failures deterministically, and allow limited retry iterations using existing task-contract, repository-map, provider, and implementation-agent artifacts.

## Scope

- Add deterministic verification result classification for configured named commands.
- Classify failures into categories such as timeout, missing executable, command failure, assertion/test failure evidence, lint/syntax evidence, and unknown failure.
- Extend the bounded implementation flow to optionally perform limited retry iterations after failed validation.
- Persist verification attempts, classifications, retry decisions, and final outcomes as run artifacts.
- Keep command execution restricted to configured named commands and explicit permissions.
- Add focused tests using stub provider responses and small temporary repositories.
- Update README usage for verification failure iteration.

## Acceptance Criteria

- Verification classification is deterministic and based only on command metadata and captured stdout/stderr artifacts.
- Retry attempts are bounded by explicit limits.
- The system records why it retried or why it stopped.
- Failed work produces an honest structured failure report with evidence paths.
- Passing work produces a proposed-diff report with validation evidence.
- Existing discovery, issue parsing, implementation-agent, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add reviewer agents, waveform analysis, mutation testing, CI bots, databases, queues, dashboards, or a web UI.
- Do not execute arbitrary shell commands from provider output.
- Do not add pull-request automation.
- Do not broaden model-provider support beyond what is needed for deterministic tests.

## Completion State

Active.
