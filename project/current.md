# Waveform Evidence Bundle Integration

## Objective

Extend the existing deterministic evidence-bundle exporter so waveform-slice and assertion-to-waveform linkage artifacts produced under a run directory are recognized, classified, hashed, and recorded with their schema versions and provenance, exactly like the other typed reports. Do not redesign export or change any existing artifact schema.

## Scope

- Add evidence artifact kinds for the waveform-slice report and the assertion-waveform linkage report to `src/rtl_agent/evidence_bundle_models.py` (`EvidenceArtifactKind`).
- Teach `src/rtl_agent/evidence_bundle.py` to classify these artifacts by their `schema_version` and stable file locations, reusing the existing hashing, schema-version detection, and omitted-content handling rather than adding a parallel path.
- Preserve deterministic ordering, run-relative provenance references, and existing warning/failure semantics.
- Add compact tests covering classification of a waveform-slice artifact and an assertion-link artifact within a run directory, plus deterministic bundle output.
- Update the README evidence-bundle section with one concise mention of the new recognized artifact kinds.

## Acceptance Criteria

- Waveform-slice and assertion-link artifacts under a run directory are indexed with correct kinds, SHA-256 hashes, sizes, and schema versions.
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
- Do not add semantic waveform interpretation, signal-dependency tracing, model-based analysis, source localization, stimulus minimization, or patch generation.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
