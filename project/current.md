# Schema Examples and Compatibility Fixtures

## Objective

Add compact checked-in example artifacts and compatibility tests for the public JSON schemas emitted by the deterministic rtl-agent workflow.

## Scope

- Add small example JSON fixtures for representative repository-map, task-contract, implementation-report, review-report, triage-report, verification-strength-report, benchmark-report, and evidence-bundle-report artifacts.
- Add tests that load each fixture through the current typed models.
- Add README guidance for fixture purpose and compatibility expectations.
- Keep fixtures compact and free of logs, waveforms, secrets, generated run directories, and external repository content.

## Acceptance Criteria

- Every checked-in schema example validates through its corresponding typed model.
- Fixtures are deterministic, compact, and safe to commit.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, verification-strength, benchmark, evidence-bundle, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add large logs, waveforms, external repository snapshots, cloud storage, signing infrastructure, CI automation, dashboards, databases, queues, or a web UI.
- Do not add real model-provider integration, semantic waveform analysis, or mutation execution.

## Completion State

Active.
