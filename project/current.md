# Persistent HKG Lifecycle and Counterfactual Evidence Integration Audit

## Objective

Produce a bounded design/audit artifact that prepares the next implementation milestone for deterministic HKG persistence and integration with counterfactual evidence, without implementing the lifecycle itself.

## Scope

- Audit the current HKG construction/query/memory surfaces and the MVP/counterfactual artifacts they would need to ingest.
- Specify deterministic HKG build, update, and idempotence semantics.
- Specify ingestion expectations for real MVP intervention and experiment evidence.
- Define the standard artifact location and CLI lifecycle expectations for future implementation.
- Define how historical-memory wiring should feed later MVP runs.
- Record schema compatibility and provenance requirements, including artifact references and hashes.
- Keep this design/audit only; do not change runtime behavior.

## Acceptance Criteria

- One focused design/audit document is added under `docs/architecture/`.
- The document identifies concrete implementation boundaries, inputs, outputs, invariants, and risks for the future persistent-HKG lifecycle milestone.
- No HKG lifecycle code, CLI commands, schema changes, supervisor enforcement, or historical-memory wiring is implemented.
- Canonical validation continues to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No implementation of HKG persistence lifecycle, build/update CLI commands, database/server/UI, external model integration, supervisor enforcement, historical-memory wiring, automatic patching, or causal/root-cause claims.

## Completion State

Active.
