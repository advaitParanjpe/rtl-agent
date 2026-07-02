# Verification Strength and Mutation Assessment

## Objective

Estimate whether configured validation evidence is strong enough for a task contract and identify weak validation signals using deterministic, bounded analysis of task contracts, repository maps, implementation reports, review reports, and triage artifacts.

## Scope

- Add typed verification-strength models and a versioned JSON artifact.
- Score validation evidence using deterministic signals such as passed command coverage, acceptance-criteria references, changed-file relevance, failure/retry history, and review findings.
- Detect weak validation patterns such as no validation, only smoke commands, missing acceptance coverage, failed review, missing triage for simulator failures, or validation unrelated to changed files.
- Add a CLI command for strength assessment.
- Persist assessment artifacts under existing run-artifact paths where practical.
- Add focused tests using compact synthetic artifacts.
- Update README usage.

## Acceptance Criteria

- Assessment artifacts are stable JSON for the same inputs.
- Failed validation or unacceptable review produces weak/insufficient strength.
- Passing validation with relevant evidence produces stronger assessment than smoke-only validation.
- The system never mutates source files or executes arbitrary commands during assessment.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add mutation testing execution in this milestone.
- Do not execute EDA tools beyond existing configured command infrastructure.
- Do not add model-based assessment, pull-request automation, CI bots, databases, queues, dashboards, or a web UI.

## Completion State

Active.
