# Waveform and Assertion Triage

## Objective

Capture and summarize simulator outputs, assertion failures, waveform artifact references, and failure context from configured verification command artifacts so later stages can reason about RTL failures without ingesting unrestricted logs.

## Scope

- Extend verification evidence extraction for common simulator and assertion failure patterns.
- Record bounded stdout/stderr excerpts and artifact paths for waveform, VCD/FST/FSDB, assertion, and simulation-output files when referenced by command artifacts.
- Add typed triage models and versioned JSON artifacts.
- Integrate triage summaries with existing verification classification and review artifacts where practical.
- Keep all command execution restricted to configured named commands.
- Add focused tests using compact synthetic simulator outputs.
- Update README usage for waveform/assertion triage.

## Acceptance Criteria

- Triage artifacts are deterministic and bounded for the same command artifacts.
- Assertion failures and waveform references are extracted from captured command output when explicitly present.
- The system does not ingest unrestricted logs into provider prompts or review findings.
- Missing waveform files are reported as warnings with cited evidence.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add waveform rendering or UI.
- Do not add mutation testing.
- Do not add pull-request automation, CI bots, databases, queues, dashboards, or a web UI.
- Do not require external EDA tools for tests.

## Completion State

Active.
