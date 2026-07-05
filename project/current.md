# Failure Fingerprinting and Experiment Comparison

## Objective

Define a stable, deterministic behavioral fingerprint for a localized failure — derived from the observed failure mechanism, not volatile run metadata — so that repeated seeds, baseline runs, and counterfactual experiments can be grouped and compared by observed failure mechanism. Reuse existing artifacts (failure report, comparison, mapping) and models; add no new analysis behavior and no causal claims.

## Scope

- Add a typed, versioned failure-fingerprint model plus a deterministic service that computes a fingerprint from an existing failure-intelligence run (or its failure report + comparison), using only stable, mechanism-defining evidence: the earliest divergent signal set, the failure timestamp/window shape (relative to the extraction window, not absolute run time), the assertion identity where available, and the mapped candidate source location(s)/module(s) — explicitly excluding volatile fields (run ids, timestamps/dates, durations, absolute paths, hashes, worktree names).
- Emit a stable fingerprint key (a deterministic digest over the canonicalized mechanism fields) plus the human-readable component breakdown, so two runs with the same observed failure mechanism produce the same key and different mechanisms produce different keys.
- Add a CLI command (for example `fingerprint-run`) that reads a run directory (read-only) and writes the typed fingerprint report; keep it inspection-safe and bounded.
- Add an experiment-grouping/comparison affordance: given two or more fingerprints (for example a baseline and a counterfactual intervention run, or repeated seeds), report whether they share a fingerprint key and enumerate the mechanism-field differences deterministically — reusing the counterfactual observable-difference style, without causal claims.
- Reuse the existing failure report, comparison, signal-source mapping, and (where present) triage assertion evidence; do not recompute waveform or driver analysis and do not add a parallel pipeline.
- Add deterministic tests: identical mechanism → identical key; changed earliest signal or timestamp/window shape → different key; volatile-field changes (run id, absolute paths, durations) → unchanged key; stable serialization; and a grouping comparison over baseline vs a counterfactual intervention run.

## Acceptance Criteria

- The fingerprint is deterministic and depends only on mechanism-defining evidence; volatile fields never change the key, and genuine mechanism changes always do.
- Fingerprints can group/compare repeated seeds and counterfactual experiments by observed failure mechanism, with deterministic, evidence-based difference reporting and no causal claims.
- The command is read-only with respect to the run directory and reuses existing artifacts/services; no new analysis algorithm or parallel pipeline is added.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No causal/root-cause claims, semantic elaboration, new waveform/driver analysis, model providers, remote execution, CI, or UI.
- No fingerprint that depends on volatile run metadata (ids, timestamps, durations, absolute paths, hashes).
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
