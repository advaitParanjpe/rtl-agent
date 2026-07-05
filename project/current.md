# Manual Counterfactual Intervention Runner

## Objective

Build the first experimental counterfactual-RTL-debugging capability. Given a validated baseline failure-intelligence run and one user-supplied manual intervention, apply the intervention in an isolated Git worktree, rerun a named configured command, analyze the resulting failure evidence with the existing pipeline, compare against the baseline, and emit a typed, versioned counterfactual experiment report. Reuse existing services; add no parallel analysis path and no causal claims.

## Scope

- Add a `run-counterfactual` CLI command and a `counterfactual` service that orchestrates: inspect+validate baseline run → create isolated worktree → apply intervention to allowed files → run named command (timeout) → capture logs/waveform → reuse triage + failure-intelligence → compare vs baseline → classify → write report.
- Support exactly one manual intervention per experiment, either a unified diff `--patch <file>` (applied with `git apply`) or a structured `replace_text` edit (`--replace-file/--replace-old/--replace-new`, reusing the existing bounded-edit exactly-one-match semantics). Preserve the intervention as an experiment artifact; fail honestly if it cannot be applied cleanly.
- Restrict intervention edits to explicitly allowed repository files (`--allowed-file`, repeatable). Apply only inside the worktree; never modify the baseline repository; never commit/push/alter remotes.
- Baseline: accept a failure-intelligence run directory; inspect+validate (refuse invalid); identify baseline failure finding/timestamp/waveform/report; preserve provenance + hashes; never regenerate or alter it.
- Execution: use a named configured command only; enforce an explicit timeout; capture stdout/stderr/exit-code/duration/logs/waveform references via the existing command runner and git worktree support; preserve artifacts on failure.
- Classify the outcome deterministically as one of: `failure_removed`, `failure_delayed`, `failure_advanced`, `failure_changed`, `no_observable_effect`, `new_failure_introduced`, `experiment_failed`, `insufficient_evidence` — based only on explicit evidence (original finding still present, timestamp change, assertion identity, earliest divergence, simulator exit status, new failure evidence, artifact availability/validity). Never claim root cause/causality.
- Emit a typed, versioned experiment report (JSON) with: experiment id; baseline run reference + hashes; target repo + baseline commit; intervention description + artifact; allowed files; worktree provenance; execution command + result; baseline failure identity + time; intervention failure identity + time; outcome classification; observable differences; generated artifact references; warnings/ambiguity/insufficient-evidence reasons; and an explicit statement that it records an intervention outcome, not proven causality. Also emit a concise Markdown report.
- Add one real Icarus-backed pilot (gated, skipped when Icarus absent): seeded backpressure baseline failure; a manual intervention that removes/changes the corrupting assignment; runs in an isolated worktree; the source repo stays byte-for-byte unchanged; the simulator reruns; the original failure is removed/displaced; the report classifies correctly; all intermediate evidence preserved; no unsupported causal claim.
- Add deterministic tests: successful failure removal; no observable effect; changed failure identity; patch application failure; command timeout/infra failure; invalid baseline run; disallowed file modification; dirty/modified target-repo safety; worktree cleanup and preservation policy; stable report serialization excluding documented volatile fields.

## Acceptance Criteria

- One user-supplied manual intervention runs reliably and safely: applied only in an isolated worktree, baseline repo unchanged, no commit/push, honest failure on unclean apply or disallowed file.
- Outcome classification is deterministic and evidence-based across the enumerated cases, with no causal/root-cause claims and an explicit non-causality disclaimer in the report.
- Existing services are reused (command runner, worktree, triage, assertion linking, waveform, comparison, failure-intelligence, inspection, package); no parallel analysis path or new analysis algorithm is added.
- The Icarus pilot passes when the simulator is present and skips cleanly otherwise; canonical validation stays hermetic.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No automatic/LLM intervention generation, multiple interventions per experiment, patch search/optimization, stimulus minimization, semantic elaboration, formal proof, or causal/root-cause claims.
- No FST/FSDB support, remote execution, CI, UI, model providers, or broad third-party dependency management.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
