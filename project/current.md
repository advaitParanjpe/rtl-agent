# Failure Intelligence Evidence Bundle Integration

## Objective

Extend the existing deterministic evidence-bundle exporter so the remaining failure-intelligence artifacts produced under a run directory are recognized, classified, hashed, and recorded with their schema versions and provenance, exactly like the other typed reports. Do not redesign export or change any existing artifact schema.

## Scope

- Add evidence artifact kinds for the relevant-signal reduction report, waveform comparison report, signal-source-map report, driver-trace report, and failure-divergence-graph report to `src/rtl_agent/evidence_bundle_models.py` (`EvidenceArtifactKind`).
- Teach `src/rtl_agent/evidence_bundle.py` to classify these artifacts by distinctive top-level JSON keys, reusing the existing hashing, schema-version detection, run-relative provenance, and omitted-content handling rather than adding a parallel path (matching the existing review/triage/verification-strength/waveform-slice/assertion-link detection style).
- Preserve deterministic ordering, run-relative provenance references, and existing warning/failure semantics.
- Add compact tests covering classification of each new artifact within a run directory, plus deterministic bundle output.
- Update the README evidence-bundle section with one concise mention of the newly recognized artifact kinds.

## Acceptance Criteria

- Relevant-signal reduction, waveform comparison, signal-source-map, driver-trace, and failure-divergence-graph artifacts under a run directory are indexed with correct kinds, SHA-256 hashes, sizes, and schema versions.
- Unknown JSON and non-JSON artifacts are still hashed and referenced as before.
- Evidence-bundle output remains deterministic for identical inputs.
- No existing artifact schema, CLI behavior, provider behavior, or product workflow changes.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not redesign the evidence-bundle exporter or its manifest/report schema shape.
- Do not add real model-provider integration, external repositories, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not add semantic waveform interpretation, dependency tracing, model-based analysis, source localization, stimulus minimization, patch generation, or causal claims.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
