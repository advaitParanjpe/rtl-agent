# Persistent HKG Source Lifecycle and Recovery Audit

## Objective

Perform a bounded, read-only architecture and implementation audit of the concrete operational limitations left by persistent HKG v1: MVP source identity stability, explicit source replacement/removal, interrupted-write recovery, and concurrent-writer detection. Define the smallest coherent deterministic local follow-up without implementing it.

## Scope

- Inspect the implemented schema-2 graph/manifest lifecycle, source adapters, atomic-write behavior, CLI, tests, and registered lifecycle check.
- Evaluate whether an additive immutable MVP source identifier is justified by the current `target_commit` plus output-directory-name key and identify every affected producer/consumer if so.
- Define explicit, provenance-safe semantics for replacing or removing one source without silently retaining stale source-scoped graph evidence.
- Define bounded crash-recovery and concurrent-writer detection requirements consistent with the two-file local store; do not assume a database or locking framework is required.
- Recommend one smallest coherent implementation milestone, with exact files, compatibility rules, failure behavior, tests, and acceptance criteria.

## Acceptance Criteria

- The audit distinguishes confirmed behavior, proposed behavior, and unresolved issues with concrete file paths, symbols, identities, and runtime evidence.
- Replacement/removal rules account for source-scoped nodes, shared canonical entities, derived clusters, provenance, idempotence, and rollback on failure.
- Recovery and writer-safety recommendations preserve deterministic local operation and identify whether a lightweight generation/compare-and-swap mechanism is sufficient.
- Any source-schema addition is justified narrowly and remains additive/backward-compatible; unnecessary migrations are rejected.
- The next implementation milestone is bounded, testable, and does not include unrelated HKG query, inference, server, UI, or database work.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Read-only audit only. No production code, tests, schemas, CLI behavior, graph/source artifacts, source replacement/removal, writer locking, database/server/UI, broad migration framework, graph federation, advanced graph algorithms, external model-provider integration, supervisor enforcement, automatic patch generation, or causal/root-cause claims.

## Completion State

Active.
