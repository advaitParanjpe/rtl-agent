# Benchmark Suite Manifest and Local Runner

## Objective

Create a deterministic benchmark-suite foundation that can run existing rtl-agent workflow commands against compact, repository-local fixtures and persist machine-readable benchmark results.

## Scope

- Add typed benchmark manifest and result models.
- Add a small checked-in manifest for existing compact fixtures only.
- Add a CLI command that runs configured benchmark steps by invoking existing rtl-agent services or configured named commands with bounded inputs.
- Persist benchmark result artifacts under existing run-artifact paths where practical.
- Record pass/fail status, artifact paths, durations, and concise failure summaries.
- Add focused tests for manifest parsing, result stability, failed-step reporting, and CLI behavior.
- Update README usage.

## Acceptance Criteria

- Benchmark result artifacts are stable JSON for the same deterministic inputs.
- A failing benchmark step produces a failed benchmark result without hiding earlier artifacts.
- The runner does not fetch external repositories, call model providers, create pull requests, or require CI.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, verification-strength, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add external benchmark downloads.
- Do not add a real model provider.
- Do not add CI automation, dashboards, databases, queues, or a web UI.
- Do not add a broad mutation framework or semantic waveform analysis.

## Completion State

Active.
