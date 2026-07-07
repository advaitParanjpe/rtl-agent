# Hypothesis-Driven Intervention Templates

## Objective

Introduce a small deterministic library of safe, bounded intervention templates derived from existing driver and divergence evidence, and generate candidate experiments as explicit, reviewable intervention manifests. The library proposes reviewable artifacts; it must not execute unrestricted autonomous patching. All generated interventions must be expressible in the existing manual-intervention representation (patch or structured `replace_text` edit) so they can be fed unchanged into the experiment matrix.

## Scope

- Add an `intervention-templates` service and CLI command that, given a validated failure-intelligence run (its driver trace and divergence/fingerprint evidence) and the target repository + config, emit a bounded, deterministic set of candidate interventions as an explicit intervention manifest (the same schema consumed by `run-experiment-matrix`).
- Implement a small fixed library of safe, evidence-anchored templates, each deriving its target site strictly from existing evidence (driver trace, earliest-divergence signals, mapped source locations). Start with a minimal set such as: suppress one assignment to a divergent signal, hold a register value across a bounded window, and override one condition for a bounded window. Each template must produce a structured bounded edit restricted to explicitly allowed files, a stable intervention id, a human description citing the evidence it was derived from, and tags/metadata; templates must never mutate more than their declared site.
- Each generated candidate must be a reviewable artifact only: the service writes the manifest and a typed template report but does not apply or run anything. Applying candidates remains the job of `run-experiment-matrix`.
- Deterministic and bounded: a fixed maximum number of candidates, deterministic ordering independent of filesystem enumeration, a semantic digest per candidate, and no randomness. Reuse the existing driver-trace, divergence/fingerprint, signal-source-map, and manual-intervention representations; do not add a new edit engine.
- Emit a typed, versioned template report (JSON + Markdown) recording, per candidate: template id/kind, derived target site with cited evidence (signal, source location, driver reference), the generated bounded edit, allowed files, a reviewability note, and an explicit disclaimer that a template is an evidence-anchored hypothesis, not a proven fix or a causal claim. Include a summary of templates considered, candidates emitted, and evidence sites skipped (with reasons).
- Add a gated Icarus-backed pilot (skipped when the simulator is absent) that derives candidate interventions from the counterexample fixture's baseline evidence, writes a manifest, and confirms the manifest is valid input to `run-experiment-matrix` (optionally running it to show at least one generated candidate removes or changes the observed failure) — without ever applying edits outside isolated worktrees. Plus deterministic hermetic tests covering: template derivation from evidence, bounded/allowed-file safety, deterministic ordering and candidate count, per-candidate digest stability, skipping sites with insufficient evidence, malformed/insufficient input handling, manifest schema compatibility with the experiment matrix, no source mutation, and stable serialization.

## Acceptance Criteria

- Candidate interventions are derived deterministically from existing evidence and emitted as explicit, reviewable manifests compatible with `run-experiment-matrix`, with no automatic application and no source-repository mutation.
- The template library is small, fixed, bounded, and evidence-anchored; each candidate cites the evidence it came from and stays within its declared edit site and allowed files.
- No LLM-generated patches, no intervention search/optimization, no ranking by suspected root cause, and no causal claims.
- The Icarus pilot passes when the simulator is present and skips cleanly otherwise; canonical validation stays hermetic.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No automatic application of generated interventions (generation only), no LLM-generated patches, no search/optimization over templates, no ranking by suspected cause, and no causal/root-cause claims.
- No new analysis behavior, model providers, databases, remote execution, CI, or UI.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
