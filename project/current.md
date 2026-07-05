# Counterexample Stimulus Minimization Foundation

## Objective

Introduce a generic, deterministic reduction harness that can test whether a candidate reduced stimulus still reproduces the same observed failure family, without yet implementing broad automatic search across every testbench format. Reuse the existing failure-fingerprint family digest as the equivalence oracle and the existing command-runner / Git worktree / triage / failure-intelligence machinery. Read-only with respect to source repositories; no new analysis behavior and no causal claims.

## Scope

- Add a `reduction` service and a CLI command (for example `check-reduction`) that, given a baseline failure-intelligence run (or its fingerprint) and one explicit candidate reduced stimulus supplied by the user, evaluates whether the candidate still reproduces the same observed failure family.
- Reproduce-and-compare mechanics: apply the candidate stimulus in an isolated Git worktree (never modifying the baseline repository, never committing/pushing), run a named configured command with an explicit timeout, capture logs and the generated waveform, run the existing failure-intelligence pipeline, fingerprint the result, and compare its `family_digest` (and exact/related classification) to the baseline fingerprint. Reuse the existing command-runner, worktree, triage, waveform, failure-intelligence, fingerprint, and inspection services — no parallel analysis path.
- The candidate stimulus is one explicit, user-supplied input (for example a replacement stimulus file applied via the existing bounded edit / patch mechanism, restricted to explicitly allowed files). No automatic search, no enumeration over reductions, and no broad testbench-format parsing in this milestone.
- Emit a typed, versioned reduction-check report: baseline reference and family digest, candidate description and artifact, worktree/execution provenance, resulting fingerprint, and a deterministic verdict — `reproduces_same_family`, `reproduces_exact`, `related_but_different_family`, `different_failure`, `failure_not_reproduced`, or `insufficient_evidence` — with an explicit statement that it records observed reproduction, not proven minimality or causality. Also emit concise Markdown.
- Add a gated Icarus-backed pilot (skipped when the simulator is absent) plus deterministic hermetic tests covering: same-family reproduction, exact reproduction, failure removed/not reproduced, a different failure family, insufficient evidence, patch/edit application failure, invalid baseline, worktree isolation and cleanup, and stable report serialization.

## Acceptance Criteria

- The harness deterministically decides whether one user-supplied candidate stimulus reproduces the baseline's observed failure family, using the existing fingerprint family digest as the oracle and reusing existing services with no new analysis or parallel path.
- It is read-only with respect to the baseline repository (isolated worktree, no commits/pushes) and fails honestly on unclean apply, invalid baseline, or infrastructure failure.
- The report is typed, versioned, deterministic, and makes no minimality or causal claim.
- The Icarus pilot passes when the simulator is present and skips cleanly otherwise; canonical validation stays hermetic.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No automatic search/enumeration over reductions, delta-debugging, or optimization; exactly one user-supplied candidate per invocation.
- No broad testbench-format parsing, waveform generation from RTL semantics, model providers, databases, remote execution, CI, or UI.
- No new analysis behavior, causal/root-cause claims, or minimality proofs.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
