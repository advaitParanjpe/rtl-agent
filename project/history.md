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
