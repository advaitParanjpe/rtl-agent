# Issue Parsing and Explicit Task Contracts

## Objective

Transform a user-supplied issue in Markdown or plain text into a typed task contract containing the requested behavior, scoped repository context, invariants, acceptance criteria, required validation commands, prohibited shortcuts, and evidence requirements.

## Scope

- Add deterministic issue parsing invoked from the CLI.
- Accept a Markdown or plain-text issue file and optional repository-map JSON.
- Produce a versioned task-contract JSON artifact using typed Pydantic models.
- Extract explicit sections, checklists, code/path references, validation commands, constraints, and acceptance criteria with deterministic parsing heuristics.
- Preserve uncertainty as warnings or missing fields rather than inventing requirements.
- Add focused tests using compact issue fixtures.
- Update README usage for issue parsing.

## Acceptance Criteria

- Task contracts are stable JSON for the same issue text and inputs.
- Parser handles common Markdown headings, bullet lists, checkboxes, fenced commands, and path/code references.
- Contract records requested behavior, scoped context, invariants, acceptance criteria, validation commands, prohibited shortcuts, and evidence requirements when present.
- Missing or ambiguous sections are reported as warnings.
- CLI returns non-zero for invalid issue paths or malformed repository-map inputs.
- Existing discovery, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add model-provider integration.
- Do not add autonomous implementation-agent behavior.
- Do not execute validation commands from parsed issues.
- Do not implement planning, review agents, waveform analysis, mutation testing, CI bots, databases, queues, dashboards, or a web UI.

## Completion State

Active.
