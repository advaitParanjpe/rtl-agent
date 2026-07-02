# Packaging Smoke Verification

## Objective

Add a bounded local packaging smoke check that verifies the installed `rtl-agent` console script and `python -m rtl_agent` module invocation expose the documented CLI surface.

## Scope

- Add a small script or test helper that builds/installs the local package into a temporary environment or otherwise verifies installed console-script behavior without network access when dependencies are already available.
- Check `rtl-agent --help`, `python -m rtl_agent --help`, and documented command help availability.
- Keep the check optional or bounded enough for local validation without introducing CI automation.
- Update README only if needed to describe the packaging smoke command.

## Acceptance Criteria

- Installed console-script and module invocation help checks pass in a local environment.
- The check remains deterministic, local, and does not require remote services, providers, CI, dashboards, or UI.
- Existing discovery, issue parsing, implementation-agent, verification iteration, review, triage, verification-strength, benchmark, evidence-bundle, schema-example, CLI-doc, command-runner, config, run-store, and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add CI automation, remote package publishing, dashboards, databases, queues, a web UI, migration infrastructure, remote schema registries, or code generation.
- Do not add real model-provider integration, semantic waveform analysis, mutation execution, or unrelated workflow features.

## Completion State

Active.
