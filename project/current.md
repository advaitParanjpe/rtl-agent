# Prohibited-Shortcut Review Finding Example Check

## Objective

Add a compact, deterministic local example check that exercises the review service's `det-prohibited-shortcut-N` deterministic finding, which currently has neither a dedicated unit test nor example coverage even though `src/rtl_agent/review/service.py` (`_diff_findings`, `_prohibited_token`) implements it.

## Scope

- Add a small provider-plan fixture (or reuse an existing one if it already produces a matching diff) under `examples/provider-plans/` whose applied `replace_text` edit textually conflicts with an existing task-contract prohibited shortcut (for example, the `reset-behavior.md` issue's "Do not remove the example testbench to make discovery pass." invariant, which tokenizes to `"remove the example testbench"`).
- Add `scripts/prohibited_shortcut_example_check.py` that copies checked-in examples into a temporary workspace, drives `inspect-repo`, `parse-issue`, `implement-task`, and `review-task`, and asserts the `det-prohibited-shortcut-1` finding is present with the expected evidence.
- Reuse the shared `scripts/_example_check.py` helper for repository root, interpreter selection, and `run_cli`.
- Register the new check in `scripts/check.py` and mention it in the README's example-check summary paragraph, matching the existing four checks' documentation pattern.
- Keep generated outputs in temporary or ignored artifact directories.

## Acceptance Criteria

- The new example check is local, deterministic, compact, and independently runnable.
- It reuses the shared helper without adding new dependencies or a framework.
- It asserts on stable schema versions, statuses, finding IDs, and artifact existence rather than volatile timestamps, UUIDs, durations, hashes, or absolute paths.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, verification-strength, benchmark, evidence-bundle, schema-example, CLI-doc, packaging-smoke, e2e-example, failure-example, tool-failure-example, no-change-example, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not change generated artifact schemas, CLI behavior, provider behavior, or product workflow features (the finding logic itself already exists; this milestone only adds coverage).
- Do not add broad orchestration features, publishing automation, semantic waveform analysis, mutation execution, or large generated artifacts under tracked paths.

## Completion State

Active.
