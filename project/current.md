# Compact End-to-End Example Check

## Objective

Add a local scripted example check that exercises the deterministic rtl-agent workflow across compact checked-in fixtures and verifies expected artifacts.

## Scope

- Add a bounded script that runs a compact local workflow using existing CLI/services and ignored artifact directories.
- Cover repository inspection, issue parsing, bounded implementation with stub provider, validation, review or verification-strength where practical, benchmark or evidence export where practical.
- Assert expected output artifact paths and key statuses without depending on timestamps, UUIDs, absolute paths, durations, or hashes.
- Include the check in the canonical validation workflow only if it remains fast and deterministic.
- Update README usage if a new script is added.

## Acceptance Criteria

- The example check is local, deterministic, compact, and does not require external tools, providers, network access, CI, containers, dashboards, or UI.
- It verifies expected artifacts and statuses from a realistic mini workflow.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, verification-strength, benchmark, evidence-bundle, schema-example, CLI-doc, packaging-smoke, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add real model-provider integration, semantic waveform analysis, mutation execution, CI automation, remote publishing, containers, dashboards, databases, queues, or a web UI.
- Do not add external RTL repositories, large logs, waveforms, or generated artifacts under tracked paths.

## Completion State

Active.
