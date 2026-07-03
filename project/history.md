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
