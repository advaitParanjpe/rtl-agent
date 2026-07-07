# History

Append only. Keep entries compact: milestone, decisions, validation evidence, and known limitations.

## 2026-07-01 - Bootstrap: Deterministic Orchestration Foundation

Completed the initial repository bootstrap as a Python 3.12+ project with an installable `rtl-agent` CLI, typed YAML configuration, artifact-backed named command execution, a durable run store, a narrow Git worktree abstraction, tests, and canonical validation script.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 11 pytest tests.
- `.venv/bin/rtl-agent --help` - passed.
- `.venv/bin/rtl-agent init` - passed.
- `.venv/bin/python -m rtl_agent --help` - passed.
- `.venv/bin/python -m rtl_agent inspect-config --config examples/rtl-agent.yaml` - passed.
- `.venv/bin/python -m rtl_agent run-command --config examples/rtl-agent.yaml --command smoke` - passed and wrote run artifacts under `.rtl-agent/runs/20260701T211537Z-9828a455/`.

Architectural decisions:

- Commands are executed only by configured name and use `subprocess.run(..., shell=False)`.
- Large stdout/stderr are written to command artifact files instead of retained in memory.
- Configuration paths resolve relative to the config file location.
- Git worktree support is intentionally limited to validation, path planning, create, and remove; no commits, pushes, remotes, or branch automation.

Known limitations:

- No RTL repository discovery yet.
- No AI coding agent or model-provider abstraction yet.
- No EDA-specific tool integration beyond deterministic configured commands.

## 2026-07-01 - RTL Repository Discovery and Structured Repository Model

Completed deterministic RTL repository discovery with a typed, versioned repository-map JSON schema, bounded scanner, lightweight SystemVerilog declaration and instantiation parser, hierarchy candidate scoring, build/verification command evidence extraction, Git metadata discovery, CLI entry points, run-artifact integration, tests, and README usage.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 22 pytest tests.
- `.venv/bin/python -m rtl_agent discover --config examples/rtl-agent.yaml` - passed and wrote `.rtl-agent/runs/<run-id>/discovery/repository-map.json`.
- `.venv/bin/rtl-agent inspect-repo --repo examples/simple-rtl --output .rtl-agent/simple-rtl-map.json` - passed; inspected JSON reported schema version 1, 7 files, 4 declarations, 2 discovered commands, design top candidates, and testbench candidates.
- `.venv/bin/rtl-agent inspect-repo --repo . --output .rtl-agent/self-map.json` - passed gracefully on the Python-heavy `rtl-agent` repository.
- `git diff --check` - passed.

Architectural decisions:

- Discovery is deterministic and filesystem-based; it never executes discovered repository commands.
- Scanner enforces default exclusions, configurable include/exclude patterns, maximum file count, maximum text file size, binary skipping, and safe symlink handling.
- SystemVerilog support is intentionally lightweight: comments and strings are masked before regex extraction, with parser notes recorded in the map.
- Top-level modules are scored candidates with reasons rather than asserted facts.
- `src/rtl_agent/artifacts` is tracked after narrowing the root artifact ignore rule.

Known limitations:

- No full SystemVerilog preprocessing, elaboration, parameter resolution, generate expansion, or semantic compilation.
- Build discovery records command evidence but does not integrate or run EDA tools.
- No issue parsing, task contracts, AI coding agent, or model-provider abstraction yet.

## 2026-07-01 - Issue Parsing and Explicit Task Contracts

Completed deterministic issue parsing with a typed, versioned task-contract JSON schema, Markdown/plain-text section extraction, checklist handling, fenced validation command parsing, path/code reference extraction, optional repository-map validation, CLI support, tests, and README usage.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 30 pytest tests.
- `.venv/bin/rtl-agent inspect-repo --repo examples/simple-rtl --output .rtl-agent/simple-rtl-map.json` - passed and produced a repository map for issue-context validation.
- `.venv/bin/rtl-agent parse-issue --issue examples/issues/reset-behavior.md --repository-map .rtl-agent/simple-rtl-map.json --output .rtl-agent/reset-task-contract.json` - passed; inspected JSON reported schema version 1, 1 requested behavior item, 2 acceptance criteria, 2 validation commands, no warnings, and matched repository-relative paths.
- `git diff --check` - passed.

Architectural decisions:

- Issue parsing extracts only explicit sections, bullets, checkboxes, fenced shell commands, and path/code references.
- Ambiguous prose is warned about rather than converted into invented requirements.
- Parsed validation commands are recorded as argv and raw text but never executed.
- Repository-map input is validated with the existing Pydantic repository-map schema and used only for context matching.

Known limitations:

- No natural-language planning or inference beyond deterministic section and pattern extraction.
- No model-provider integration or autonomous implementation-agent behavior yet.
- No execution of parsed validation commands.

## 2026-07-01 - Model Provider Abstraction and One Bounded Implementation Agent

Completed a tightly bounded implementation loop with typed provider request/response models, a deterministic local stub provider, explicit file and command permissions, repository-local structured `read_file` and `replace_text` tool calls, limited iterations, run-artifact audit trail, named-command-only validation, proposed-diff/failure reporting, CLI support, tests, and README usage.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 35 pytest tests.
- `.venv/bin/rtl-agent inspect-repo --repo examples/simple-rtl --output .rtl-agent/simple-rtl-map.json` - passed.
- `.venv/bin/rtl-agent parse-issue --issue examples/issues/reset-behavior.md --repository-map .rtl-agent/simple-rtl-map.json --output .rtl-agent/reset-task-contract.json` - passed.
- `.venv/bin/rtl-agent implement-task --config examples/simple-rtl-agent.yaml --task-contract .rtl-agent/reset-task-contract.json --repository-map .rtl-agent/simple-rtl-map.json --provider-plan examples/provider-plans/no-change.json --allowed-file rtl/top.sv --max-iterations 1` - passed and wrote implementation report, provider request/response artifacts, and diff artifact under `.rtl-agent/runs/<run-id>/implementation/`.
- `git diff --check` - passed.

Architectural decisions:

- The only provider shipped in this milestone is a local JSON stub provider for deterministic tests and examples.
- Model output is restricted to structured tool calls; arbitrary shell commands from provider output are not executed.
- Editable files must be explicitly allowed, repository-relative, present in the repository map, and in task-contract scope.
- Validation is limited to configured named commands explicitly allowed on the CLI.
- The implementation loop returns either a proposed-diff report or an honest structured failure report.

Known limitations:

- No real external model-provider integration yet.
- No multi-agent framework, reviewer agent, pull-request automation, waveform analysis, mutation testing, CI bots, databases, queues, dashboards, or web UI.
- No semantic verification beyond configured named-command execution.

## 2026-07-02 - Verification Execution and Failure Iteration

Completed deterministic verification classification and bounded retry iteration inside the existing implementation-agent flow. Validation command results are classified from command metadata and bounded stdout/stderr excerpts, failed validation is never reported as success, concise structured failure evidence is passed to the next provider iteration, retry/stop decisions are recorded, and reports include validation classifications and retry decisions.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 41 pytest tests.
- `.venv/bin/rtl-agent inspect-repo --repo examples/simple-rtl --output .rtl-agent/simple-rtl-map.json` - passed.
- `.venv/bin/rtl-agent parse-issue --issue examples/issues/define-value.md --repository-map .rtl-agent/simple-rtl-map.json --output .rtl-agent/define-task-contract.json` - passed.
- `.venv/bin/rtl-agent implement-task --config examples/simple-rtl-agent.yaml --task-contract .rtl-agent/define-task-contract.json --repository-map .rtl-agent/simple-rtl-map.json --provider-plan examples/provider-plans/retry-after-failure.json --allowed-file rtl/defs.svh --validation-command check-define --max-iterations 2` - passed; report recorded first validation as `assertion_or_test_failure`, retried once, then passed.
- `git diff --check` - passed.

Architectural decisions:

- Verification classification reuses existing command-runner artifacts and stores only concise bounded excerpts in provider-facing failure evidence.
- Retry is strictly bounded by `max_iterations` and records `retry` or `stop` decisions.
- Failed validation keeps the report failed when the retry limit is reached.
- Command execution remains restricted to configured named commands explicitly allowed on the CLI.

Known limitations:

- Classification is heuristic and deterministic; it does not perform semantic log analysis.
- No reviewer agent, pull-request automation, waveform analysis, mutation testing, CI bots, databases, queues, dashboards, or web UI yet.

## 2026-07-02 - Independent Reviewer

Completed a read-only independent review pass over task-contract, repository-map, implementation-report, diff, and validation artifacts. The reviewer emits a versioned review-report JSON artifact with deterministic findings separated from optional provider-backed semantic findings, requires every finding to cite concrete evidence, rejects missing or final failed validation as unacceptable, flags out-of-scope edits and missing artifacts, and exposes a `review-task` CLI command.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 49 pytest tests.
- `.venv/bin/rtl-agent inspect-repo --repo examples/simple-rtl --output .rtl-agent/simple-rtl-map.json` - passed.
- `.venv/bin/rtl-agent parse-issue --issue examples/issues/define-value.md --repository-map .rtl-agent/simple-rtl-map.json --output .rtl-agent/define-task-contract.json` - passed.
- `.venv/bin/rtl-agent implement-task --config examples/simple-rtl-agent.yaml --task-contract .rtl-agent/define-task-contract.json --repository-map .rtl-agent/simple-rtl-map.json --provider-plan examples/provider-plans/retry-after-failure.json --allowed-file rtl/defs.svh --validation-command check-define --max-iterations 2` - passed.
- `.venv/bin/rtl-agent review-task --task-contract .rtl-agent/define-task-contract.json --repository-map .rtl-agent/simple-rtl-map.json --implementation-report <report.json> --output .rtl-agent/review-report.json --fail-on-unacceptable` - passed; review was acceptable with one deterministic warning citing the retried validation failure.
- `git diff --check` - passed.

Architectural decisions:

- The reviewer is read-only: it does not edit files, execute commands, retry implementation, or override final failed validation.
- Deterministic findings and provider-backed findings are stored separately.
- Provider-backed findings are optional input and must cite concrete evidence.
- Intermediate failed validation attempts can be cited as warnings when a later validation for the same command passed; final failed or missing validation remains unacceptable.

Known limitations:

- Review checks are deterministic and artifact-based; no semantic model reviewer is included yet.
- Prohibited-shortcut conflict detection is simple diff-token matching.
- No pull-request automation, waveform analysis, mutation testing, CI bots, databases, queues, dashboards, or web UI yet.

## 2026-07-02 - Waveform and Assertion Triage

Completed deterministic waveform and assertion triage from existing command-runner artifacts. The triage pass reads command result JSON plus bounded stdout/stderr artifacts, extracts explicit assertion failures, simulator context, waveform references, missing-waveform warnings, and bounded evidence into a versioned triage-report JSON artifact, and exposes a `triage-command` CLI command. Review can optionally consume triage reports and cite triage warnings or assertion summaries.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 56 pytest tests.
- `.venv/bin/rtl-agent triage-command --command-result .rtl-agent/triage-smoke/result.json --output .rtl-agent/triage-smoke/triage.json` - passed on a synthetic command artifact with assertion and waveform references.
- `git diff --check` - passed.

Architectural decisions:

- Triage is read-only and artifact-based; it does not execute simulators or commands.
- Waveform references are recorded by path and existence only; waveform contents are not interpreted.
- Evidence extraction is bounded by line count, item count, and text length.
- Review integration is optional and cites triage warnings as deterministic review findings.

Known limitations:

- Triage patterns are deterministic heuristics for common simulator/assertion text.
- No waveform rendering, semantic waveform interpretation, model-based debugger, mutation testing, CI bots, databases, queues, dashboards, or web UI.

## 2026-07-02 - Verification Strength and Mutation Assessment

Completed deterministic verification-strength assessment from existing artifacts. The assessment reads task-contract, repository-map, implementation-report, optional review-report, and optional triage-report JSON; emits a versioned verification-strength report; scores bounded signals for passed command coverage, acceptance-criteria references, changed-file relevance, retry history, review outcome, repository command context, and triage availability; and flags weak patterns including no validation, failed latest validation, smoke-only validation, missing acceptance coverage, failed review, missing triage for simulator-like failures, and validation unrelated to changed files.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 63 pytest tests.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Assessment is read-only and artifact-only: it does not execute commands, mutate source files, inspect waveform contents, run mutation tests, or call model providers.
- Strength reports reuse existing task-contract, repository-map, implementation-report, review, triage, and command-result artifacts rather than introducing a new evidence store.
- Weak/insufficient conclusions are deterministic and evidence-cited; uncertainty is represented as weak patterns and bounded scoring rather than semantic claims.
- Mutation assessment is limited to identifying weak validation signals; no mutation execution framework was added.

Known limitations:

- Acceptance and changed-file relevance use deterministic textual evidence, not semantic proof.
- Smoke-only and simulator-failure detection are conservative heuristics.
- No real model provider, semantic waveform analysis, CI automation, broad mutation framework, databases, queues, dashboards, or web UI.

## 2026-07-02 - Benchmark Suite Manifest and Local Runner

Completed a deterministic local benchmark-suite foundation. Benchmark manifests declare a run-artifact directory, bounded resources, compact local cases, existing rtl-agent config files, named-command steps, per-step timeout overrides, and expected observed statuses. The runner reuses `CommandRunner` and `RunStore`, writes command artifacts plus a versioned benchmark report, and records honest `passed`, `failed`, `timeout`, and `infrastructure_error` results without hiding earlier artifacts.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 71 pytest tests.
- `PYTHONPATH=src .venv/bin/python -m rtl_agent run-benchmark --manifest examples/benchmarks/local-smoke.yaml --fail-on-unmet-expected` - passed with 2 compact local cases.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Benchmark execution is local and compact: no external repository downloads, copied large RTL projects, model providers, pull requests, CI, dashboards, databases, queues, or web UI.
- The runner invokes existing configured named commands instead of duplicating orchestration logic.
- `CommandRunner` gained an optional deterministic command-id factory for stable benchmark tests while preserving UUID command IDs by default.
- Expected outcomes are compared against observed step statuses, but observed failure, timeout, and infrastructure-error statuses are still recorded directly.

Known limitations:

- The first benchmark runner supports named-command steps only.
- Reports include measured durations, so reruns are comparable but not byte-identical across separate executions.
- No benchmark matrix over external RTL repositories yet.

## 2026-07-02 - Evidence Bundle Export

Completed deterministic local evidence-bundle export from existing run artifacts. The exporter writes a compact `manifest.json` and `bundle.json` under a caller-specified output directory, preserves provenance through run-relative artifact references, records SHA-256 hashes, byte sizes, JSON schema versions when present, and explicit omitted-content reasons for logs and other artifacts. Missing optional artifacts are warnings; missing required `run.json` produces a failed export result.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 78 pytest tests.
- `PYTHONPATH=src .venv/bin/python -m rtl_agent run-benchmark --manifest examples/benchmarks/local-smoke.yaml --fail-on-unmet-expected` - passed and produced local run artifacts.
- `PYTHONPATH=src .venv/bin/python -m rtl_agent export-evidence --run-dir .rtl-agent/runs/20260702T120133Z-f762820a --output-dir .rtl-agent/bundles/20260702T120133Z-f762820a --fail-on-failed-export` - passed with 9 artifact references and 2 optional-artifact warnings.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Export is index-only and artifact-based: it does not execute commands, mutate source files, copy large logs, inspect waveforms, call providers, upload artifacts, sign bundles, or add cloud storage.
- Artifact classification reuses existing run layout and report schemas; unknown JSON and non-JSON artifacts are still hashed and referenced.
- Command logs and waveform-like files are explicitly marked referenced-only with omitted-content reasons.
- The export result is deterministic for the same run artifact inputs.

Known limitations:

- The exporter indexes artifacts present under one local run directory only.
- It records artifact metadata and hashes, not embedded artifact contents.
- Optional report discovery outside the run directory is not included.

## 2026-07-02 - Schema Examples and Compatibility Fixtures

Completed compact checked-in public-schema examples for repository-map, task-contract, implementation-report, review-report, triage-report, verification-strength-report, benchmark-report, and evidence-bundle-report artifacts. Added compatibility tests that discover all checked-in schema examples, validate each through the current Pydantic model, re-serialize through `model_dump(mode="json")`, and keep assertions focused on schema compatibility rather than volatile timestamps, durations, UUIDs, absolute paths, or real hashes.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 82 pytest tests.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Fixtures are compact documentation and compatibility artifacts, not generated run directories.
- Compatibility checks reuse existing typed models rather than handwritten duplicate schemas.
- Fixture content uses representative relative paths and placeholder values for volatile fields.

Known limitations:

- Fixtures are representative examples, not exhaustive schema conformance suites.
- No migration infrastructure, remote schema registry, code generation, CI automation, or unrelated workflow feature was added.

## 2026-07-02 - CLI Documentation Consistency Pass

Completed a focused README and CLI usability consistency pass. Removed stale bootstrap wording, clarified current deterministic capabilities and limitations, switched installation guidance to standard local install, added source-tree invocation guidance for development, collapsed duplicate quick-start command blocks, kept artifact-dependent commands in their own sections, and added README command help coverage tests.

Validation evidence:

- `.venv/bin/python -m pip install --force-reinstall ".[dev]"` - passed and produced a working installed `rtl-agent` console script.
- `.venv/bin/rtl-agent <documented-command> --help` - passed for every command documented in README.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, and 83 pytest tests.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Kept this milestone documentation/test focused; no orchestration features, providers, UI, CI, or schema changes were added.
- README quick start now contains compact runnable commands, while commands requiring existing run artifacts remain in the relevant artifact sections with placeholders.
- Compatibility test coverage checks documented command names against current Typer help.

Known limitations:

- README command examples are concise and do not form a full end-to-end implementation/review pipeline.
- Packaging smoke verification is still manual in this milestone and is queued as the next focused task.

## 2026-07-02 - Packaging Smoke Verification

Completed a bounded local packaging smoke check. The canonical `scripts/check.py` workflow now builds a local wheel without dependency resolution, installs it into a temporary virtual environment without index access, exposes current dev-environment runtime dependencies through a `.pth` file, and verifies `rtl-agent --help`, `python -m rtl_agent --help`, and every README-documented `rtl-agent <command> --help`.

Validation evidence:

- `.venv/bin/python scripts/packaging_smoke.py` - passed.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 83 pytest tests, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Packaging smoke verification is local and deterministic: no publishing, remote package index lookup, CI workflow, container, provider, UI, or unrelated packaging refactor was added.
- The script installs the built wheel into a temporary venv and verifies installed console-script plus module invocation, rather than relying on `PYTHONPATH=src`.
- `hatchling` is included in the dev extra so local no-build-isolation wheel builds are explicit.

Known limitations:

- The temporary packaging smoke environment reuses current dev-environment runtime dependencies through a `.pth` file instead of creating a fully dependency-isolated offline wheelhouse.
- The smoke check verifies CLI help availability, not every command's runtime behavior.

## 2026-07-02 - Compact End-to-End Example Check

Completed a compact local end-to-end example check. The canonical `scripts/check.py` workflow now runs `scripts/e2e_example_check.py`, which copies checked-in examples into a temporary workspace, exercises the real CLI workflow stages, and validates emitted artifacts through the existing Pydantic models. The check covers repository inspection, issue parsing, deterministic stub-provider implementation with one failed validation and retry, command-result triage, deterministic review, verification-strength assessment, local benchmark execution, and evidence-bundle export.

Validation evidence:

- `.venv/bin/python scripts/e2e_example_check.py` - passed.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 83 pytest tests, compact end-to-end example check, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The example check uses checked-in fixtures but copies them to a temporary workspace because the implementation stage intentionally mutates its configured repository.
- The check invokes the real CLI via `python -m rtl_agent` and validates generated JSON through existing artifact models rather than adding a parallel demo path or duplicate schemas.
- Assertions avoid volatile timestamps, UUIDs, durations, hashes, and absolute path equality; they focus on schema versions, statuses, stable file names, retry decisions, and artifact existence.

Known limitations:

- The scripted example is a compact deterministic smoke of the workflow, not an exhaustive integration test of every command option.
- It uses the existing local stub provider only; no real provider, external repository, CI, container, UI, or broad orchestration feature was added.

## 2026-07-03 - Failure Report Example Check

Completed a compact local failure-path example check. The canonical `scripts/check.py` workflow now runs `scripts/failure_example_check.py`, which copies checked-in examples into a temporary workspace, exercises the real CLI workflow with a one-iteration bounded implementation run, expects the terminal failed implementation exit, and validates emitted artifacts through the existing Pydantic models. The check covers failed implementation status and reason, command-result evidence, retry stop history, triage, unacceptable review disposition, insufficient verification-strength result, and evidence-bundle export of the failed run artifacts.

Validation evidence:

- `python3 scripts/failure_example_check.py` - passed.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 83 pytest tests, compact end-to-end example check, compact failure example check, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The failure example reuses the existing compact fixtures, stub-provider plan, configured `check-define` command, CLI stages, run artifacts, and schemas rather than adding a parallel demo path.
- The implementation stage is bounded to one iteration so the first real validation failure becomes the terminal report; assertions avoid timestamps, UUIDs, absolute paths, durations, and hashes.
- Review, verification-strength, triage, and evidence-bundle artifacts are written under the temporary run directory where practical so evidence export can classify them.

Known limitations:

- The check covers a deterministic validation-failure terminal path, not every possible provider, permission, or structured-tool failure mode.
- It remains a compact local workflow smoke; no real provider, external repository, CI, container, dashboard, database, queue, UI, semantic waveform analysis, or broad orchestration feature was added.

## 2026-07-03 - Cross-Agent Workflow Portability

Completed a focused repository-workflow portability update so Codex, Claude Code, or another coding agent can resume from checked-in repository state. Added a thin `CLAUDE.md` adapter, inactive `project/handoff.md` template, concise portability/session-start/session-end rules in `AGENTS.md`, launcher documentation in README, and a canonical deterministic portability check.

Validation evidence:

- `python3 scripts/agent_portability_check.py` - passed.
- `python3 scripts/check.py` - passed.
- `git diff --check` - passed.
- `git status --short --branch` - reviewed before commit.
- `grep -n "AGENTS.md" CLAUDE.md` - passed.
- `grep -n "Status:" project/handoff.md` - passed.

Architectural decisions:

- `AGENTS.md` remains authoritative; `CLAUDE.md` is only a thin adapter.
- `project/current.md` remains the only active milestone; `project/handoff.md` is inactive continuity state unless explicitly marked active.
- The existing active product milestone was preserved.

Known limitations:

- The portability check is deterministic file-policy validation, not automatic conflict resolution or branch synchronization.

## 2026-07-03 - Tool Failure Report Example Check

Completed a compact local structured-tool failure example check. The canonical `scripts/check.py` workflow now runs `scripts/tool_failure_example_check.py`, which copies checked-in examples into a temporary workspace, uses the existing stub-provider plan against a deliberately mismatched temporary fixture file, expects the real `replace_text` tool call to fail, and validates emitted artifacts through the existing Pydantic models. The check covers failed implementation status and reason, failed tool-result evidence, absence of validation execution and command artifacts, unacceptable review disposition, insufficient verification-strength result, and evidence-bundle export of the failed run artifacts.

Validation evidence:

- `python3 scripts/tool_failure_example_check.py` - passed.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 83 pytest tests, agent portability check, compact end-to-end example check, compact failure example check, compact tool-failure example check, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short --branch` - reviewed before commit.

Architectural decisions:

- The tool-failure example reuses checked-in examples, the existing `retry-after-failure` stub-provider plan, real CLI stages, run artifacts, and schemas rather than adding a parallel demo path.
- The temporary workspace file is changed before implementation so the allowed structured `replace_text` call fails deterministically with zero matches.
- No validation command executes after the tool failure; review, verification-strength, and evidence-bundle stages consume the failed implementation artifact directly.

Known limitations:

- The check covers one deterministic structured-tool failure mode, not every possible provider, permission, or malformed tool-call failure.
- It remains a compact local workflow smoke; no real provider, external repository, CI, container, dashboard, database, queue, UI, semantic waveform analysis, or broad orchestration feature was added.

## 2026-07-02 - Example Script Helper Consolidation

Consolidated the duplicated CLI-invocation helper shared by the local example-check scripts. Added a small `scripts/_example_check.py` module that exposes the repository root, the venv-aware Python interpreter, source-path setup, and the `run_cli` subprocess helper. The end-to-end, failure, and tool-failure example scripts now import that helper instead of each redefining `ROOT`, `PYTHON`, `sys.path` insertion, and a near-identical `run_cli`, and their per-example assertions are unchanged.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 83 pytest tests, agent portability check, compact end-to-end example check, compact failure example check, compact tool-failure example check, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The shared helper is a single dependency-free module in `scripts/`; no framework, package, or new dependency was introduced.
- Removing the mid-file `sys.path.insert` let the two `# ruff: noqa: E402` suppressions be dropped while keeping the source tree importable via the helper's import-time path setup.
- `run_cli(args, expected_exit=0)` unifies the success-path and expected-failure-path callers so each example still reads its own exit expectation inline.
- The structurally different `agent_portability_check.py` and `packaging_smoke.py` scripts were intentionally left untouched; they do not share the CLI-subprocess-JSON pattern.

Known limitations:

- Consolidation covers only the three example-check scripts that share the CLI-invocation pattern.
- No workflow behavior, artifact schema, CLI behavior, or provider behavior changed.

## 2026-07-03 - No-Change Implementation Example Check

Completed a compact local example check for the deterministic no-op (no-change) implementation path. `scripts/no_change_example_check.py` copies checked-in examples into a temporary workspace, scopes `rtl/top.sv` via the existing `reset-behavior.md` issue, drives `implement-task` with the existing `no-change.json` provider plan, and validates emitted artifacts through the current typed models. The check reuses the shared `scripts/_example_check.py` helper and is registered in `scripts/check.py`. It confirms that a successful `replace_text` tool call with identical old/new content produces a `proposed_diff` implementation report, an empty diff artifact, unchanged file content, zero validation results, an `unacceptable` review (`det-validation-missing`), an `insufficient` verification-strength result (`no-validation`, `failed-review` weak patterns), and a passing evidence-bundle export that includes the empty diff artifact and omits any `commands/` artifacts.

Validation evidence:

- `python3 scripts/no_change_example_check.py` - passed.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 83 pytest tests, agent portability check, compact end-to-end example check, compact failure example check, compact tool-failure example check, compact no-change example check, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The no-change example reuses the existing `reset-behavior.md` issue (already scoped to `rtl/top.sv`) and the existing `no-change.json` stub-provider plan rather than adding new fixtures.
- Assertions cover the deterministic downstream consequence of a proposed diff with no requested validation commands: an error-severity `det-validation-missing` review finding and an `insufficient` verification-strength result, rather than treating "no validation" as a silent success.
- README's example-check summary paragraph was updated to describe the new check alongside the existing three.

Known limitations:

- The check covers one deterministic no-op tool-application path, not every possible zero-validation implementation scenario.
- It remains a compact local workflow smoke; no real provider, external repository, CI, container, dashboard, database, queue, UI, semantic waveform analysis, or broad orchestration feature was added.

## 2026-07-03 - VCD Failure Window Extraction

Built the first deterministic RTL failure-intelligence capability. Added a typed, versioned waveform-slice schema (`src/rtl_agent/waveform_slice_models.py`), a deterministic textual-VCD parser and window extractor (`src/rtl_agent/waveform/service.py`), and an `extract-waveform-window` CLI command. Given a VCD path, a failure timestamp, configurable time before/after, and optional exact signal names or hierarchical prefixes, the extractor parses headers, scopes, variables, timescale, and value changes, then emits only the bounded window as a compact waveform-slice artifact. It preserves hierarchical signal names, widths, identifiers, and bit ranges; represents scalar, vector, unknown (`x`), and high-impedance (`z`) values verbatim; records each selected signal's value at the window start when a prior change makes it determinable; and records source metadata (path, size, SHA-256, timescale, requested window, observed bounds, selected signals, warnings, and parse statistics). The Prohibited-Shortcut Review Finding Example Check that had been auto-proposed as the next milestone was deliberately deferred in the roadmap in favor of this product milestone.

Validation evidence:

- `PYTHONPATH=src .venv/bin/rtl-agent extract-waveform-window --vcd examples/waveforms/failure.vcd --failure-time 40 --before 15 --after 5 --signal-prefix top.dut --output .rtl-agent/waveform-slice.json` - passed; emitted a bounded two-signal slice with observed bounds inside the requested window.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 103 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change example checks, and packaging smoke verification (which now also verifies `extract-waveform-window --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Textual VCD only. Parsing is a single deterministic token stream over the header plus a bounded scan of the value-change section; only selected identifiers and in-window changes are retained, so memory stays bounded (with a file-size guard and truncation warnings).
- Timestamp boundaries are inclusive; a signal's initial value at the window start is the most recent change strictly before `requested_start`, and is marked non-determinable when no such change exists.
- The waveform-slice artifact is intentionally kept out of `examples/schema-artifacts/` because the existing schema-example guard forbids `.vcd` fragments; VCD fixtures live under `examples/waveforms/` instead, and no existing schema-example test was modified.
- Optional `--triage-report` source resolution reuses existing triage `waveform_references` without redesigning triage.
- The extractor never interprets causal meaning or claims root cause; parser notes state this explicitly.

Known limitations:

- Textual VCD only; no FST/FSDB, model-based analysis, source-driver tracing, or stimulus minimization.
- Value-change scanning reads to end-of-file for honest total statistics rather than early-exiting at the window end; bounded by a file-size guard and output caps.
- Signal aliasing (multiple `$var` references sharing one identifier) is supported by expanding per selected signal, but exotic array bit-selects are recorded by base name plus an optional raw bit-range string only.

## 2026-07-03 - Assertion-to-Waveform Failure Linking

Connected existing simulator/assertion triage artifacts to VCD failure-window extraction. Added a typed, versioned linkage report schema (`src/rtl_agent/assertion_waveform_link_models.py`), a deterministic linkage service (`src/rtl_agent/assertion_link/service.py`), and a `link-assertion-waveform` CLI command. Given an existing triage report, the workflow selects one assertion finding by stable id (`assertion-<index>`) or index, resolves its associated `.vcd` waveform reference, converts the assertion's simulator time into VCD tick units using the waveform's `$timescale`, and invokes the existing `extract_waveform_window` service (reusing its parser via a new `read_vcd_timescale` helper) rather than duplicating VCD parsing. It supports configurable before/after window and optional exact-name and hierarchical-prefix signal filters, and emits a linkage report recording the selected assertion, source triage report, selected waveform, timestamp-conversion details, generated waveform-slice path and SHA-256, warnings, and unresolved ambiguities. A compact runnable triage fixture (`examples/waveforms/triage-report.json`, VCD referenced by repository-relative path) drives the README example and a repo-root test.

Validation evidence:

- `PYTHONPATH=src .venv/bin/rtl-agent link-assertion-waveform --triage-report examples/waveforms/triage-report.json --assertion-id assertion-0 --before 15 --after 5 --signal-prefix top.dut --slice-output .rtl-agent/waveform-slice.json --output .rtl-agent/assertion-link.json` - passed; converted `40 ns` at a `1ns` timescale to tick 40 and generated a bounded slice.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 121 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change example checks, and packaging smoke verification (which now also verifies `link-assertion-waveform --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The linkage service reuses `extract_waveform_window` and a thin new `read_vcd_timescale` helper (both delegating to the same header parser) so VCD parsing is never duplicated.
- Timestamp conversion is exact integer arithmetic in femtoseconds via `fractions.Fraction`; only explicit `fs/ps/ns/us/ms/s` assertion units and `1|10|100` VCD timescales convert. Missing timestamps, non-time units (e.g. `cycles`), and absent/unsupported timescales fail honestly rather than guessing. Non-integer tick results are floored with an explicit warning.
- Ambiguity is never resolved silently: assertion selection is required (no default pick), and multiple distinct existing `.vcd` candidates require `--waveform-path`, which then records the unselected candidates in `unresolved_ambiguities`.
- Waveform candidates are re-validated on disk at link time; missing files and non-`.vcd` formats (unsupported) produce distinct honest errors, and malformed VCDs surface the parser's error.
- The linkage never infers root cause; parser notes state this explicitly.

Known limitations:

- Textual VCD only; no FST/FSDB, semantic waveform interpretation, signal-dependency tracing, automatic signal selection, source localization, stimulus minimization, or patch generation.
- Assertion timestamps expressed in clock cycles or without an explicit SI time unit are treated as ambiguous and rejected, since converting them would require clock-period assumptions.

## 2026-07-03 - Waveform Evidence Bundle Integration

Extended the deterministic evidence-bundle exporter so waveform-slice and assertion-to-waveform linkage artifacts under a run directory are recognized alongside the other typed reports. Added two `EvidenceArtifactKind` values (`waveform_slice_report`, `assertion_waveform_link_report`) and two content-based classifiers in `_json_artifact_kind`, reusing the existing hashing, schema-version detection, run-relative provenance, and omitted-content rules with no changes to export flow, manifest/report schema shape, or any other artifact schema.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 123 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change example checks, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Classification uses distinctive JSON key-sets (`selected_assertion`/`selected_waveform`/`timestamp_conversion` for linkage; `window`/`value_changes`/`parse_statistics`/`selected_signals` for slices), matching the existing review/triage/verification-strength detection style rather than inventing fixed run-relative paths that these user-specified outputs do not have.
- Tests generate real slice and linkage artifacts from the checked-in VCD and triage fixtures, so a future field rename in either model surfaces as a classification-test failure.

Known limitations:

- Detection is content-based on stable top-level keys; deeply restructured future report schemas would need the key-sets updated.
- The linkage report's own generated waveform slice is classified as a waveform-slice artifact, which is correct but means one linkage run contributes two waveform-related artifacts to a bundle.

## 2026-07-03 - Automatic Relevant-Signal Reduction

Added deterministic relevant-signal reduction over an existing waveform slice. New typed, versioned report schema (`src/rtl_agent/relevant_signal_models.py`), a reduction service (`src/rtl_agent/signal_reduction/service.py`), and a `reduce-signals` CLI command consume a waveform-slice report (and optionally an assertion-link report and/or explicit assertion signal/summary flags) and rank each slice signal by explicit, evidence-cited criteria: assertion-named (100), transition at the failure timestamp (40), any in-window transition (20), unknown/high-impedance `x`/`z` presence (25), and shared parent-scope hierarchy proximity to the assertion signal (15). Retained signals are a strict, score-sorted, `--max-signals`-bounded subset, each citing its matched criteria; excluded signals are summarized by reason. The service also writes a reduced waveform-slice artifact (reusing the existing `WaveformSliceReport` schema and `write_waveform_slice`), filtered to the retained signals with recomputed selected-signal and in-window value-change statistics.

Validation evidence:

- `PYTHONPATH=src .venv/bin/rtl-agent extract-waveform-window --vcd examples/waveforms/failure.vcd --failure-time 40 --before 15 --after 5 --output .rtl-agent/waveform-slice.json` then `... reduce-signals --waveform-slice .rtl-agent/waveform-slice.json --assertion-signal top.dut.valid --reduced-slice-output .rtl-agent/reduced-slice.json --output .rtl-agent/relevant-signals.json` - passed; `top.dut.valid` ranked highest (assertion-named + transition + x/z).
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 136 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change example checks, and packaging smoke verification (which now also verifies `reduce-signals --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Reduction consumes the existing slice artifact only; it never re-parses VCD or re-extracts windows. The reduced output reuses the unchanged `WaveformSliceReport` schema so downstream tools (evidence bundle) already recognize it.
- Criterion weights are fixed module constants and every retained signal carries per-criterion point/detail reasons, keeping ranking deterministic and auditable rather than a black-box score.
- Assertion context is optional and layered: explicit `--assertion-signal`/`--assertion-summary` flags take precedence over an `--assertion-link` report; with no context, ranking relies solely on transition and `x`/`z` evidence.
- Hierarchy proximity requires sharing the assertion signal's immediate parent scope (not merely the root), so shallow root-only overlap does not inflate relevance.

Known limitations:

- Relevance is heuristic and evidence-based, not causal; it deliberately performs no dependency tracing, semantic interpretation, RTL source localization, model-based analysis, stimulus minimization, or patch generation.
- Assertion-name matching is exact full-name, exact leaf-name, or whole-token summary match; it does not fuzzy-match renamed or partially-quoted signal references.

## 2026-07-03 - Passing-vs-Failing Waveform Comparison

Added deterministic comparison of a failing waveform slice against a passing (reference) slice. New typed, versioned comparison report schema (`src/rtl_agent/waveform_comparison_models.py`), a comparison service (`src/rtl_agent/waveform_comparison/service.py`), and a `compare-waveforms` CLI command reuse the existing `WaveformSliceReport` model (no VCD re-parsing). For each signal present in both slices, the service reconstructs the value timeline (initial value plus in-window transitions) and reports whether timelines are identical, the first divergence time with each side's value there, per-side transition counts, `x`/`z` differences, and divergence duration and intervals. It reports added/removed signals relative to the reference, the global earliest divergence and its signals, and a deterministic ranking of the most divergent signals. The time basis is explicit: identical timescales compare in shared ticks; differing-but-parseable timescales normalize to femtoseconds (recorded in `time_basis` with per-side tick sizes); ambiguous/incompatible timescales compare as raw ticks with a warning. Window mismatches restrict comparison to the overlapping range with a warning; ambiguous duplicate names, missing overlap, empty slices, and no shared signals all warn.

Validation evidence:

- Live pipeline: two `extract-waveform-window` runs on the fixture VCD and a stable-`state`/high-`valid` variant, then `compare-waveforms` - `top.dut.state` and `top.dut.valid` diverged (x/z differences), `top.clk`/`top.data` identical, global earliest divergence at tick 25.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 152 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change example checks, and packaging smoke verification (which now also verifies `compare-waveforms --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Comparison consumes the existing slice artifacts only; it never re-parses VCD or re-extracts windows. Signals are matched by hierarchical name (VCD identifiers can legitimately differ between two separate dumps).
- Value timelines are compared as step functions sampled at the union of both sides' transition times within the overlapping window, so differing tick grids and transition sets are handled without alignment heuristics.
- Timestamp normalization is explicit and recorded in `time_basis`; incompatible or ambiguous timescales are never silently aligned (they downgrade to raw-tick comparison with a warning).
- Divergence ranking is a deterministic integer score (duration-weighted, plus interval count and an x/z bonus); ordering is stable by score, first divergence time, then name.

Known limitations:

- Comparison is observational only: it reports value/timeline differences and never claims causal meaning, traces dependencies, localizes RTL source, minimizes stimulus, or generates patches.
- Undetermined initial values (not determinable at the window start) are treated as a distinct token, so an undetermined-vs-concrete boundary is reported as a divergence.
- Textual same-timescale or simple-magnitude (1/10/100 × fs…s) timescales normalize; exotic timescales fall back to raw-tick comparison with a warning.

## 2026-07-03 - Signal-to-RTL Source Mapping

Added deterministic mapping of hierarchical waveform signal names to candidate RTL declarations. New typed, versioned mapping report schema (`src/rtl_agent/signal_source_map_models.py`), a mapping service (`src/rtl_agent/signal_source_map/service.py`), and a `map-signals` CLI command consume an existing repository-map artifact plus signal names (given directly, or read from a waveform-slice or comparison report) and match each signal's hierarchical path components and leaf against repository-map declaration names (`module`/`interface`/`package`/`program`/`checker`, with file path and line). Each signal is classified `exact` (unambiguous scope-component match), `probable` (weaker leaf or case-insensitive match), `ambiguous` (a matched name with multiple declarations — all preserved), or `unresolved`, and every candidate carries a tiered score and an explicit match reason.

Validation evidence:

- Live run: `inspect-repo` on `examples/simple-rtl` then `map-signals --signal top.u_child.clk --signal top --signal top.foo.bar` - resolved `top.*` scope signals to `module top` at `rtl/top.sv:1` (exact) and a bare `top` leaf as probable.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 164 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change example checks, and packaging smoke verification (which now also verifies `map-signals --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Mapping consumes the existing repository-map and waveform artifacts only; it never re-scans the repository or re-parses RTL. Declaration evidence is limited to top-level declarations (modules/interfaces/packages/programs/checkers), so mapping resolves hierarchical scope components rather than internal net/reg names.
- Scoring is tiered and deterministic: scope-component exact-name matches outrank leaf and case-insensitive matches, and outer (design-root) scope components are preferred via a depth bonus, giving stable scope-based disambiguation.
- Ambiguity is never collapsed: when a matched name has multiple declarations, every candidate location is preserved and the signal is reported `ambiguous`.
- The report explains every match with a per-candidate reason string and an overall per-signal reason; nothing is silently chosen.

Known limitations:

- The repository map extracts only top-level declarations, so leaf signal names (nets/registers) generally do not resolve to a declaration; mapping targets the declaring module/scope, not the individual signal line.
- Instance names in the hierarchy are not resolved to their module types (that requires connectivity/elaboration, which is deliberately out of scope); only path components whose names coincide with declaration names resolve.
- Matching is exact or case-insensitive name matching only; no fuzzy, partial, or parameter-aware matching.

## 2026-07-03 - Static RTL Driver and Dependency Tracing

Added deterministic, bounded, explicitly-textual driver and dependency tracing for mapped signals. New typed, versioned report schema (`src/rtl_agent/rtl_driver_trace_models.py`), a tracing service (`src/rtl_agent/rtl_driver_trace/service.py`), and a `trace-drivers` CLI command consume an existing signal-source-map report plus the repository map (for `repository_root` and per-file declarations) and, for each mapped signal, scan the declaring RTL file(s) for statements referencing the signal's leaf name: continuous assignments (`assign`), procedural assignments (`<=`/`=`), and port connections. Each match records file, line, statement kind, bounded statement text, LHS and RHS identifiers, the enclosing declaration (from repository-map evidence), and the nearest conditional guard where practical. A bounded upstream dependency expansion (configurable `--max-depth` and `--max-nodes`) walks the referenced RHS identifiers, emitting edges labeled `textual` (identifier appears in a matched assignment) or `inferred_textual` (name-based port connection). Comments and string literals are masked before scanning, and Verilog sized/based literals (e.g. `1'b0`) are stripped so they do not leak spurious identifiers.

Validation evidence:

- Live run on a synthetic `dut.sv` (`assign valid = a & b;`, guarded procedural `a <= ...`): `dut.valid` resolved to the continuous assign with RHS `[a, b]`; `dut.a` preserved both procedural drivers (guards `if (!rst_n)` and `else`); dependency edges `valid->a`, `valid->b`, `a->b`, `a->valid`; `b` reported unresolved.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 177 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change example checks, and packaging smoke verification (which now also verifies `trace-drivers --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The scan is purely textual and bounded (masked comments/strings, per-file match cap, file-size cap, configurable depth/node limits); it never elaborates, preprocesses, expands generates, resolves parameters, simulates, or builds a semantic dataflow graph.
- Every edge cites source evidence (file + line + statement kind) and is labeled `textual` or `inferred_textual`; nothing is asserted as semantic or causal.
- Ambiguity is preserved: a signal with multiple drivers keeps all of them, and undriven/unknown identifiers (inputs, constants) are reported in `unresolved_identifiers` rather than silently resolved.
- The set of files scanned comes from the signal-source-map candidates, so tracing reuses the existing mapping artifact instead of re-scanning the repository.

Known limitations:

- Statement recognition is line-oriented regex matching, so assignments spanning multiple physical lines, and blocking `=` inside vs outside procedural blocks, are approximated; guards are the nearest preceding `if`/`else`/`case`/`always` line within a bounded lookback (best-effort, textual).
- Cross-module driver resolution is limited to textual port-connection matches by name; instance-to-module-type connectivity is not resolved.
- RHS identifiers are textual candidates, not proven dependencies; concatenations, function calls, and macro-expanded references are captured only as their surface identifiers.

## 2026-07-03 - Failure Divergence Graph

Added a deterministic, purely compositional failure-divergence-graph capability. New typed, versioned report schema (`src/rtl_agent/failure_divergence_graph_models.py`), a composition service (`src/rtl_agent/failure_divergence_graph/service.py`), and a `divergence-graph` CLI command consume an existing waveform-comparison report, signal-source-map report, and driver-trace report and build a bounded directed graph rooted at the diverging signals. Roots are the comparison's diverging signals mapped to their leaf identifiers (with first divergence time, values, and score attached); each node composes its mapping status and declaration location (from the signal-source map) and driver-resolution status (from the driver trace); edges are the driver-trace dependency edges, retaining their `textual`/`inferred_textual` label and citing source file and line. A bounded BFS from the roots (configurable `--max-depth`/`--max-nodes`) traverses only the existing driver-trace edge set — no new RTL scanning, VCD parsing, or recomputation.

Validation evidence:

- Live run composing real signal-source-map + driver-trace (synthetic `dut.sv`) with a comparison where `dut.valid` diverges: root `valid` (divergence attached), edges `valid->a`/`valid->b`/`a->b` with textual evidence lines, `a` resolved via mapping, `b` preserved as unresolved.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 190 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change example checks, and packaging smoke verification (which now also verifies `divergence-graph --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The graph is composed strictly from the three prior artifacts; it performs no new analysis. The BFS traverses the already-extracted driver-trace edges, so it inherits (rather than recomputes) the textual/inferred-textual evidence.
- Divergence roots are bridged to the driver-trace's leaf-identifier space via the signal-source map (hierarchical signal -> leaf); a diverging signal absent from the map falls back to its textual leaf with a warning.
- Every edge cites its source evidence (file, line, statement kind) and label; no node or edge is asserted as semantic, causal, or a root cause.
- Ambiguity and honesty are preserved: multiple diverging signals collapsing to one leaf warn and pick deterministically (earliest divergence, then name); unresolved identifiers are reported; a driver-trace produced from a different signal-source map warns about possible inconsistency.

Known limitations:

- Root bridging relies on the signal-source map's leaf; hierarchical signals sharing a leaf are collapsed to one graph root (with a warning), since the driver-trace edge space is leaf-identifier keyed.
- The graph reflects only edges the driver-trace already extracted; it neither deepens nor re-scans beyond that evidence, and inherits the driver-trace's textual approximations.
- Node divergence attributes are attached only to identifiers that are diverging-signal leaves; upstream nodes carry mapping/driver attributes but no divergence unless they are themselves diverging leaves.

## 2026-07-03 - Failure Intelligence Evidence Bundle Integration

Extended the deterministic evidence-bundle exporter so the remaining failure-intelligence artifacts under a run directory are recognized alongside the other typed reports. Added five `EvidenceArtifactKind` values (`relevant_signal_reduction_report`, `waveform_comparison_report`, `signal_source_map_report`, `rtl_driver_trace_report`, `failure_divergence_graph_report`) and five content-based classifiers in `_json_artifact_kind`, reusing the existing hashing, schema-version detection, run-relative provenance, and omitted-content rules with no changes to export flow, manifest/report schema shape, or any other artifact schema.

Validation evidence:

- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 192 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change example checks, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Classification uses distinctive top-level JSON key-sets (reduction: `retained_signals`/`reduced_slice_path`/`total_candidate_signals`; comparison: `diverging_signals`/`time_basis`/`shared_signal_count`; signal-source map: `mappings`/`exact_count`/`ambiguous_count`; driver trace: `traced_signals`/`dependency_nodes`/`dependency_edges`; divergence graph: `root_identifiers`/`nodes`/`edges`), matching the existing review/triage/verification-strength/waveform-slice/assertion-link detection style rather than inventing fixed run-relative paths these user-specified outputs do not have.
- The five key-sets are mutually disjoint and disjoint from the existing detectors (e.g. driver-trace `dependency_nodes`/`dependency_edges` vs divergence-graph `nodes`/`edges`), so ordering is irrelevant and there is no cross-classification.
- Tests construct the five reports from their real model classes and dump them under a run directory, so a future field rename surfaces as a classification-test failure.

Known limitations:

- Detection is content-based on stable top-level keys; deeply restructured future report schemas would need the key-sets updated.
- The waveform-comparison classifier keys on `time_basis`/`diverging_signals`/`shared_signal_count`; a comparison-report schema that renamed those would fall back to `other_json`.

## 2026-07-03 - Compact Failure Intelligence Example Check

Added a compact, deterministic local integration check over the real failure-intelligence services and CLI. `scripts/failure_intelligence_example_check.py` builds a run directory in a temporary workspace and chains the actual CLI end-to-end: waveform extraction (a failing slice from `examples/waveforms/failure.vcd` and a passing reference from a new `examples/waveforms/passing.vcd`), relevant-signal reduction, passing/failing comparison, repository discovery on `examples/simple-rtl`, signal-source mapping of the compared signals, static driver tracing, failure-divergence graph composition, and evidence-bundle export. It validates every emitted artifact through the existing typed models and reuses the shared `scripts/_example_check.py` helper; it is registered in `scripts/check.py`.

Validation evidence:

- `python3 scripts/failure_intelligence_example_check.py` - passed.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 192 pytest tests, agent portability check, compact end-to-end/failure/tool-failure/no-change/failure-intelligence example checks, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The check drives the real CLI commands over checked-in fixtures (no parallel implementation path) and asserts stable semantic properties — schema versions, the diverging-signal set `{top.dut.state, top.dut.valid}`, the identical signals, the global earliest divergence tick (25), `exact` source mappings to `rtl/top.sv`, `top.clk`'s port-connection driver evidence, the graph roots `[state, valid]` with composed divergence/mapping attributes, and the evidence-bundle artifact kinds — rather than timestamps, UUIDs, durations, absolute paths, or exact hashes.
- A compact `examples/waveforms/passing.vcd` fixture (identical declarations and clk/data timelines to the failing fixture, but with `valid` held high and `state` held at `0011`) was added so the comparison deterministically diverges on `valid` and `state` with `x`/`z` differences.
- The check writes each pipeline artifact under a `RunStore` run directory so the final `export-evidence` exercises the stage-27 failure-intelligence artifact classification as part of the same flow.

Known limitations:

- The example RTL (`examples/simple-rtl`) does not assign the waveform-only signals, so driver tracing honestly reports `no_drivers` for the diverging signals and the divergence graph has no dependency edges; the check validates composition and honest unresolved reporting, not a richly connected graph.
- It is a compact deterministic smoke of the pipeline, not an exhaustive matrix over every command option.

## 2026-07-03 - Compact Failure Report Synthesis

Added a deterministic, purely compositional failure-report synthesis capability. New typed, versioned report schema (`src/rtl_agent/failure_report_models.py`), a synthesis service (`src/rtl_agent/failure_report/service.py`), and a `synthesize-failure-report` CLI command consume an existing failure-divergence-graph report (required) plus optional relevant-signal reduction, driver-trace, verification-strength, and review reports, and emit both a typed JSON report and a concise engineer-facing Markdown summary. The report cleanly separates observed failure facts, earliest waveform divergence, ranked relevant signals, candidate RTL source locations, textual driver/dependency evidence, unresolved and ambiguous evidence, verification/review status, and artifact provenance (paths, schema versions, SHA-256 hashes). Every statement cites its originating artifact via a `source` field, and the report never labels a signal or RTL statement as a root cause.

Validation evidence:

- Live run composing real pipeline artifacts (extract → compare → inspect → map → trace → divergence-graph → reduce → synthesize): observed facts for `top.dut.state`/`top.dut.valid` at t=25 with x/z differences, ranked signals from reduction, `exact` source locations at `rtl/top.sv:1`, unresolved `state`/`valid`, and provenance for all five upstream artifacts; both JSON and Markdown emitted.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 204 pytest tests, agent portability check, all five example checks, and packaging smoke verification (which now also verifies `synthesize-failure-report --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The failure-divergence-graph report is the spine (it already composes comparison + signal-source map + driver trace), so the synthesis reads facts from it and cites them, rather than recomputing divergences, mappings, or drivers.
- Optional inputs enrich specific sections only: reduction → ranked relevant signals; driver-trace → statement text/guard enrichment of the graph's dependency edges; verification-strength → verification status; review → review status. Absent inputs leave their sections empty/none, reported honestly.
- Provenance lists every loaded input plus the graph's cited upstream paths (comparison, signal-source map, driver trace), deduped by resolved path, each with schema version and SHA-256 following the evidence-bundle convention.
- Both a typed JSON report and a Markdown summary are emitted; the Markdown carries an explicit "never identifies a root cause" disclaimer and every line cites its source artifact.

Known limitations:

- Ambiguity is surfaced from the graph node `mapping_status == "ambiguous"`; the full ambiguous candidate list lives in the signal-source-map report and is referenced by provenance rather than re-expanded here.
- Driver/dependency evidence is drawn from the graph's dependency edges (optionally enriched with driver-trace statement text); when the graph has no edges, the section is honestly empty.
- The report composes only supplied artifacts; it performs no new waveform, dependency, or semantic analysis and makes no causal claims.

## 2026-07-03 - Failure Intelligence Run Orchestration

Added one bounded, deterministic orchestrator that invokes the existing failure-intelligence stages in a fixed sequence and writes all artifacts under a single `RunStore` run directory, without duplicating any stage. New typed, versioned run-manifest schema (`src/rtl_agent/failure_intelligence_run_models.py`), an orchestration service (`src/rtl_agent/failure_intelligence_run/service.py`), and a `run-failure-intelligence` CLI command run: failing/passing waveform extraction → comparison → repository discovery → signal-source mapping → driver tracing → divergence-graph composition → relevant-signal reduction → failure-report synthesis (JSON + Markdown). Each stage reuses its existing service function directly (no subprocesses, no reimplementation). The manifest records per-stage status, inputs, outputs, duration, warnings, and failure reason, and links every generated artifact; run events are appended per stage.

Validation evidence:

- Live success run over the checked-in fixtures: 9 stages completed, 11 artifacts under the run directory, final JSON + Markdown report produced, manifest written.
- Live failure run (malformed passing VCD): `extract-passing` failed, the run stopped, the completed `extract-failing` slice was preserved, the manifest recorded the failing stage, and the CLI exited 1.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 213 pytest tests, agent portability check, all five example checks, and packaging smoke verification (which now also verifies `run-failure-intelligence --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The orchestrator is a thin sequencer: a generic `one(...)` helper writes each stage's report with its concrete writer, and dedicated actions handle the two-artifact reduce and synthesize stages; a `run_stage` wrapper times each stage, records status/warnings, appends a run event, and raises an internal `_StageFailed` to stop the sequence honestly.
- Terminal errors stop the run but always write the manifest; completed intermediate artifacts remain on disk, so a failed run is still inspectable.
- Optional stages exist only where the underlying inputs are genuinely optional: `--verification-strength` and `--review` flow through to report synthesis; the pipeline-produced inputs (reduction, driver-trace) are always present.
- Determinism: stage artifact contents depend only on their inputs; the manifest's run id, timestamp, and per-stage durations are the only volatile fields. Tests assert byte-identical `failing-slice.json` and `reduced-slice.json` across two runs.

Known limitations:

- The manifest records wall-clock stage durations, so it is not byte-identical across runs; determinism is asserted on the stage artifacts, not the manifest.
- Comparison, mapping, graph, and report artifacts embed absolute run-directory input paths, so those specific files are not byte-identical across differently-named run directories even though their semantic content is stable.
- The orchestrator exposes only the bounded window options (`--failure-time`/`--before`/`--after`) plus the optional passthrough inputs; per-stage tuning knobs use the existing service defaults.

## 2026-07-03 - Failure Intelligence Run Resume and Replay

Extended the existing run orchestration (no second execution path) with deterministic, manifest-driven resume and replay. The `run-failure-intelligence` command gained `--resume` (reuse valid existing stage artifacts and run only the remaining or invalid stages) and `--replay-from <stage>` (regenerate from an explicitly named stage onward). Before reusing any artifact the run verifies its existence, its recorded SHA-256, its typed model and supported schema version, and that the prior run's inputs (VCDs, repository root, failure window) match the current inputs; a missing, stale, incompatible, or unprovenanced artifact is regenerated rather than trusted, and regenerating any stage invalidates and regenerates the downstream stages. The run manifest schema was bumped to version 2: each stage now records a `disposition` (executed / reused / regenerated / skipped / failed) and each artifact records its SHA-256; skipped stages after a failure are recorded explicitly, and a run event explains every reuse or invalidation decision.

Validation evidence:

- Live runs: fresh (all executed) → `--resume` (all reused) → `--replay-from trace-drivers` (earlier reused, trace-drivers onward regenerated) → corrupt an intermediate artifact then `--resume` (regenerated from the first invalid stage with downstream cascade) → `--replay-from bogus` (clear error, exit 2).
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 220 pytest tests, agent portability check, all five example checks, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The orchestrator was refactored into a declarative list of stages (name, inputs, typed outputs, action) so resume/replay iterate the same fixed sequence used by a fresh run; there is one execution path, not two.
- Reuse validation is layered exactly as required: existence → recorded SHA-256 → typed-model validation → supported schema version → run-input match; the run-level input match enforces upstream-input consistency, and any failed check triggers regeneration.
- Downstream invalidation is conservative in the linear pipeline: once any stage regenerates, every subsequent stage regenerates (and its stale output is deleted before re-running), which is deterministic and avoids introducing a dependency scheduler.
- Terminal errors still stop the run, preserve completed artifacts, record the failing stage, and mark the remaining stages `skipped`; the manifest is always written.

Known limitations:

- The linear-pipeline cascade regenerates all stages after the first changed stage even when a later stage is not data-dependent on it; this is safe and deterministic but may recompute more than a dependency-aware scheduler would (deliberately out of scope).
- Reuse trusts the prior manifest's recorded SHA-256 and run inputs; it does not re-derive provenance from artifact contents beyond typed-model and schema-version validation.
- Unsupported prior-manifest schema versions are ignored (treated as no prior manifest) rather than migrated, matching the no-automatic-migration exclusion.

## 2026-07-03 - Failure Intelligence Run Portability and Relative Provenance

Made the failure-intelligence run directory portable, reusing the existing orchestration and run manifest. Stage inputs and outputs are now recorded as typed `PathRef`s carrying a `kind` of `run_relative` (a POSIX path under the run directory) or `external` (an absolute path outside it), and the manifest records the external run inputs explicitly (`external_inputs`: failing VCD, passing VCD, repository root, and any verification/review reports) with their absolute paths and existence at write time. Run-relative artifact references are resolved against the current run directory, so a moved or copied run directory remains inspectable and can be resumed or replayed from its new location while hashes and typed-model validation are still enforced. A new `resolve_run_relative` helper rejects absolute paths, `..` traversal, and any path escaping the run directory; recorded artifact paths that escape the run directory are ignored (their stage regenerates) with a warning. Missing external inputs are recorded and warned about and are never silently reinterpreted — a stage that needs a missing external input fails honestly. The run-manifest schema was bumped to version 3; prior manifests at versions 2 and 3 are both accepted for reuse (no migration framework), since the fields consulted for reuse are stable across them.

Validation evidence:

- Live runs: copy a completed run to a new location and `--resume` (all reused); `--replay-from divergence-graph` after relocation (earlier reused, from-stage regenerated); corrupt an artifact after moving then `--resume` (sha256-mismatch regeneration with downstream cascade); tamper a recorded path to `../escape.json` (ignored-unsafe warning, stage regenerated, nothing written outside the run dir); missing external VCD (external `exists=false`, warning, `extract-failing` failed honestly, run status failed).
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 228 pytest tests, agent portability check, all five example checks, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Relocation resume already worked because artifact validation keys on run-relative `relative_path` + recorded SHA-256; this milestone made provenance explicit (path kinds, external-input records) and added an explicit safe-resolution boundary rather than changing the reuse mechanism.
- The top-level `failing_vcd`/`passing_vcd`/`repository_root` Path fields were kept (alongside the new `external_inputs`) so the input-match gate and v2 manifest reuse keep working without a migration layer.
- Path-traversal defense is centralized in `resolve_run_relative`/`_is_safe_run_relative`; recorded artifact paths are filtered through the safe check during prior-manifest indexing, so an unsafe path can never be resolved to the filesystem and simply forces regeneration.

Known limitations:

- The manifest's `run_dir` field still records the write-time absolute location (informational); resume re-derives the actual run directory from the run store, and a future inspection command should resolve artifacts against the manifest's real location rather than the recorded `run_dir`.
- External-input consistency across relocation is matched on the recorded absolute external paths; if an external input is itself moved, it must be re-supplied (by design, since external inputs live outside the run).
- Only manifest schema versions 2 and 3 are accepted for reuse; older or newer versions are treated as no prior manifest, not migrated.

## 2026-07-03 - Failure Intelligence Run Inspection and Validation

Added a read-only `inspect-run` command that validates an existing run directory against its manifest without re-running any stage, reusing the existing manifest, typed artifact models, hashing (`sha256_file`), schema-version detection (`schema_version_of`), external-input records, and safe run-relative path resolution (`resolve_run_relative`, promoted from the run service). A new typed, versioned inspection report (`src/rtl_agent/run_inspection_models.py`) and service (`src/rtl_agent/run_inspection/service.py`) classify each recorded artifact as `valid`, `missing`, `hash_mismatch`, `schema_malformed`, `schema_unsupported`, or `unsafe_path`; each stage as `valid`, `incomplete`, `stale`, or `invalid`; re-check whether recorded external inputs still exist; and compute overall run validity. Run-relative artifacts are resolved against the actual inspected directory (rejecting `..`/absolute/escaping paths), so a moved or copied run inspects correctly. The CLI prints a concise summary, optionally writes the full JSON report with `--output`, exits non-zero on an invalid run (still writing the report), and exits 2 on an unreadable/absent manifest.

Validation evidence:

- Live: valid run (all valid, exit 0); corrupted artifact (hash_mismatch → stage invalid, downstream stale, exit 1); moved run (still valid); tampered `../escape.json` recorded path (unsafe_path, warning, exit 1, no file written outside the run); unsupported manifest version 99 (invalid + warning); missing manifest (exit 2).
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 244 pytest tests, agent portability check, all five example checks, and packaging smoke verification (which now also verifies `inspect-run --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Inspection is strictly read-only: it never resolves an unsafe recorded path to the filesystem, never writes into the run directory, and a dedicated test snapshots the run directory's file bytes before and after to prove it is unchanged.
- The service reads the manifest defensively as raw JSON and accepts manifest schema versions 2 and 3 (the fields consulted are stable); an unsupported version yields an explicit invalid report rather than an error, while an absent or unparseable manifest raises `RunInspectionError` (CLI exit 2).
- Overall run validity requires a completed manifest status with all stages valid and no missing/invalid artifacts; missing external inputs are reported separately (they live outside the run) and do not, by themselves, flip artifact validity.
- Staleness is derived deterministically in manifest stage order: once any stage is invalid or incomplete, later stages whose own outputs are valid are marked `stale`, mirroring the orchestrator's linear cascade.

Known limitations:

- Inspection trusts the manifest's recorded artifact list; artifacts present on disk but not recorded in the manifest are not inspected.
- Overall validity is computed for a completed run; a legitimately failed run is reported invalid (it did not produce a complete artifact set), which is correct but means "invalid" spans both corruption and honest terminal failure.
- Only artifact kinds known to the inspection registry get typed-model validation; unknown kinds are validated by existence and hash only.

## 2026-07-04 - Portable Failure Package Export

Added a read-only, inspection-gated `export-failure-package` command that packages a validated run directory into a single self-contained portable directory package, reusing the existing run inspection, hashing (`sha256_file`), safe run-relative path resolution, and manifest models. A new typed, versioned package manifest schema (`src/rtl_agent/failure_package_models.py`) and export service (`src/rtl_agent/failure_package/service.py`) run `inspect_run`, refuse an invalid run by default, and (only with `--allow-failed`) export a failed-but-internally-consistent run clearly marked `failed`. The package contains the run manifest, the freshly written inspection report, the JSON and Markdown failure report, and every validated, manifest-referenced evidence artifact at its run-relative path under `run/`; external inputs, run-store event logs (`events.jsonl`, `run.json`), caches, and unrelated files are never included, and unsafe or missing artifacts are never packaged. The package manifest records each file's package-relative path, source role, size, SHA-256, schema version where applicable, and original run-relative provenance; the completed package is verified (each packaged file's hash recomputed and compared) before success is reported.

Validation evidence:

- Live: valid run → 13-file package (`package-manifest.json`, `inspection-report.json`, `run/run-manifest.json`, all 10 artifacts including the failure report JSON/Markdown), `package_status=valid`, `verified=true`; corrupted artifact → refused (exit 2, no package); a run with `status` set to failed → refused without the flag, exported as `failed` with `--allow-failed`; tampered `../escape.json` path → refused; non-empty or inside-run output → refused.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 258 pytest tests, agent portability check, all five example checks, and packaging smoke verification (which now also verifies `export-failure-package --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Export is strictly inspection-gated and read-only: it packages only artifacts that `inspect_run` marked `valid`, resolves each via the shared safe resolver (rejecting traversal), and never writes into or mutates the source run.
- The gate distinguishes an invalid run (missing/invalid/unsafe artifacts → always refused) from a failed-but-internally-consistent run (`manifest_status == "failed"` with all recorded artifacts valid → exported only with `--allow-failed`, marked `failed`).
- Only manifest-referenced artifacts plus the run manifest and generated inspection report are packaged, so run-store bookkeeping, external inputs, caches, and unrelated files are excluded by construction.
- The package is deterministic (sorted file ordering, sorted JSON, no timestamps in the package manifest), so exporting the same run twice yields byte-identical `package-manifest.json` and artifact bytes.

Known limitations:

- Only a directory package is supported in this milestone (no archive, signing, or encryption, by exclusion).
- A failed run that produced no artifacts still exports (under `--allow-failed`) as a minimal package of just the run manifest and inspection report, marked `failed`.
- Verification recomputes hashes of the just-written package files against the validated source hashes; it does not independently re-validate typed models a second time (that already happened during inspection).

## 2026-07-04 - AXI Router Seeded-Failure Validation

Validated the existing failure-intelligence pipeline end-to-end against a compact but realistic AXI-stream-router failure, with no new product behavior. Added a checked-in fixture (`examples/axi-stream-router/` with `rtl/axi_stream_router.sv`, a passing VCD, a seeded failing VCD, and `examples/axi-stream-router-agent.yaml`) whose RTL drives real internal signals with continuous and procedural assignments, so static driver tracing has genuine evidence to cite. The seeded bug is payload instability under backpressure: the locked `payload_out` goes to `x` at t=40 in the failing VCD while the passing reference holds it stable, and the state register diverges strictly later at t=50. A new scripted check (`scripts/axi_router_seeded_failure_check.py`, registered in `scripts/check.py`) drives the real orchestrator (`run-failure-intelligence`) plus `inspect-run` and `export-failure-package` over the fixtures in a temporary workspace and asserts, against the typed schemas, that the pipeline: identifies `payload_out` as the earliest divergence at t=40; ranks the protocol/state signals; maps `payload_out` exactly to the `axi_stream_router` module in `rtl/axi_stream_router.sv`; extracts the real `assign payload_out = payload_reg;` continuous-assignment driver and a connected `payload_out → payload_reg → payload_in` dependency chain with cited file/line edges; produces a connected divergence graph rooted at the divergent signal; surfaces the source location and textual driver evidence in the synthesized JSON and Markdown failure report; exports and validates a portable failure package; and preserves ambiguity (module inputs and localparams left unresolved) while making no causal or root-cause claim.

Validation evidence:

- The new check reads only stable, schema-backed values (divergent-signal set and times, mapped module/file, driver statement text and cited lines, graph roots/edges, report fields, inspection validity, package verification) — never timestamps, hashes, durations, UUIDs, or absolute paths.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 258 pytest tests, agent portability check, all six example checks (including the new AXI router check), and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The check drives the existing orchestrator and CLI only; no product service was changed, no expected answer was hard-coded into a service, and no parallel analysis path was introduced. The fixture RTL is what makes driver tracing produce real evidence — unlike the earlier `simple-rtl` fixture whose signals were undriven (`no_drivers`).
- The seeded divergence was designed so signals are identical at the window start (t=25) and diverge later, giving a deterministic earliest-divergence signal (`payload_out` at t=40) distinct from the later state divergence (t=50); this was confirmed by running the real pipeline and reading its actual outputs before codifying assertions.
- Clock and reset live under a `tb` scope with no matching module declaration, so they remain unmapped and identical — realistic testbench context that the pipeline correctly leaves out of the RTL localization.

Known limitations:

- The fixture is a single-file compact RTL fragment; it exercises intra-file driver tracing and dependency expansion but not cross-file or multi-module hierarchy resolution.
- The check asserts the seeded signal is localized with cited evidence; it deliberately does not assert an exhaustive edge/node count, so the fixture can grow without churn as long as the seeded localization holds.
- The waveforms are hand-authored VCDs, not simulator output, consistent with the no-simulator exclusion.

## 2026-07-04 - Real AXI Router Repository Pilot

Validated that the existing failure-intelligence architecture scales to hierarchical, multi-file RTL, with no new analysis behaviour, heuristics, AXI-specific logic, or parallel path. Added a compact multi-file repository (`examples/axi-router-repo/` with `rtl/axi_router.sv`, `rtl/axi_ingress.sv`, `rtl/axi_route.sv`, a passing VCD, a seeded failing VCD, and `examples/axi-router-repo-agent.yaml`): a top module `axi_router` instantiates two child modules — `axi_ingress` (drives `payload_staged` from `payload_in`) and `axi_route` (drives `payload_out` from the cross-module `payload_staged`) — from separate files, wiring the staged payload across the module boundary. The seeded fault corrupts `payload_staged` in the ingress under backpressure at t=40 and propagates to `payload_out` in the route at t=50. A new scripted check (`scripts/axi_router_repository_pilot_check.py`, registered in `scripts/check.py`) drives the real orchestrator plus `inspect-run` and `export-failure-package` and asserts, against the typed schemas, that the pipeline: recognizes three modules across three files; identifies `payload_staged` as the earliest divergence at t=40; maps `payload_staged` to `axi_ingress.sv` and `payload_out` to `axi_route.sv` (cross-file source mapping to the correct child modules); reconstructs the `payload_out → payload_staged → payload_in` chain with its two links cited to two different files (`axi_route.sv` and `axi_ingress.sv`) — genuine cross-module driver/dependency tracing; produces a divergence graph whose two roots localize to two child files and whose edges connect across them; cites both child source files in the synthesized failure report; exports and validates a portable failure package; and preserves ambiguity (module inputs unresolved) with no root-cause claim.

Validation evidence:

- Confirmed the cross-file behaviour by running the real pipeline and reading its actual outputs before codifying assertions: `payload_staged`→`rtl/axi_ingress.sv`, `payload_out`→`rtl/axi_route.sv`, dependency edges `payload_out→payload_staged @ axi_route.sv:18` and `payload_staged→payload_in @ axi_ingress.sv:26`.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 258 pytest tests, agent portability check, all seven example checks (including the new repository pilot check), and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- No product code changed: the check drives only the existing orchestrator and CLI. Cross-file behaviour is an emergent property of the existing services — the driver trace scans the union of all traced signals' declaring files, so when two signals map to two child files the dependency expansion naturally reconstructs edges across them.
- The VCD hierarchy names the two child instance scopes to match the child module names (`axi_ingress`, `axi_route`) under a non-module `dut` instance scope, so each signal resolves to its own child file rather than collapsing to the shallower top module; this is what forces the existing mapping to exercise cross-file resolution. The top module remains in the repository (indexed by discovery) to establish the instantiating hierarchy.
- The seeded fault is physically consistent with the RTL text (staged payload corrupts first in the ingress, then the routed output that continuously assigns from it), so the earliest-divergence signal and the cross-module chain agree.

Known limitations:

- The hierarchy is two levels deep with two children; deeper or wider trees and same-named signals across unrelated modules are not exercised here.
- Cross-file dependency reconstruction relies on both endpoints being among the traced signals' declaring files (the union scanned by the existing driver trace); a dependency whose driver lives in a file no observed signal maps to is still left unresolved, by design.
- Waveforms are hand-authored VCDs, not simulator output, consistent with the no-simulator exclusion.

## 2026-07-04 - Cross-Module Ambiguity and Multi-Instance Robustness Pilot

Validated that the existing pipeline handles genuinely ambiguous hierarchical RTL honestly — preserving multiple candidates and explicitly reporting ambiguity rather than a false-confident single answer — with no new analysis behaviour, heuristics, or disambiguation logic. Added a compact ambiguity fixture (`examples/axi-router-ambiguity/` with `rtl/lane_rtl.sv`, `rtl/lane_shadow.sv`, `rtl/top.sv`, a passing VCD, a seeded failing VCD, and `examples/axi-router-ambiguity-agent.yaml`): the child module `lane` is defined in two separate files and instantiated more than once by `top`, so the internal signal names (`data_out`, `data_hold`) are non-unique across files. The seeded fault drives both signals to `x` at t=40 under an instance scope (`tb.dut.lane`) whose source therefore matches two declarations. A new scripted check (`scripts/axi_router_ambiguity_pilot_check.py`, registered in `scripts/check.py`) drives the real orchestrator plus `inspect-run` and `export-failure-package` and asserts, against the typed schemas, that the pipeline: records `lane` as a duplicate declaration across both files and as an instantiated type; identifies the earliest divergence at t=40; reports the divergent signal's source mapping as `ambiguous` with both candidate files preserved; keeps driver evidence and dependency edges from both files (not collapsed to one); carries `mapping_status = ambiguous` with both declarations onto the divergence-graph root node; cites both candidate source locations and records explicit `ambiguous_evidence` in the synthesized JSON and Markdown failure report; exports and validates a portable failure package; and makes no root-cause claim.

Validation evidence:

- Confirmed the behaviour by running the real pipeline and reading its actual outputs before codifying assertions: signal map `ambiguous_count = 2` with `data_out`/`data_hold` each carrying both `rtl/lane_rtl.sv` and `rtl/lane_shadow.sv` candidates; driver trace with drivers and dependency edges in both files; failure report `candidate_source_locations` listing both files and `ambiguous_evidence` naming both signals.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 258 pytest tests, agent portability check, all eight example checks (including the new ambiguity pilot), and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- No product code changed and no disambiguation heuristic was added: the ambiguity is an emergent, correct property of the existing services. The signal-source map classifies a mapping as `ambiguous` when the top-scoring path component matches multiple distinct declarations (here, the duplicated `module lane`), and the driver trace scans all candidate/declaring files, so evidence from both files is naturally preserved rather than collapsed.
- The genuine ambiguity is produced by a duplicate module declaration (`module lane` in two files), which is what the existing declaration-based mapping can legitimately detect; repeated instantiation in `top.sv` and the non-unique internal signal names reinforce the scenario. Instance-only ambiguity (two instances of one module) maps unambiguously to that one module's source, which is correct, so it is not what drives the reported ambiguity.
- The observed instance scope is named `lane` under a non-module `dut` scope so the ambiguous child match is the top-scoring component; a matching top-level scope would otherwise resolve to a single shallower module.

Known limitations:

- The ambiguity demonstrated is duplicate-module-declaration ambiguity; case-insensitive/probable near-matches and cross-scope collisions are not separately exercised here.
- Both `lane` definitions share identical port and internal signal names by design; a partial overlap (some names shared, some not) is not exercised.
- Waveforms are hand-authored VCDs, not simulator output, consistent with the no-simulator exclusion.

## 2026-07-04 - Simulator-Generated AXI Failure Pilot

Replaced hand-authored waveforms, for one pilot, with genuinely simulator-generated ones, proving the existing pipeline works on real tool output without adding any new analysis behaviour or a product runtime dependency. Added a compact simulatable design and testbench (`examples/axi-router-sim/rtl/axi_pipe.sv`, `examples/axi-router-sim/tb/axi_pipe_tb.sv`, and `examples/axi-router-sim-agent.yaml`): `axi_pipe` captures a payload under a lock and must hold it stable under backpressure; the seeded fault is a compile-time define (`INJECT_FAULT`) that corrupts the held payload to `x` under backpressure. A new gated check (`scripts/axi_router_simulated_failure_check.py`, registered in `scripts/check.py`) detects Icarus Verilog (`iverilog`/`vvp`); when present it compiles the design + testbench twice from the same stimulus (clean and `-DINJECT_FAULT`), runs each with `vvp +vcd=<path>` to emit a real passing-vs-failing VCD pair, and drives the existing pipeline (`run-failure-intelligence` plus `inspect-run` and `export-failure-package`) over the generated VCDs. It asserts, against the typed schemas, that the two runs differ; the earliest divergence is `payload_reg`/`payload_out` at t=45 with an x/z difference; those signals map exactly to `axi_pipe.sv` (module `axi_pipe`); the driver trace recovers the real `assign payload_out = payload_reg;` and `payload_reg <= payload_in;` statements and the `payload_out → payload_reg` dependency edge; the failure report localizes to `axi_pipe.sv` and claims no root cause; and inspection and portable-package export succeed. When the simulator is not on `PATH` the check prints a skip notice and returns success, so `scripts/check.py` stays hermetic and green.

Validation evidence:

- Confirmed the simulator path by generating both VCDs with `iverilog -g2012` (+ `-DINJECT_FAULT`) and `vvp`, then reading the pipeline outputs before codifying assertions: the failing VCD adds `bx` value changes on `payload_reg`/`payload_out` at t=45; the comparison, mapping, driver trace, and failure report localize to `axi_pipe.sv`.
- Confirmed the skip path by running the check with an empty `PATH`: it printed "skipped (iverilog/vvp not available)" and returned 0.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 258 pytest tests, agent portability check, all nine example checks (the simulator check ran because Icarus Verilog is installed locally), and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The simulator is a gated fixture-generation/dev tool, detected with `shutil.which` and skipped cleanly when absent; it is never added to the product's install or runtime dependencies, and the gating lives inside the check script so `scripts/check.py` needs no conditional wiring and stays hermetic.
- The seeded fault is a compile-time define rather than a testbench force, so the same deterministic stimulus produces a genuine passing-vs-failing pair that differs only where the bug manifests; no randomness is used.
- The testbench module is kept out of the inspected RTL repository (the pipeline's `--repo` points at `examples/axi-router-sim/rtl`), so signal-source mapping resolves the DUT scope to the `axi_pipe` module rather than to the testbench top; the DUT instance is named `axi_pipe` so the dump hierarchy exposes a matching scope.
- No product code changed; the check drives only the existing orchestrator and CLI, and all assertions are on stable schema values (times, signal names, file paths, statement text), not timestamps or hashes from the VCD header.

Known limitations:

- Only Icarus Verilog is wired as the generator; Verilator (also installed on some machines) is not used here, and the VCD timescale reflects the simulator default (`1s`) since the fixture omits an explicit `timescale.
- The generated pilot is single-module; combining simulator generation with the multi-file/ambiguity fixtures is left to a future milestone.
- The check compiles and runs a real toolchain, so it is slower than the hand-authored checks and depends on the locally installed simulator version behaving as Icarus Verilog 13 does.

## 2026-07-04 - Simulator-Generated Multi-Module Failure Pilot

Combined the two validated threads — simulator-generated waveforms and hierarchical multi-file RTL — into one pilot, proving the existing pipeline localizes a real, cross-module, simulator-generated failure without any new analysis behaviour. Added a hierarchical simulatable design (`examples/axi-router-sim-hier/` with `rtl/ingress.sv`, `rtl/route.sv`, `rtl/top.sv`, `tb/top_tb.sv`, and `examples/axi-router-sim-hier-agent.yaml`): the top module instantiates the `ingress` and `route` child modules from separate files and wires a staged payload across the boundary. The compile-time seeded fault (`INJECT_FAULT`, in the ingress child) corrupts the staged payload to `x` under backpressure; the route child registers that cross-module signal one cycle later, so the fault originates in one child and propagates into another child's observable output. A new gated check (`scripts/axi_router_simulated_multimodule_check.py`, registered in `scripts/check.py`) detects Icarus Verilog and, when present, compiles the three RTL files + testbench twice from the same stimulus (clean and `-DINJECT_FAULT`), runs each to emit a real passing-vs-failing VCD pair, and drives the existing pipeline (`run-failure-intelligence` plus `inspect-run` and `export-failure-package`) over the generated VCDs. It asserts, against the typed schemas: the earliest divergence is `payload_staged` at t=45 and the routed `payload_out` follows at t=55, both x/z; `payload_staged` maps exactly to `ingress.sv` and `payload_out` exactly to `route.sv`; both continuous and procedural driver forms are recovered; the routed output's `payload_out <= payload_staged;` register driver is cited in `route.sv`; the cross-module dependency chain `payload_out → payload_staged → data_in` is cited across `route.sv` and `ingress.sv`; the divergence graph roots localize across the two files with cited source edges; the synthesized JSON and Markdown report cite both child files; run inspection is valid; the portable package export is verified; and no root cause is claimed. When the simulator is not on `PATH` the check skips cleanly and returns success.

Validation evidence:

- Generated both VCDs with `iverilog -g2012` (+ `-DINJECT_FAULT`) and `vvp`, read the pipeline outputs, then codified stable assertions: comparison earliest 45 (`payload_staged`) with `payload_out` at 55; mapping `payload_staged`→`ingress.sv`, `payload_out`→`route.sv`; dependency edges `payload_out→payload_staged @ route.sv` and `payload_staged→data_in @ ingress.sv`.
- Verified the skip path with an empty `PATH`: "skipped (iverilog/vvp not available)", rc=0.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 258 pytest tests, agent portability check, all ten example checks (both simulator checks ran because Icarus Verilog is installed), and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- No product code changed; the check drives only the existing orchestrator and CLI, and all assertions are on stable schema values (times, signal names, file paths, statement text).
- The testbench dumps only the two child scopes (`$dumpvars(1, dut.ingress)` and `$dumpvars(1, dut.route)`) rather than the whole testbench, so each observed signal resolves to exactly one child module; dumping the full hierarchy had also emitted redundant top/testbench-level copies of `payload_out` that pulled its aggregated graph-node mapping status to `unresolved`.
- The child instances are named after their modules (`ingress`, `route`) and the top instance is named `dut` (a non-module scope), with the testbench kept out of the inspected repo (`--repo` → `.../rtl`), so cross-file mapping resolves each signal to its child file rather than to a shallower ancestor or the testbench.
- The route child registers the cross-module staged payload (procedural) so the fault propagates across a cycle boundary, giving a genuine one-cycle-later divergence on `payload_out` rather than a same-timestep continuous copy.

Known limitations:

- `payload_staged` is the boundary net and is dumped under both the ingress (output) and route (input) scopes, so its aggregated graph node carries declarations from both files; this is faithful to the wiring but means the boundary signal is not single-file.
- Only Icarus Verilog is wired; Verilator is not used, and the VCD timescale is the iverilog default (`1s`) since the fixtures omit an explicit `timescale.
- The check compiles and runs a real toolchain, so it is slower than the hand-authored checks and depends on the locally installed simulator version.

## 2026-07-04 - Simulator Failure Triage Integration Pilot

Wired real simulator logs and assertion evidence into the existing failure-intelligence orchestration end to end, reusing the command runner, triage, assertion-to-waveform linking, waveform extraction, and run services rather than adding a parallel pipeline. Added a simulatable fixture (`examples/axi-router-sim-triage/rtl/axi_pipe.sv`, `tb/axi_pipe_tb.sv`, and `examples/axi-router-sim-triage-agent.yaml`) with an explicit `` `timescale 1ns/1ns `` so log timestamps and VCD ticks share ns units: the testbench dumps a VCD, and on the compile-time-seeded fault (`INJECT_FAULT`) it emits a stable marker `assertion payload_stable failed at time=45 ns` when the observable payload goes unknown, then terminates the run with a non-zero status (`$fatal`) after the full waveform is written. A new gated check (`scripts/axi_router_simulated_triage_check.py`, registered in `scripts/check.py`) detects Icarus Verilog and, when present: compiles the clean and faulted builds and generates the passing reference VCD directly; runs the failing simulation through the existing command runner (`run-command`, which records it as `failed` with exit code 1 and captures its stdout/stderr and the dumped VCD); triages the captured result with `triage-command` (recovering the `payload_stable` assertion at `45 ns` and the referenced `cmd_failure.vcd`); links the finding with `link-assertion-waveform`, which derives the failure timestamp (`45 ns` → tick 45, exact, using the VCD timescale) and selects the failing VCD — the user provides neither the failure time nor the waveform path; and drives the existing `run-failure-intelligence` orchestration over the derived failing VCD and timestamp plus the passing reference. It asserts the divergence is localized to `axi_pipe.sv` at t=45, that the triaged failure and the localized divergence describe one run (the linked VCD is the one the run consumed and the comparison's earliest divergence equals the derived assertion tick), and that run inspection is valid and the portable-package export is verified. When the simulator is absent the check skips cleanly and returns success.

Validation evidence:

- Confirmed the whole chain manually before codifying assertions: `run-command` → status `failed`, exit 1; `triage-command` → assertion `payload_stable` / `45 ns`, waveform `cmd_failure.vcd` (exists); `link-assertion-waveform` → `failure_timestamp_ticks=45`, `exact=true`, selected `cmd_failure.vcd`; `run-failure-intelligence` → earliest divergence 45 on `payload_out`/`payload_reg`, exact mapping and report citing `axi_pipe.sv`, no root-cause claim; inspection valid; package verified.
- Verified the skip path with an empty `PATH`: "skipped (iverilog/vvp not available)", rc=0.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 258 pytest tests, agent portability check, all eleven example checks (all three simulator checks ran because Icarus Verilog is installed), and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- No product code changed and no simulator-specific logic was added to any general analysis service; the check composes existing CLI commands only (`run-command`, `triage-command`, `link-assertion-waveform`, `run-failure-intelligence`, `inspect-run`, `export-failure-package`).
- The failure timestamp and failing-waveform path are derived from the triaged assertion and its waveform reference through the existing linker, satisfying the "no manual timestamp/path" requirement; only the assertion *finding index* (`--assertion-index 0`) is selected, which chooses which finding, not the time or path.
- The testbench emits the assertion marker on the value-change of the observable payload (so the timestamp is the divergence time, t=45, not a clock-sample cycle later) and defers `$fatal` to the end of the stimulus so the full VCD is written before the terminal failure; the passing build never trips the marker and exits zero.
- An explicit `` `timescale 1ns/1ns `` makes the assertion's `ns` units convert exactly against the VCD timescale (the linker requires an explicit unit and fails rather than guessing), so the derived tick is exact.
- The failing run is executed through the command runner via a workspace-local config whose command invokes `vvp` on the pre-compiled binary; compilation and the passing reference are fixture prep, consistent with the earlier simulator pilots.

Known limitations:

- Terminal-failure capture relies on `$fatal` yielding a non-zero `vvp` exit; a simulator that reported failures differently (e.g. only via a log string) would need a different marker convention, though triage would still recover the textual assertion.
- The pilot is single-module; it exercises the triage/assertion/link integration rather than cross-module localization (covered by the prior multi-module pilot).
- Only Icarus Verilog is wired, and the check compiles and runs a real toolchain, so it is slower than the hand-authored checks and depends on the locally installed simulator version.

## 2026-07-04 - External AXI Router Repository Integration

Validated the existing repository-discovery, signal-source-mapping, and static driver-tracing services against real, unmodified third-party RTL. Vendored a minimal, pinned snapshot of alexforencich/verilog-axis (MIT, Copyright (c) 2014-2018 Alex Forencich) under `examples/external/verilog-axis/upstream/` — the arbitrated AXI-stream mux router path (`axis_arb_mux.v` → `arbiter.v` → `priority_encoder.v`) plus `axis_demux.v` and the upstream `COPYING` — pinned to commit `48ff7a7e2ef782cf778d47910cf85835c64b1bce` with per-file sha256 digests, URL, license, and attribution recorded in the project-owned `PROVENANCE.json` and `README.md` (upstream files clearly separated from project-owned material and vendored verbatim, never modified to make rtl-agent succeed). A new gated check (`scripts/external_axi_router_repo_check.py`, registered in `scripts/check.py`) first enforces provenance — pinned 40-hex commit, upstream URL, MIT license text and attribution present, every vendored file's sha256 matching the record, and no unlisted files under `upstream/` — then drives the existing services over the real hierarchy and asserts, against the typed schemas: all four real modules discovered in their files with `rtl_source` classification; the real instantiation hierarchy (`arbiter` and `priority_encoder` instantiated; `axis_arb_mux` and `axis_demux` uninstantiated top candidates); exact single-file mapping where the waveform scope names the module (`tb.axis_arb_mux.m_axis_tdata_reg`, `tb.axis_demux.m_axis_tvalid_reg`); preserved multi-candidate evidence on the nested instance path `tb.axis_arb_mux.arbiter.grant_reg` (both `arbiter.v` and `axis_arb_mux.v` kept); honest `unresolved` for a scope matching no declaration; real continuous driver evidence (`assign m_axis_tdata = m_axis_tdata_reg;` at `axis_arb_mux.v:231`) and real procedural evidence (`grant_reg <= grant_next;` at `arbiter.v:144`, found in the true declaring file because tracing searches every preserved candidate); non-empty unresolved identifiers; no truncation; and bounded artifact sizes (each JSON ≤ 256 KiB). No waveform fixture was needed: `map-signals --signal` takes real hierarchical names directly, so no project-authored VCD pretends to be upstream simulation output. The check skips cleanly when the snapshot is absent, and canonical validation performs no network access; `scripts/vendor_verilog_axis.py` is a manual, network-using re-vendoring helper kept out of `scripts/check.py`.

Validation evidence:

- Ran discovery/mapping/tracing over the vendored hierarchy and read actual outputs before codifying assertions; verified the drift gate by tampering one vendored byte (check fails with "vendored file drifted") and the skip path by hiding `PROVENANCE.json` (clean skip, rc 0).
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 258 pytest tests, agent portability check, all twelve example checks (including the new external repo check), and packaging smoke verification. No network access during the run.
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Concrete limitations discovered against the real codebase (recorded, not papered over; no fixture-specific heuristics added):

- Declaration line numbers are skewed early on real files: the discovery declaration regex begins `(?m)^\s*` and `\s` also matches newlines, so on `arbiter.v` the match start swallows the blank/masked lines above the keyword and `_line_for_offset` reports line 30 for a `module arbiter` that is truly at line 34 (`match.start("name")` would be correct). The check therefore does not assert exact declaration lines.
- Nested instance paths pick the wrong primary: scope scoring gives shallower components a larger depth bonus, so `tb.axis_arb_mux.arbiter.grant_reg` is classified `exact` with primary `axis_arb_mux` (`axis_arb_mux.v`) even though `grant_reg` is declared and driven in `arbiter.v`; the true declaring file survives only as a secondary candidate (and driver tracing still finds the real drivers because it searches all candidates).
- Dependency expansion conflates same-named identifiers across files: expansion scans the union of all relevant files, so `m_axis_tdata_int` (a name that exists independently in both `axis_arb_mux.v` and `axis_demux.v`) becomes one node with edges cited from both unrelated modules.

Architectural decisions:

- Provenance is enforced in the check itself (commit format, URL, license text, attribution, per-file sha256, and a no-unlisted-files sweep), so the pinned snapshot cannot silently drift and upstream separation is mechanically guarded.
- Signals are supplied to `map-signals` via the existing `--signal` option using real hierarchical names from the upstream modules, avoiding a synthetic waveform that would masquerade as upstream simulation output.
- The optional fetch helper performs network access only when run manually with an explicit invocation; it rewrites `PROVENANCE.json` digests so a deliberate re-pin remains consistent with the drift gate.

Known limitations:

- The snapshot is four files; larger upstream trees (includes, packages, interfaces, generate-heavy code) remain unexercised.
- Waveform-driven stages (extract/compare/divergence graph) are not exercised against the external RTL in this pilot since no simulator run of upstream code is vendored.
- The three discovered accuracy limitations above are real product gaps in discovery line reporting, mapping primary selection, and dependency-node identity; they motivate the next milestone.

## 2026-07-04 - External RTL Mapping Accuracy Follow-up

Fixed the three concrete real-code accuracy gaps exposed by the external verilog-axis pilot without changing public artifact schemas or adding fixture-specific/AXI-specific heuristics. Discovery declaration locations now report the declaration keyword/name line instead of leading blank or masked comment lines. Signal-source mapping now prefers a deeper unique scope component as the primary candidate for nested hierarchy paths while preserving ambiguity when a deeper component maps to multiple declarations. Driver dependency expansion now carries an evidence-file scope through the bounded textual BFS so same-named identifiers in unrelated files/modules are not conflated into one dependency expansion.

Validation evidence:

- `python3 -m pytest tests/test_discovery.py tests/test_signal_source_map.py tests/test_rtl_driver_trace.py` - passed, 32 tests.
- `python3 scripts/external_axi_router_repo_check.py` - passed, now asserting real verilog-axis declaration lines, nested `arbiter` primary mapping for `tb.axis_arb_mux.arbiter.grant_reg`, and file-scoped `m_axis_tdata_int` dependency edges.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 261 pytest tests, agent portability check, all external/example/simulator checks, and packaging smoke verification.
- `git diff --check` - passed.
- `git status --short --branch` - reviewed before commit.

Architectural decisions:

- Declaration line accuracy uses the existing regex match's `kind` group offset; it does not add preprocessing or a new parser.
- Mapping scoring still uses deterministic declaration-name evidence only; unique deeper scope evidence outranks a shallower scope, while duplicated deeper scope evidence is penalized so honest ambiguity does not override a clean outer match.
- Driver dependency expansion remains textual and bounded; dependency identifiers discovered from a driver are followed only in that driver's evidence file, while direct ambiguous/multi-candidate signal tracing still searches all preserved candidate files.

Known limitations:

- The fixes do not elaborate hierarchy or prove semantic connectivity; port connections remain textual evidence only.
- The external pilot still validates a small pinned subset and does not exercise a simulator-generated waveform from upstream RTL.
- Real instance port-connection evidence across the vendored hierarchy is the next external-RTL limitation to validate.

## 2026-07-05 - Manual Counterfactual Intervention Runner

Built the first experimental counterfactual-RTL-debugging capability, overriding the incremental External RTL Port-Connection Evidence follow-up (stage 43) per a deliberate product-direction decision recorded in the roadmap. Added a `run-counterfactual` CLI command and a `counterfactual` service (`src/rtl_agent/counterfactual/`, `counterfactual_models.py`) that, given a validated baseline failure-intelligence run and one user-supplied manual intervention, applies the intervention in an isolated Git worktree, reruns a named configured command, analyzes the resulting evidence with the existing pipeline, compares against the baseline, and emits a typed versioned counterfactual experiment report (JSON + Markdown). The runner reuses the existing command runner, `GitWorktreeManager`, triage, waveform/comparison, failure-intelligence orchestration, and run inspection — no parallel analysis path and no new analysis algorithm.

Intervention support (exactly one per experiment): a unified diff `--patch` (validated and applied with `git apply --check`/`git apply`, target files parsed via `git apply --numstat`) or a structured `replace_text` edit (`--replace-file/--replace-old/--replace-new`, reusing the existing exactly-one-match semantics), both restricted to explicitly allowed files (`--allowed-file`) and applied only inside the worktree. The intervention is preserved as an experiment artifact; an unclean apply, a disallowed file, or a missing baseline fails honestly.

Baseline handling: the runner inspects and validates the baseline run (refuses invalid), reads its manifest and failure report to identify the baseline failure signals/timestamp and the passing reference, records baseline provenance (run id, manifest and failure-report SHA-256), and never regenerates or alters it. Execution uses the named configured command only with an explicit timeout, capturing stdout/stderr/exit-code/duration/logs and the generated waveform reference (via triage of the command result); artifacts are preserved on failure and the worktree is removed afterward. The baseline repository is never modified and nothing is committed, pushed, or altered on any remote.

Outcome classification (`counterfactual/classify.py`) is deterministic and evidence-based — command status, whether valid intervention comparison evidence exists, and the baseline vs intervention divergent-signal sets and timestamps — yielding exactly one of `failure_removed`, `failure_delayed`, `failure_advanced`, `failure_changed`, `no_observable_effect`, `new_failure_introduced`, `experiment_failed`, or `insufficient_evidence`. The report records observable differences, generated-artifact references with hashes, warnings, insufficient-evidence reasons, and an explicit non-causality disclaimer; it never asserts root cause or causality.

Validation evidence:

- Real Icarus-backed pilot (`scripts/counterfactual_pilot_check.py`, registered in `scripts/check.py`): builds a target Git repo from the project-owned `examples/counterfactual-axi/` fixture (seeded backpressure fault), generates a genuine baseline failure run, then applies `interventions/remove-fault.diff` through `run-counterfactual`; asserts `failure_removed`, the source repo stays byte-for-byte unchanged (same commit, identical file hashes, no remotes), all intermediate evidence is preserved, the worktree is cleaned, and the report makes no causal claim. Skips cleanly when Icarus is absent.
- Deterministic hermetic tests (`tests/test_counterfactual.py`, 16): classifier unit tests for every outcome; service tests over a fake configured command for failure-removal, no-observable-effect, patch-application failure, command timeout, exec-error, invalid baseline refusal, disallowed-file refusal, dirty-target-repo safety, worktree cleanup, and stable report serialization (excluding volatile fields).
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 277 pytest tests, agent portability check, all example checks (including the new counterfactual pilot), and packaging smoke verification (which now exercises `run-counterfactual --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The experiment runs the intervention command through a worktree-scoped `AgentConfig` (a `model_copy` of the user config re-pointed at the worktree with allowed paths restricted to it), so the existing command runner executes inside the isolated worktree with no changes to the command runner itself.
- The intervention failure-intelligence run reuses `run_failure_intelligence` with the intervention's generated VCD as the failing input and the baseline's recorded passing reference as the golden input, so classification compares two failure reports produced by the same pipeline.
- Patch application, target-file extraction, commit resolution, and dirty detection use Git directly (`git apply`, `--numstat`, `rev-parse`, `status --porcelain`); `git worktree add --detach` isolates the intervention from the working tree, so uncommitted changes in the target repo are excluded (recorded as a warning) rather than blocking the experiment.

Known limitations:

- Exactly one manual intervention per experiment; no automatic/LLM intervention generation, patch search/optimization, or stimulus minimization (out of scope by design).
- `new_failure_introduced` vs `failure_changed` is decided by divergent-signal-set overlap; assertion-identity change is recorded as evidence but is not itself a classifier input because a baseline failure-intelligence run does not necessarily carry an assertion.
- The pilot depends on a locally installed Icarus Verilog; the hermetic tests use a fake command and cover the machinery and classification rather than real simulation.

## 2026-07-05 - Failure Fingerprinting and Experiment Comparison

Added a deterministic, read-only failure-fingerprinting capability for existing failure-intelligence runs. The new `failure_fingerprint` service and typed models build exact and family digests from stable observed-evidence components: assertion identity, terminal simulator/command outcome, normalized failure-time characteristics, earliest divergent signals, ranked divergent and relevant signal sets, transition and `x`/`z` characteristics, mapped RTL source/dependency shape, unresolved and ambiguous markers, and failure-divergence graph shape. The digest construction excludes volatile metadata such as run IDs, execution timestamps, durations, absolute paths, UUID-like command IDs, artifact hashes, and raw path-bearing command errors. Shifted-time failures remain distinguishable by exact digest while sharing the same likely observed failure family when the signal/source/dependency mechanism is otherwise unchanged.

Added `rtl-agent fingerprint-run` and `rtl-agent compare-fingerprints` as bounded read-only commands. `fingerprint-run` consumes an existing run directory and writes a typed JSON fingerprint without re-running analysis. `compare-fingerprints` consumes two fingerprint JSON files and emits a typed comparison report distinguishing exact identity, same likely observed failure family, related but materially different failures, and insufficient evidence; the CLI also prints a concise component-level summary. README command documentation and command-help coverage were updated.

Integrated fingerprints into counterfactual experiment reports where available: baseline and intervention failure identities now carry exact/family digest fields, Markdown reports display them, and observable differences record digest changes for failure-removed and failure-changed scenarios. Missing or malformed fingerprint evidence does not block counterfactual analysis; it remains an optional comparison-strength improvement over the existing evidence path.

Validation evidence:

- `python3 -m pytest tests/test_failure_fingerprint.py tests/test_counterfactual.py tests/test_cli.py` - passed, 31 tests.
- `python3 -m ruff format --check .` - passed.
- `python3 -m ruff check .` - passed.
- `python3 -m mypy` - passed, 151 source files.
- `python3 scripts/check.py` - passed.
- `git diff --check` - passed.
- `git status --short --branch` - reviewed before commit.

Architectural decisions:

- The fingerprint service only reads manifest-linked artifacts from an existing run and stores input provenance as run-relative paths; it does not trust or hash absolute run locations into semantic identity.
- Exact digests include normalized timing evidence; family digests intentionally exclude time-only shifts so repeated observations of the same mechanism can group together while still preserving exact distinctions.
- Comparison remains local and pairwise in this milestone. Multi-run clustering is the next milestone rather than being hidden inside fingerprint comparison.

Known limitations:

- Fingerprints summarize available textual artifacts only; they do not add elaboration, preprocessing, semantic connectivity, new waveform analysis, stimulus minimization, or causal inference.
- Sparse evidence yields an explicit insufficient-evidence comparison rather than a confident family assignment.
- The new commands compare one run or two fingerprints at a time; batch clustering across regression runs is the next active milestone.

## 2026-07-05 - Failure Family Clustering Across Regression Runs

Added a deterministic, read-only workflow that groups many existing failure fingerprints from a regression run into a small set of recurring observed failure families and emits an engineer-facing regression summary. New `cluster-failures` CLI command plus a `failure_family` service (`src/rtl_agent/failure_family/`, `failure_family_models.py`) turn a repeated `--fingerprint` list and/or a `--fingerprint-dir` into a typed, versioned JSON report, a concise Markdown report, and a terminal summary — without rerunning simulations or performing new waveform/RTL analysis. Inputs preserve their source path as provenance while absolute paths never enter semantic identity; `--strict` fails the whole operation on any invalid/incompatible input, while permissive (default) excludes invalid inputs and records warnings.

Grouping reuses the existing fingerprint comparison semantics with no duplicated logic: the path-based `compare_fingerprints` was refactored to delegate to a new public model-level `compare_fingerprint_reports`, which the clustering service reuses for related-family links. Primary family membership is equal `family_digest` (a stable, transitive rule documented in the parser notes); exact duplicates are equal `exact_digest` within a family; insufficient-evidence fingerprints (non-empty `insufficient_evidence`) are reported separately and never forced into a confident family; single-member families are unique outliers; distinct families that still share ≥1 fingerprint component are recorded as related-family links (bounded pairwise over representatives). Each family carries one deterministic representative (most complete evidence; ties broken by canonical fields then digest, with the reason recorded), a concise evidence-grounded description that is never a root-cause claim, an observed time range, assertion identities, earliest-divergence signals, relevant-signal union/intersection, mapped sources, and ambiguity/insufficient markers. Every ordering is canonical, so the result is independent of input order. Counterfactual experiment reports may be supplied directly — their baseline and intervention runs are fingerprinted via the existing `fingerprint_run` service, with no separate manual conversion.

Validation evidence:

- Deterministic tests (`tests/test_failure_family.py`, 17): multiple exact duplicates; time-shifted members of one family; multiple distinct families; changed assertion identity; changed earliest-divergence mechanism; insufficient-evidence handling; related but nonidentical families (a `related_but_materially_different` link with shared/differing components); duplicate input files; malformed and incompatible input; strict vs permissive; input-order independence; deterministic representative selection; stable JSON and Markdown output; empty input; directory input; a larger synthetic regression set (20 runs → 3 families); and counterfactual baseline/intervention fingerprints participating.
- Hermetic example check (`scripts/failure_family_cluster_check.py`, registered in `scripts/check.py`): generates real fingerprints for three distinct mechanisms from the checked-in fixtures, replays each three times, and asserts nine regression seeds collapse into three families (each with three exact-duplicate members), plus order-independence — with no simulator.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 306 pytest tests, agent portability check, all example checks (including the new family-cluster check), and packaging smoke verification (which now exercises `cluster-failures --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Family membership is defined by equality of the existing `family_digest` (transitive by construction), so grouping needs no non-transitive pairwise clustering; the existing comparison semantics are used only for related-family links and representative-level component differences.
- To avoid duplicating fingerprint logic, comparison was made reusable at the model level (`compare_fingerprint_reports`) rather than re-implemented in the clustering service; the public path-based API is unchanged.
- Counterfactual integration derives fingerprints from a counterfactual report's baseline run directory and its `intervention-run` subdirectory via `fingerprint_run`, so a `failure_removed` intervention naturally lands in the insufficient-evidence bucket while the baseline forms a family.

Known limitations:

- Related-family link computation is bounded (skipped with a warning above 48 families) to keep the pairwise pass small and deterministic.
- Within a single `family_digest`, all family-defining fields are identical, so representative completeness ties are common and resolved by exact digest then source path; the recorded reason states this.
- Counterfactual participation fingerprints the baseline and intervention runs referenced by one report; it does not recursively expand nested experiment references.

## 2026-07-05 - Counterexample Stimulus Minimization Foundation

Built the first generic deterministic reduction harness for minimizing a failing RTL stimulus while preserving the same observed failure family, using one explicit structured stimulus format. The goal was reliable reduction mechanics (candidate evaluation, equivalence checking, caching, provenance, reporting), not broad automatic minimization across every testbench format.

Structured stimulus (`src/rtl_agent/stimulus.py`, `stimulus_models.py`): a compact JSON of ordered, independent actions, each with a stable id, index, kind, and payload plus optional metadata excluded from semantic identity. Parsing validates duplicate/malformed item ids and empty stimuli; `stimulus_digest` is a deterministic digest over the ordered `(kind, payload)` content (ids, indices, and metadata excluded) so semantically identical candidates share a digest; `subset_by_ids` removes items order-preservingly and renumbers indices; `materialize_stimulus` writes the candidate JSON plus a hex program into the worktree.

Reduction (`src/rtl_agent/reduction/`): `evaluate_candidate` materializes a candidate only inside an isolated Git worktree, runs the named configured command via the existing command runner, and reuses the existing triage (assertion timestamp), failure-intelligence orchestration, and fingerprint services to classify preservation as one of `same_failure_exact`, `same_failure_family`, `different_failure`, `failure_removed`, `insufficient_evidence`, `candidate_invalid`, `execution_failed`, or `timed_out` (only the first two preserve the counterexample). `ddmin` is a deterministic delta-debugging reduction over whole items (never mutating contents, preserving relative order, coarse-to-fine chunking) with a `BudgetExhausted` early stop. `minimize_stimulus` validates and refuses an invalid baseline, anchors on the baseline fingerprint's exact/family digests, runs ddmin with a caching oracle (semantic-digest cache so identical candidates are never re-simulated; configurable `--max-evaluations` budget and `--timeout` per evaluation), removes the worktree afterward, and emits a typed versioned JSON + Markdown report (baseline and candidate digests, target commit, original/minimized stimulus references and digests, retained/removed item ids, ordered evaluation history with per-candidate classification and fingerprint digests, total evaluations, cache hits, termination reason, simulator summary, reproducibility instructions, warnings, and an explicit disclaimer that preserving a failure family does not prove identical root cause). A `minimize-stimulus` CLI command wires it up with a terminal summary (item counts, percent reduced, evaluations, cache hits, classification, termination reason, output paths).

Validation evidence:

- Real Icarus-backed pilot (`scripts/counterexample_pilot_check.py`, registered in `scripts/check.py`): builds a target Git repo from the project-owned `examples/counterexample-axi/` fixture (a program-driven testbench that loads the structured stimulus as a hex program and drives one action per cycle; the seeded fault corrupts the held payload when a stall follows a send), generates a genuine baseline failure run, and runs `minimize-stimulus`; the 7-item stimulus (three warmup idles, the send/stall core, two cooldown idles) reduces to a strictly smaller subset that still reproduces the same failure family, the irrelevant idles are removed, all candidate artifacts are preserved, and the source repository stays byte-for-byte unchanged. Skips cleanly without Icarus.
- Deterministic hermetic tests (`tests/test_stimulus.py` 8, `tests/test_reduction.py` 14): structured-stimulus parsing, duplicate/malformed ids, empty stimulus, deterministic semantic digest, subset order preservation, hex encoding, materialization; ddmin reduces-to-minimal, order preservation, determinism, irreducible, budget exhaustion; and `minimize_stimulus` over a fake configured command for successful reduction, failure-removed and changed-family (baseline-not-preserved), command failure, timeout, evaluation caching (unique-vs-history invariant), budget exhaustion, invalid-baseline rejection, repository-unchanged, and stable serialization.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking, 328 pytest tests, agent portability check, all example checks (including the new counterexample pilot), and packaging smoke verification (which now exercises `minimize-stimulus --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Preservation is judged solely by the fingerprint family digest, which is stimulus-shape-sensitive: reduction stops at the smallest subset whose windowed divergent-signal waveform (and thus family digest) still matches the baseline. In the pilot, one warmup idle is retained because removing every warmup would push the fault into the reset window and change the observed family — a correct, honest minimum for this oracle rather than a naive count-based minimum.
- The candidate digest is over `(kind, payload)` only (not item ids), so interchangeable actions map to one cached evaluation; the classifier treats "no divergence" as `failure_removed` even though the fingerprint marks that as insufficient evidence of a failure.
- One isolated worktree is created for the whole minimization and re-materialized per candidate (cheaper than a worktree per candidate) while still never touching the source repository; command execution runs through a worktree-scoped `AgentConfig` copy so the existing command runner is reused unchanged.

Known limitations:

- One explicit structured stimulus format only; arbitrary SystemVerilog/cocotb/UVM testbenches, random-seed reduction, waveform/signal minimization, and item-content mutation are intentionally out of scope.
- The family-digest oracle is strict (waveform-shape-sensitive), so reduction preserves the family only for item removals that leave the windowed divergent-signal behavior unchanged; it minimizes to a 1-minimal subset under that oracle, not a globally smallest reproducer.
- The pilot depends on a locally installed Icarus Verilog; the hermetic tests use a fake command and cover the mechanics and classification rather than real simulation.

## 2026-07-06 - Counterfactual Experiment Matrix

Composed the complete experimental-debugging workflow into one deterministic command: baseline failure -> minimized counterexample -> a bounded set of explicit manual interventions -> isolated experiment runs -> failure-intelligence analysis -> fingerprint comparison -> a typed intervention-outcome matrix. This milestone was about reliably composing existing capabilities, not adding new analysis.

Shared intervention engine (`src/rtl_agent/counterfactual/intervention.py`): extracted the manual patch / structured `replace_text` application, normalization, and a deterministic semantic intervention digest from the counterfactual service into a reusable module raising `InterventionError`. Both the counterfactual runner and the experiment matrix now use this single edit engine; the counterfactual service delegates to it and translates `InterventionError` back to `CounterfactualError`, preserving its public behavior (the one counterfactual test whose match string referenced the old `--allowed-file` wording was updated to the generic message).

Experiment matrix (`src/rtl_agent/experiment_matrix/`): `run_experiment_matrix` validates a baseline failure-intelligence run (refusing an invalid or insufficient-evidence baseline), loads the minimized stimulus and reduction report (rejecting a stimulus/report digest mismatch), and validates an explicit bounded intervention manifest (`src/rtl_agent/experiment_matrix_models.py`) whose entries carry a stable id, description, a patch or structured replace edit, allowed files, optional tags/metadata, and an enabled flag (duplicate ids, empty ids, missing allowed files, and entries without exactly one of patch/replace are rejected). It first runs the minimized stimulus with no intervention to establish the comparison reference, validated to share the original baseline's failure family, because the minimized stimulus reproduces the fault at a different absolute time than the full-stimulus baseline. For each enabled intervention it creates a fresh isolated Git worktree, applies the intervention only inside it, materializes the same minimized stimulus, runs the named command, and reuses the existing triage (assertion time), failure-intelligence orchestration, fingerprint, fingerprint-comparison, and counterfactual `classify_outcome` services. Each typed row records the intervention and reference exact/family digests, files affected, execution and simulator status, resulting fingerprint digests, the counterfactual outcome (failure_removed / failure_delayed / failure_advanced / failure_changed / no_observable_effect / new_failure_introduced / experiment_failed / insufficient_evidence), the fingerprint-comparison relation, whether the family was preserved / removed / shifted in time / replaced, warnings, artifact references, and an explicit non-causality disclaimer. Experiments are cached by a semantic digest over target commit, baseline family digest, minimized-stimulus digest, command identity, and canonical intervention, so semantically duplicate interventions are served from cache and never re-simulated; row ordering follows the manifest deterministically and the source repository is never modified. A `run-experiment-matrix` CLI command emits typed versioned JSON + Markdown reports and a concise terminal matrix.

Validation evidence:

- Real Icarus-backed pilot (`scripts/experiment_matrix_pilot_check.py`, registered in `scripts/check.py`): builds a target Git repo from the counterexample AXI fixture, generates a genuine baseline, minimizes the stimulus, then runs the checked-in intervention manifest (`examples/counterexample-axi/interventions.json`) of four distinct interventions plus a cached duplicate: remove the failure (failure_removed), a benign marker edit (no_observable_effect, exact fingerprint), corrupt one cycle earlier in the faulted build only (failure_advanced, -10 ns), and corrupt to a defined wrong value instead of x (materially different failure family), with a fifth semantic-duplicate intervention served from cache. The pilot asserts the same minimized stimulus is reused, all interventions run in isolated worktrees, the source repo is byte-for-byte unchanged, every executed row preserves evidence, classifications match observed results, and the report makes no causal claim. Skips cleanly without Icarus.
- Deterministic hermetic tests (`tests/test_experiment_matrix.py`, 13): manifest parsing, duplicate ids, patch-or-replace requirement, malformed baseline, stimulus/reduction digest mismatch, deterministic ordering with a disabled intervention, disallowed-file and patch-application invalid rows, reference-failure abort, intervention-level execution failure and timeout, bounded experiment budget, failure removal, no-effect, same-signal timing shift (failure_delayed), different family, semantic-duplicate caching, repository immutability, and stable serialization; the counterfactual refactor is covered by the existing `tests/test_counterfactual.py`.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict type checking (175 source files), 341 pytest tests, agent portability check, all example checks (including the new experiment matrix pilot), and packaging smoke verification (which now exercises `run-experiment-matrix --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- Interventions are compared against a minimized-counterexample reference run, not the original full-stimulus baseline, because the minimized stimulus reproduces the fault at a different absolute time; comparing against the full baseline produced a spurious uniform time shift on every row. The reference is validated to share the baseline family before any intervention runs, so the family anchor is still the investigation's baseline family.
- The counterfactual outcome (signal + time based) and the fingerprint-comparison relation (full family digest) are reported per row as two independent lenses; they can legitimately disagree (for example a defined-value corruption keeps the same divergent signal and time yet yields a materially different family), which is informative rather than contradictory.
- A fresh worktree is created per intervention (reset to the target commit) so interventions never compound, while the reduction milestone's single-worktree reuse is intentionally not shared here.

Known limitations:

- Interventions are explicit manual patches or structured replace_text edits only; there is no automatic or template-driven generation yet (that is the next milestone), no LLM-generated patches, no intervention search/optimization, and no causal scoring.
- The fingerprint family digest is window-sensitive, so a genuine "same family at a shifted time" is demonstrated at the counterfactual-outcome level (failure_delayed / failure_advanced) rather than as an identical family digest; the hermetic timing-shift test asserts the counterfactual classification and the real advance is shown in the pilot.
- The pilot depends on a locally installed Icarus Verilog; the hermetic tests use a fake command driven by RTL markers and cover the composition and classification rather than real simulation.

## 2026-07-06 - Hypothesis-Driven Intervention Templates

Built the first deterministic evidence-to-experiment generation layer: a `generate-interventions` command and `intervention_templates` service that transform existing failure evidence into a bounded set of explicit, reviewable intervention candidates compatible with the Counterfactual Experiment Matrix. Generation only — nothing is applied, executed, committed, or pushed, and the target repository is never modified.

Template library (`src/rtl_agent/intervention_templates/templates.py`): a small, fixed set of pure, deterministic edit derivations over already-extracted textual evidence — suppress an assignment (drive a benign `'0`, skipping self-holds), hold a register value across a sequential nonblocking update (`lhs <= lhs`), override one Boolean guard with `1'b0` (preserving the original expression), and block one constant next-state transition by holding. A time-windowed bounded-signal override cannot be expressed safely with the existing patch/replace_text edit model, so it is recorded as unsupported rather than built as a parallel mechanism.

Generator (`src/rtl_agent/intervention_templates/service.py`): validates the failure-intelligence run via the existing run inspector (a tampered evidence artifact is caught by its hash and the whole run refused), loads the divergence graph, signal-source map, and driver/dependency trace, and (contextually) the failure fingerprint. It generates direct suppress/hold/override candidates only for divergent root signals with exact/probable mapping, and derives block-state-transition candidates for state-like enable registers (>=2 non-reset constant transitions) referenced in a divergent driver's guard. Every candidate is resolved read-only against the committed target source with `git show <commit>:<path>`: the repo-relative file is matched from the driver path against the allowed-file policy, the exact edit span is verified to occur exactly once (ambiguous, disallowed, or stale spans are refused with a recorded reason), and the original snippet + file sha256 are preserved. Confidence (`high_evidence` / `moderate_evidence` / `low_evidence` / `insufficient_evidence`) is a deterministic function of evidence completeness only (exact mapping + divergent root + direct failing-value driver -> high), never predicted fix likelihood. Candidates are deduplicated by a semantic digest over (file, old, new, family), deterministically ordered (confidence, then divergence proximity, then template kind, file, line, digest), and bounded by `--max-candidates`.

Outputs (`report.py`): a matrix-compatible `interventions.json` (the `InterventionManifest` reused verbatim from the experiment matrix, one entry per candidate with a `replace` edit, allowed files, tags, and rich evidence metadata), a typed versioned `intervention-templates.json` with full per-candidate evidence anchors, a `intervention-templates.md` review report, and per-candidate unified diffs. A `generate-interventions` CLI command emits a terminal summary; the generated manifest is consumed unchanged by `run-experiment-matrix`.

Validation evidence:

- Real Icarus-backed pilot (`scripts/intervention_templates_pilot_check.py`, registered in `scripts/check.py`): builds a target repo from the counterexample AXI fixture, generates a genuine baseline failure-intelligence run, and runs `generate-interventions` (max 12). It asserts at least three candidates spanning suppress/hold/override(+block), exact evidence preservation (each recorded span occurs exactly once in the committed source; hashes and driver anchors present), a valid matrix-compatible manifest, repository immutability, and no causal claim. As a separate integration step it minimizes the stimulus and drives the experiment matrix with the generated manifest, confirming at least one evidence-backed candidate removes or changes the observed failure (the generated hold-register and override-condition edits on the fault line both remove the failure). Skips cleanly without Icarus.
- Deterministic hermetic tests (`tests/test_intervention_templates.py`, 17): pure template unit tests (assignment extraction, procedural vs continuous, hold, guard override, block-transition, self-hold skip) plus integration tests that build a real failure-intelligence run from hand-authored VCDs (no simulator) and cover expected-kind generation with high-evidence fault-line candidates, deterministic ordering and stable digests, candidate bounds, disallowed-file rejection, ambiguous-span rejection, stale-commit source mismatch, invalid/malformed evidence rejection, matrix-manifest compatibility, repository immutability, serialization + diffs, and a full generated-manifest-to-matrix integration via a fake command keyed on the fault literal.
- `python3 scripts/check.py` - passed: Ruff format check, Ruff lint, mypy strict (182 source files), 358 pytest tests, agent portability check, all example checks (including the new intervention-templates pilot), and packaging smoke (now exercising `generate-interventions --help`).
- `git diff --check` - passed.
- `git status --short` - reviewed before commit.

Architectural decisions:

- The driver trace only traces signals present in the waveform, so a state-like enable register (e.g. `locked`) is reached via a divergent driver's guard dependency rather than as a standalone target; direct templates are restricted to divergent root signals to avoid generating candidates for unrelated traced signals.
- Edit spans are validated against the committed target source (not the working tree) so a stale commit or drifted source is detected as a span mismatch and the candidate is refused; nothing is applied to verify, keeping generation strictly read-only.
- The generated manifest reuses the experiment matrix's `InterventionManifest`/`InterventionEntry` schema verbatim, so no schema conversion is needed between generation and execution.

Known limitations:

- Direct templates require an exact/probable single source mapping and a syntactically simple assignment/guard; multi-region edits, blocking assignments in complex forms, and non-trivial guard expressions are refused rather than approximated. The bounded-signal-override template is intentionally unsupported under the current edit model.
- Confidence reflects only evidence completeness, not fix likelihood; a high-evidence candidate is not a suspected root cause.
- The pilot depends on a locally installed Icarus Verilog to produce real evidence; the hermetic tests synthesize a real failure-intelligence run from hand-authored VCDs and a fake command rather than a simulator.
