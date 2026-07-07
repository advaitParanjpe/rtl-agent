# Evidence-Guided Counterfactual MVP Demonstration

## Objective

Compose one complete, public-facing workflow that runs end to end on a realistic multi-module RTL example: from a failing regression, through failure-intelligence + fingerprinting, counterexample minimization, generated reviewable intervention candidates, experiment-matrix execution, and a final evidence-qualified summary. This milestone is a demonstration and integration layer that composes the already-built services into one coherent, reproducible story; it must not add new analysis behavior, automatic patching, or causal claims.

## Scope

- Add an `mvp-demo` (or similarly named) orchestration that runs the existing services in sequence on one realistic multi-module RTL fixture: (1) run the configured failing command and build a failure-intelligence run; (2) fingerprint it; (3) minimize the failing structured stimulus to a counterexample; (4) generate reviewable intervention candidates from the evidence; (5) run the experiment matrix against the generated manifest and the minimized counterexample; (6) emit a single evidence-qualified summary tying the stages together.
- Reuse the existing `run-failure-intelligence`/failure-report, `fingerprint-run`, `minimize-stimulus`, `generate-interventions`, and `run-experiment-matrix` services and their typed reports. Do not re-implement any stage; the orchestration only sequences them, passes artifacts between them, and reads their outputs.
- Extend or add a compact but realistic multi-module RTL example (building on the existing AXI-style fixtures) with a seeded failure that exercises more than one module, so the demonstration is not trivially single-signal. Keep it Icarus-backed and gate cleanly when the simulator is unavailable.
- Emit a typed, versioned MVP summary report (JSON + Markdown) that references each stage's run/report by path and digest and states, in evidence-qualified language: the observed failure family, the minimized counterexample size reduction, the generated candidate count by confidence, and the experiment-matrix outcomes (which candidates removed / changed / had no observed effect on the failure). The summary must carry an explicit disclaimer that it reports observed experimental results, not proven causality or a fix.
- Keep the whole demonstration read-only with respect to the source repository: every simulation runs in isolated worktrees via the existing services, and nothing is committed, pushed, or applied to the target repo.

## Acceptance Criteria

- One command (or one pilot script) runs the full failing-regression-to-summary workflow on the realistic fixture, reusing the existing services with no new analysis behavior and no parallel path.
- The final summary is typed, versioned, evidence-qualified, references every upstream stage by path/digest, and makes no causal or root-cause claim.
- The source repository is never modified; the demonstration gates cleanly when Icarus is unavailable and canonical validation stays hermetic.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No new analysis behavior, no automatic application of interventions, no LLM-generated hypotheses, no search/optimization, no ranking by suspected root cause, and no causal/root-cause claims.
- No new model providers, databases, remote execution, CI, or UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
