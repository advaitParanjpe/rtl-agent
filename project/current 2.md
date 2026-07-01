# Bootstrap: Deterministic Orchestration Foundation

## Objective

Create a clean, tested Python project with a minimal deterministic CLI, typed configuration, durable run artifacts, named-command execution, Git worktree foundation, and milestone-driven project workflow.

## Scope

- Initialize the repository and project-control files.
- Implement an installable `rtl-agent` CLI.
- Define minimal typed YAML configuration.
- Implement durable run storage.
- Implement named deterministic command execution.
- Implement narrow Git worktree helpers.
- Add tests and canonical validation script.
- Document product vision, current state, exclusions, and quick start.

## Deliverables

- `AGENTS.md`, `README.md`, `LICENSE`, `pyproject.toml`, `.gitignore`
- `project/current.md`, `project/roadmap.md`, `project/history.md`
- `src/rtl_agent/` package with CLI, config, models, artifacts, execution, and git modules
- `examples/rtl-agent.yaml`
- `scripts/check.py`
- Unit tests for CLI, config, command runner, run store, and worktree helpers

## Acceptance Criteria

- CLI supports help, initialization, config inspection, and named command execution.
- Command execution uses configured named commands, no shell invocation, timeout handling, typed results, and artifact-backed stdout/stderr logs.
- Run artifacts are stable JSON/JSONL files under the configured run directory.
- Git worktree code validates source repositories, chooses safe paths under run storage, constructs commands, and refuses dangerous paths.
- README states that no AI coding agent exists yet.
- Project-control files describe the durable milestone workflow.

## Required Validation Commands

- `python3 scripts/check.py`
- `python3 -m rtl_agent --help`
- `python3 -m rtl_agent inspect-config --config examples/rtl-agent.yaml`
- `python3 -m rtl_agent run-command --config examples/rtl-agent.yaml --command smoke`
- `git diff --check`
- `git status --short`

## Exclusions

- No autonomous implementation agent.
- No model-provider API.
- No EDA tool integration beyond deterministic configured commands.
- No branch management, commits, pushes, pull requests, remotes, database, web UI, queues, or containers.

## Completion State

Active.
