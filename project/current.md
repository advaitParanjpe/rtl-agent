# Prohibited-Shortcut Review Finding Example Check

## Objective

Add a compact, deterministic local example check that exercises the existing but currently untested `det-prohibited-shortcut-N` review finding, using a deliberate diff that textually conflicts with a task-contract prohibited shortcut. This closes the last remaining coverage gap for the review service's prohibited-shortcut detection. It is read-only and reuses the existing review and task-contract representations with no new analysis behavior.

## Scope

- Add a small example check (a `scripts/*_check.py` registered in `scripts/check.py`, consistent with the existing example checks) that constructs a minimal task contract containing at least one explicit prohibited shortcut, plus a candidate implementation diff whose text deliberately conflicts with that prohibited shortcut, runs the existing review service, and asserts the `det-prohibited-shortcut-N` finding is produced with the expected deterministic finding id and evidence.
- Reuse the existing review service, task-contract parsing/representation, and review-report models verbatim; do not add new analysis behavior, new finding types, or schema changes.
- Keep the check hermetic (no simulator dependency) and deterministic; if any real dependency is required, gate it cleanly, but prefer a fully hermetic fixture.
- If a genuine defect in the existing prohibited-shortcut detection is discovered while writing the check, fix only that narrow defect; otherwise leave the review service unchanged.

## Acceptance Criteria

- One registered example check deterministically exercises the `det-prohibited-shortcut-N` review finding via the existing review service and asserts the finding is emitted for a diff that conflicts with a task-contract prohibited shortcut, and absent for a clean diff.
- No new analysis behavior, finding types, or schema changes; the check is read-only and hermetic.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- No new review analysis behavior, no new finding types, no schema changes, no automatic patching, and no causal claims.
- No new model providers, databases, remote execution, CI, or UI.

## Completion State

Active.
