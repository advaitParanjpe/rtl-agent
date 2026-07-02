# Evidence Bundle Export

## Objective

Create a deterministic local export command that gathers existing rtl-agent run artifacts into a compact machine-readable handoff bundle for review and archival.

## Scope

- Add typed evidence-bundle manifest/result models.
- Add a CLI command that reads existing run artifacts and writes a compact export index under a caller-specified output directory.
- Include references to available run metadata, command results, benchmark reports, implementation reports, review reports, triage reports, and verification-strength reports without re-running workflow steps.
- Record missing optional artifacts as warnings and missing required run metadata as an honest failure.
- Add focused tests for stable export JSON, missing-artifact warnings, failed export reporting, and CLI behavior.
- Update README usage.

## Acceptance Criteria

- Export artifacts are stable JSON for the same inputs.
- The exporter never executes commands, calls model providers, mutates source files, downloads repositories, or requires CI.
- Missing optional artifacts produce warnings; missing required run metadata produces a failed export result.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, verification-strength, benchmark, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add CI automation, dashboards, databases, queues, or a web UI.
- Do not add external artifact upload, remote storage, or pull-request automation.
- Do not add real model-provider integration, semantic waveform analysis, or mutation execution.

## Completion State

Active.
