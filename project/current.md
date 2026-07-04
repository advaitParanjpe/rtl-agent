# Portable Failure Package Export

## Objective

Add a read-only command that packages an existing failure-intelligence run directory into a single portable, self-contained failure package that can be transported, verified, and inspected elsewhere. Reuse the existing run manifest, inspection validation, hashing, and safe path resolution; deterministic, bounded, and local. Add no new analysis behavior.

## Scope

- Add a deterministic export service and a CLI command (such as `export-failure-package`) that reads a run directory and writes a single portable package to a caller-specified output location.
- The package must be self-contained and carry: the run manifest, the failure report (JSON and Markdown), and the run-relative run artifacts referenced by the manifest, laid out under a stable package structure.
- Emit a typed, versioned package manifest that indexes every packaged file with its run-relative path, kind, and SHA-256 (reusing the existing hashing), so the package can be verified after transport.
- Before packaging, validate the run using the existing inspection service; refuse to export (or clearly mark) an invalid run per an explicit, documented rule, and never package unsafe or escaping paths.
- Resolve run-relative artifacts against the actual run directory using the existing safe resolver; never follow paths that escape the run directory.
- Produce a deterministic package: identical run inputs produce identical package contents except for inherently volatile metadata (timestamps); use stable ordering and sorted serialization.
- The command is read-only with respect to the source run directory: it must not modify, regenerate, delete, resume, or replay anything in the run.
- Add compact tests covering a valid-run package, package-manifest hashes, refusal/handling of an invalid run, an unsafe recorded path, and deterministic package contents.
- Add one concise runnable README example.

## Acceptance Criteria

- The exported package is self-contained (run manifest + failure report JSON/Markdown + referenced artifacts) and indexed by a typed, versioned package manifest with per-file SHA-256.
- Export reuses the existing inspection validation, hashing, and safe path resolution; it never packages unsafe/escaping paths and never mutates the source run.
- Invalid runs are handled per an explicit, documented rule (refused or clearly marked), not silently exported as valid.
- Package contents are deterministic for identical inputs aside from volatile timestamps.
- No existing artifact schema, provider behavior, or product workflow changes beyond adding the export command; any new report is typed and versioned.
- All existing tests, example checks, packaging smoke, and canonical validation continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not add remote artifact storage, cloud synchronization, databases, distributed execution, model providers, CI, UI, or new analysis behavior.
- Do not mutate, regenerate, resume, or replay the source run during export.
- Do not add automatic migration of unsupported manifest schemas.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
