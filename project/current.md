# Evidence Artifact Provenance Integrity Check

## Objective

Add a deterministic local check that validates existing MVP/failure-intelligence artifact references and hashes remain internally consistent across generated summaries, evidence bundles, and exported packages. This should tighten confidence in artifact provenance without adding analysis behavior.

## Scope

- Add a compact `scripts/*_check.py` registered in `scripts/check.py` that reuses existing example fixtures and typed models.
- Verify that artifact references in generated reports resolve to the expected local files and that recorded SHA-256 values match file contents where the existing schemas record hashes.
- Keep the check deterministic and local; gate any simulator-backed path cleanly if needed, but prefer existing hermetic artifacts.
- Do not add schemas, new analysis behavior, graph features, provider integration, automatic patching, or broad refactors.

## Acceptance Criteria

- One registered deterministic local check validates provenance/path/hash consistency across existing generated artifacts.
- The implementation reuses existing models and artifact conventions only.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No new analysis behavior, schema changes, graph features, model providers, databases, remote execution, CI, UI, automatic patching, or causal claims.

## Completion State

Active.
