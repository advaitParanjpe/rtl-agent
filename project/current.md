# Persistent HKG Lifecycle and Historical MVP Integration v1

## Objective

Implement one deterministic local vertical slice that persists and updates a provenance-validated HKG from real failure-intelligence runs, relocated failure packages, and MVP counterfactual outputs; exposes minimal build/update/inspect CLI operations; and optionally supplies prior, self-excluded HKG memory to later MVP repair suggestions with explicit JSON/Markdown disclosure and safe no-memory fallback.

## Scope

- Implement the canonical `.rtl-agent/hkg/` graph plus integrity-manifest store specified in `docs/architecture/persistent-hkg-lifecycle-audit.md`.
- Add validated lifecycle adapters for original failure runs, relocated failure packages, and real MVP demo outputs.
- Implement deterministic build, update, idempotence, conflict rejection, provenance validation, and minimal `hkg-build`, `hkg-update`, and `hkg-inspect` commands.
- Correct HKG-only persistent identities/provenance and ingest real minimized-stimulus, intervention, experiment, outcome, comparison, and ranking evidence.
- Add optional self-excluded historical-memory lookup to later MVP repair suggestions with structured/Markdown disclosure and safe fallback.
- Add focused tests and one deterministic hermetic registered lifecycle check.

## Acceptance Criteria

- Rebuilding or reingesting identical relocated sources is byte-deterministic and idempotent.
- Changed same-identity, tampered, unsafe, malformed, corrupt, or incompatible evidence is rejected without partial writes.
- Real failure/package/MVP artifacts are ingested with source-relative, hash-cited provenance; same-canonical failures remain distinct occurrences.
- The three bounded lifecycle commands validate and report the persistent store deterministically.
- MVP remains valid with absent/unavailable memory and discloses verified historical evidence when used without causal overclaiming.
- Focused, hermetic lifecycle, full canonical, whitespace, and Git-state validation pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No external model-provider integration, supervisor enforcement, automatic patch generation, database/server/UI, source deletion/replacement, broad migration framework, graph federation, advanced graph algorithms, broad query language, or causal/root-cause claims.

## Completion State

Active.
