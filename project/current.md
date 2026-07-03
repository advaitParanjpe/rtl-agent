# Tool Failure Report Example Check

## Objective

Add a compact local example check that exercises deterministic structured-tool failure reporting and verifies the emitted failure artifacts.

## Scope

- Reuse checked-in compact fixtures, existing CLI commands, stub-provider plans, run artifacts, and schemas.
- Exercise a bounded implementation run that ends in an honest failed report because an allowed structured tool call cannot be applied.
- Verify stable failure status, failure reason, tool-result evidence, absence of validation execution when appropriate, review disposition, verification-strength result, and exported evidence artifacts.
- Keep generated outputs in temporary or ignored artifact directories.
- Include the check in canonical validation only if it remains fast, deterministic, and local.
- Update README only if a new user-facing script or command is added.

## Acceptance Criteria

- The tool-failure example is local, deterministic, compact, and does not require external tools, providers, network access, CI, containers, dashboards, or UI.
- It verifies expected failure artifacts and statuses without depending on timestamps, UUIDs, absolute paths, durations, or hashes.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, verification-strength, benchmark, evidence-bundle, schema-example, CLI-doc, packaging-smoke, e2e-example, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not add broad orchestration features, publishing automation, semantic waveform analysis, mutation execution, or large generated artifacts under tracked paths.

## Completion State

Active.
