# Independent Reviewer

## Objective

Add an independent deterministic review pass over a proposed implementation report, diff artifact, task contract, repository map, and validation evidence to produce a structured review finding set covering acceptance criteria, risks, evidence gaps, and required follow-up.

## Scope

- Add typed review request/response models and a versioned review-report JSON artifact.
- Consume existing task-contract, repository-map, implementation-report, diff, and validation artifacts.
- Check that validation passed before marking work acceptable.
- Detect missing evidence, failed validation, out-of-scope file edits, prohibited-shortcut conflicts, and acceptance-criteria gaps using deterministic rules.
- Add a CLI command for review.
- Persist review artifacts under the existing run-artifact structure where applicable.
- Add focused tests using compact fixtures and existing stub-provider flows.
- Update README usage for the review pass.

## Acceptance Criteria

- Review reports are stable JSON for the same inputs.
- Failed validation or missing validation evidence prevents an acceptable review outcome.
- Out-of-scope edits and prohibited-shortcut conflicts are reported as findings.
- The review command returns non-zero for malformed inputs or unacceptable results when requested by CLI options.
- Existing discovery, issue parsing, implementation-agent, verification iteration, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add a second implementation agent.
- Do not add pull-request automation.
- Do not add waveform analysis, mutation testing, CI bots, databases, queues, dashboards, or a web UI.
- Do not require external model credentials for tests.

## Completion State

Active.
