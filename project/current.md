# Model Provider Abstraction and One Bounded Implementation Agent

## Objective

Add interchangeable model-provider adapters and one tightly constrained implementation loop that can propose edits for a typed task contract while preserving deterministic tool boundaries, validation evidence, and honest failure reporting.

## Scope

- Add typed model-provider interfaces and request/response models.
- Support at least one local or stub provider suitable for deterministic tests.
- Add one bounded implementation-agent loop that consumes a task-contract JSON and repository-map JSON.
- Require explicit working-path validation before edits.
- Persist prompts, model responses, decisions, and outcomes as run artifacts.
- Keep command execution limited to configured named commands.
- Add focused tests with stubbed model responses.
- Update README usage for the bounded implementation flow.

## Acceptance Criteria

- Provider interfaces are interchangeable and fully typed.
- Tests run without network access or real model credentials.
- The implementation loop respects task-contract prohibited shortcuts and scoped repository context.
- The loop can produce either a bounded proposed diff or a structured failure report.
- Validation commands are executed only through existing configured named-command infrastructure.
- Run artifacts contain enough evidence to audit prompts, responses, edits, and validation outcomes.
- Existing discovery, issue parsing, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add multiple autonomous agents.
- Do not add reviewer agents, waveform analysis, mutation testing, CI bots, databases, queues, dashboards, or a web UI.
- Do not execute arbitrary shell commands supplied by model output.
- Do not require external model credentials for tests.

## Completion State

Active.
