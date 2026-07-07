# MVP Demonstration CLI and Documentation Surface

## Objective

Expose the evidence-guided counterfactual demonstration workflow as a first-class `rtl-agent` command over the existing `run_mvp_demo` service, with a concise terminal summary, README usage documentation, and packaging-smoke coverage. This is a thin interface layer only: it reuses the existing service unchanged and adds no new analysis behavior, no automatic patching, and no causal claims.

## Scope

- Add a CLI command (for example `mvp-demo` / `demo-workflow`) that wraps `rtl_agent.mvp_demo.run_mvp_demo`, accepting the failure run, target repo, config, named command, failing stimulus, allowed files (repeatable), output directory, and the max-candidates / max-experiments / timeout / baseline-commit options, and printing a concise terminal summary (stage statuses, minimized item counts, candidate counts by confidence, experiment outcome counts, and the observed effects) plus the output paths.
- Reuse the existing `run_mvp_demo` service and its typed summary verbatim; do not change the service, its models, or any upstream service. The command only parses options, calls the service, and renders a summary.
- Add a README section documenting the command and how its generated summary ties the stages together, consistent with the existing per-command documentation and the CLI-doc test that cross-checks documented commands against registered commands.
- Ensure the new command appears in the packaging smoke check (its `--help` is exercised) and in the CLI command inventory test.

## Acceptance Criteria

- One `rtl-agent` command runs the full evidence-guided demonstration by delegating to the existing service, printing a concise, evidence-qualified terminal summary and the output artifact paths, with no new analysis behavior and no causal claims.
- The command is documented in the README, listed in the CLI-doc/inventory test, and exercised by the packaging smoke check.
- The source repository is never modified by the command; canonical validation stays hermetic and all existing tests, example checks, packaging smoke, and validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No changes to the `run_mvp_demo` service or any upstream service, no new analysis behavior, no automatic application of interventions, no LLM-generated hypotheses, no search/optimization, no ranking by suspected root cause, and no causal/root-cause claims.
- No new model providers, databases, remote execution, CI, or UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
