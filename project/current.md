# Counterfactual Experiment Matrix

## Objective

Run a bounded set of user-supplied manual interventions against one minimized counterexample, reuse cached baseline and stimulus artifacts, compare the resulting fingerprints, and emit a compact typed intervention-outcome matrix (JSON + Markdown). Deterministic and read-only with respect to source repositories; reuse the existing counterfactual runner, Git worktree isolation, failure-intelligence, and fingerprint services. Interventions are provided explicitly — no automatic generation, no search/optimization, and no causal claims.

## Scope

- Add an `experiment-matrix` service and CLI command that accepts a validated baseline failure-intelligence run (and/or a minimized counterexample stimulus from stage 48), a target repository, config, named command, and a bounded, explicit list of manual interventions (each a unified diff or structured `replace_text` edit restricted to allowed files, as in the counterfactual runner).
- For each intervention, run one counterfactual experiment reusing the existing counterfactual runner (isolated worktree, named command, timeout; the baseline repository is never modified and nothing is committed/pushed), fingerprint the intervention-run result, and compare it to the baseline fingerprint (exact / same-family / related / different) reusing the existing fingerprint comparison semantics.
- Reuse cached baseline and stimulus artifacts where practical (do not re-run the baseline or re-derive its fingerprint per intervention); deduplicate identical interventions by a semantic digest so identical interventions are not re-simulated.
- Emit a typed, versioned experiment-matrix report: baseline reference and digests, target repo/commit, the ordered list of interventions with their artifacts and per-intervention outcome classification and resulting fingerprint digests, an at-a-glance matrix (intervention × outcome/family), evaluation/cache counts, warnings and insufficient-evidence reasons, and an explicit disclaimer that outcomes are observed intervention results, not proven causality. Also emit a concise Markdown matrix.
- Add a gated Icarus-backed pilot (skipped when the simulator is absent) plus deterministic hermetic tests covering: multiple interventions producing distinct outcomes (failure removed / same family / different family), duplicate-intervention caching, an invalid/failing intervention, an invalid baseline, bounded evaluation, repository-unchanged safety, input-order-independent matrix identity where appropriate, and stable report serialization excluding documented volatile fields.

## Acceptance Criteria

- A bounded set of explicit manual interventions runs deterministically against one baseline/minimized counterexample, reusing existing services with no parallel analysis path and no new analysis behavior.
- Each intervention's outcome is classified from fingerprint evidence and assembled into a typed matrix with no causal/root-cause claims; identical interventions are cached (not re-simulated); the source repository is never modified.
- The Icarus pilot passes when the simulator is present and skips cleanly otherwise; canonical validation stays hermetic.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No automatic/LLM intervention generation, no search/optimization over interventions, no stimulus minimization changes, and no causal/root-cause claims.
- No new analysis behavior, model providers, databases, remote execution, CI, or UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
