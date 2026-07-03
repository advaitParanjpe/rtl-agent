# rtl-agent

`rtl-agent` is the foundation for an open-source, vendor-neutral agent orchestration platform for RTL engineering.

The long-term product will take a real Verilog/SystemVerilog repository plus a bounded engineering issue and coordinate AI agents, Git worktrees, verification environments, and EDA tools to produce either:

- a reproducible, evidence-backed verified Git diff; or
- an honest, evidence-backed failure report.

The principle is: **Models propose. Tools decide.**

## Current State

`rtl-agent` currently contains deterministic local infrastructure:

- milestone-driven project-control files;
- typed YAML configuration;
- installable `rtl-agent` CLI;
- durable JSON/JSONL run artifacts;
- named command execution with timeout and output logs;
- narrow Git worktree helpers;
- deterministic RTL repository discovery with a versioned JSON repository map;
- deterministic issue parsing with a versioned JSON task contract;
- one bounded implementation-agent loop with a deterministic stub provider;
- read-only deterministic review reports for implementation artifacts;
- bounded waveform and assertion triage from command artifacts;
- deterministic verification-strength assessment from existing artifacts;
- deterministic local benchmark manifests and run reports;
- compact local evidence-bundle export indexes for run artifacts;
- tests, linting, formatting, and type checking.

It does not yet contain real external model-provider integration, autonomous multi-agent behavior, review agents, semantic waveform analysis, mutation execution, pull requests, dashboards, queues, databases, containers, CI automation, or a UI.

## Installation

Use Python 3.12 or newer.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install ".[dev]"
```

For source-tree development without reinstalling after edits, use `PYTHONPATH=src python -m rtl_agent ...`.

## Using Codex or Claude Code

Codex:

```bash
cd ~/Desktop/Projects/rtl-agent
codex
```

Prompt:

```text
Read AGENTS.md and project/current.md, then complete the active milestone fully.
```

Claude Code:

```bash
cd ~/Desktop/Projects/rtl-agent
claude
```

Prompt:

```text
Complete the active milestone.
```

Claude reads `CLAUDE.md`, which points back to authoritative `AGENTS.md`. Both tools rely on the same checked-in milestone and handoff files. Switching is safest between milestones; when switching mid-milestone, the outgoing agent must leave `project/handoff.md` active and push a checkpoint branch.

## Quick Start

```bash
rtl-agent --help
rtl-agent inspect-config --config examples/rtl-agent.yaml
rtl-agent inspect-repo --repo examples/simple-rtl --output .rtl-agent/simple-rtl-map.json
rtl-agent parse-issue --issue examples/issues/reset-behavior.md --repository-map .rtl-agent/simple-rtl-map.json --output .rtl-agent/reset-task-contract.json
rtl-agent run-benchmark --manifest examples/benchmarks/local-smoke.yaml
rtl-agent discover --config examples/rtl-agent.yaml
rtl-agent run-command --config examples/rtl-agent.yaml --command smoke
```

Commands that consume existing run artifacts, such as `triage-command`, `review-task`, `assess-verification`, and `export-evidence`, are shown in their sections below with `<run-id>` placeholders.

Module invocation also works after installation:

```bash
python3 -m rtl_agent --help
python3 -m rtl_agent run-benchmark --manifest examples/benchmarks/local-smoke.yaml
```

`inspect-repo` writes the repository map to the caller-specified path and prints only a concise summary, for example:

```json
{
  "commands": 2,
  "declarations": 4,
  "files_indexed": 6,
  "output": ".rtl-agent/simple-rtl-map.json",
  "schema_version": 1,
  "warnings": 0
}
```

`discover --config ...` inspects the configured repository and writes a run artifact such as:

```text
.rtl-agent/runs/<run-id>/
├── run.json
├── events.jsonl
└── discovery/
    └── repository-map.json
```

Run canonical checks:

```bash
python3 scripts/check.py
git diff --check
git status --short
```

`scripts/check.py` includes a local packaging smoke check. It builds the current package into a wheel, installs that wheel into a temporary virtual environment without index access or dependency resolution, and verifies both `rtl-agent --help` and `python -m rtl_agent --help` plus documented command help.

It also runs `scripts/e2e_example_check.py`, a compact local example check that copies the checked-in fixtures to a temporary workspace, exercises inspect, parse, bounded implementation with retry, triage, review, verification-strength, benchmark, and evidence export stages, and verifies stable artifact statuses through the existing schemas. `scripts/failure_example_check.py` covers the matching bounded terminal-failure path, `scripts/tool_failure_example_check.py` covers deterministic structured-tool failure reporting, and `scripts/no_change_example_check.py` covers a successful no-op edit that still ends in an unacceptable review and insufficient verification strength because no validation command was executed.

## Configuration

`examples/rtl-agent.yaml` defines:

- repository path;
- allowed working paths;
- protected paths;
- named validation commands;
- run-artifact directory;
- execution timeout and output limits.
- discovery include/exclude patterns and scan limits.

Commands are executed by name only. The runner does not invoke a shell.

## Repository Discovery

Discovery inspects files under one repository root and never executes commands found in that repository. It classifies common RTL, include, testbench, assertion, constraint, build, script, documentation, generated/vendor, and unknown relevant files. It currently recognizes Verilog/SystemVerilog source extensions `.v`, `.sv`, `.vh`, and `.svh`, plus common project files such as `Makefile`, `*.mk`, `*.tcl`, `*.ys`, `*.sby`, file lists, YAML/TOML/JSON config, and Python scripts.

For Verilog/SystemVerilog, discovery uses a lightweight parser that masks comments and strings before extracting ordinary module, interface, package, program, checker, include, import, and instantiation patterns. This is not a complete SystemVerilog parser: it does not preprocess macros, elaborate generates, resolve parameters, or semantically compile the design. Top-level modules are reported as scored candidates with reasons, not as guaranteed truth.

Build and verification discovery recognizes command evidence for tools including Verilator, Icarus Verilog, Yosys, cocotb, pytest, Make, and SymbiYosys. Commercial tools may appear as recorded evidence when explicitly referenced.

## Issue Parsing

`parse-issue` converts a Markdown or plain-text issue into a typed task-contract JSON document:

```bash
rtl-agent parse-issue \
  --issue examples/issues/reset-behavior.md \
  --repository-map .rtl-agent/simple-rtl-map.json \
  --output .rtl-agent/reset-task-contract.json
```

It extracts only explicit information from recognized headings, bullets, checkboxes, fenced shell commands, and path/code references. Supported contract fields include requested behavior, scoped repository context, invariants, acceptance criteria, validation commands, prohibited shortcuts, evidence requirements, checklist items, warnings, and optional repository-map context.

Issue parsing is deterministic and does not execute validation commands. Ambiguous prose such as "maybe", "if possible", or "consider" is preserved only when it appears inside an explicit requirement section and is also reported as a warning. Unsectioned ambiguous prose is ignored with a warning. The parser does not plan an implementation or invent missing requirements.

## Bounded Implementation Agent

`implement-task` runs one tightly bounded implementation loop using a deterministic stub provider plan:

```bash
rtl-agent implement-task \
  --config examples/simple-rtl-agent.yaml \
  --task-contract .rtl-agent/reset-task-contract.json \
  --repository-map .rtl-agent/simple-rtl-map.json \
  --provider-plan examples/provider-plans/no-change.json \
  --allowed-file rtl/top.sv \
  --validation-command smoke \
  --max-iterations 1
```

The implementation agent accepts only structured stub-provider tool calls. Supported tools are `read_file` and `replace_text`. Each editable file must be explicitly listed with `--allowed-file`, must be repository-relative, must be present in the repository map, and must be in the task contract's scoped repository context. Validation can run only configured named commands explicitly listed with `--validation-command`; commands from model output are names, not shell text.

Validation failures are classified deterministically from command metadata plus bounded stdout/stderr excerpts. Categories include timeout, missing executable, assertion/test failure evidence, lint/syntax evidence, generic command failure, and unknown failure. When validation fails and `--max-iterations` leaves room, the next provider request receives only concise structured failure evidence, not unrestricted logs. If retries are exhausted, the report remains failed.

Runs write audit artifacts under:

```text
.rtl-agent/runs/<run-id>/
├── run.json
├── events.jsonl
├── commands/
└── implementation/
    ├── provider-request-1.json
    ├── provider-response-1.json
    ├── diff.patch
    └── report.json
```

The current provider is intentionally a local stub for deterministic tests and examples. There is no broad provider support, reviewer agent, pull-request automation, or multi-agent framework yet.

## Independent Review

`review-task` reads an existing task contract, repository map, implementation report, diff artifact, and validation evidence, then writes a versioned review-report JSON file:

```bash
rtl-agent review-task \
  --task-contract .rtl-agent/reset-task-contract.json \
  --repository-map .rtl-agent/simple-rtl-map.json \
  --implementation-report .rtl-agent/runs/<run-id>/implementation/report.json \
  --output .rtl-agent/review-report.json \
  --fail-on-unacceptable
```

The review pass is read-only. It does not edit files, execute commands, retry implementation, or override failed validation. Deterministic findings are separated from optional provider-backed semantic findings. Every finding must cite concrete evidence such as an input artifact path and detail. Failed or missing validation evidence makes the review unacceptable.

## Waveform and Assertion Triage

`triage-command` reads an existing command result artifact and writes a bounded triage JSON report:

```bash
rtl-agent triage-command \
  --command-result .rtl-agent/runs/<run-id>/commands/<command-id>/result.json \
  --output .rtl-agent/triage-report.json
```

Triage extracts explicit assertion failures, simulator context lines, and waveform file references such as `.vcd`, `.fst`, `.fsdb`, `.wlf`, and `.ghw` from captured stdout/stderr artifacts. It records bounded excerpts and artifact paths only. It does not execute simulators, inspect waveform contents, render waveforms, perform semantic debugging, or pass unrestricted logs to providers.

`review-task` can also consume a triage report with `--triage-report` so missing waveform references or captured assertion failures are cited in review findings.

## VCD Failure Window Extraction

`extract-waveform-window` reads a standard textual VCD waveform and emits a compact, bounded, versioned waveform-slice JSON artifact around a failure timestamp:

```bash
rtl-agent extract-waveform-window \
  --vcd examples/waveforms/failure.vcd \
  --failure-time 40 \
  --before 15 \
  --after 5 \
  --signal-prefix top.dut \
  --output .rtl-agent/waveform-slice.json
```

The extractor parses VCD headers, scopes, variables, timescale, and value changes deterministically. It selects signals by exact hierarchical name (`--signal`) or simple hierarchical prefix (`--signal-prefix`), emits only value transitions inside the requested window, and records each selected signal's value at the window start when a prior change makes it determinable. Scalar, vector, unknown (`x`), and high-impedance (`z`) values are preserved verbatim. Source metadata records the path, size, SHA-256 hash, timescale, requested window, and observed bounds. When `--vcd` is omitted, `--triage-report` locates an existing `.vcd` reference from a triage report. Textual VCD only; the tool never copies the full waveform, interprets causal meaning, or claims root cause.

## Verification Strength Assessment

`assess-verification` reads existing task-contract, repository-map, implementation-report, optional review-report, and optional triage-report artifacts, then writes a versioned verification-strength JSON report:

```bash
rtl-agent assess-verification \
  --task-contract .rtl-agent/reset-task-contract.json \
  --repository-map .rtl-agent/simple-rtl-map.json \
  --implementation-report .rtl-agent/runs/<run-id>/implementation/report.json \
  --review-report .rtl-agent/review-report.json \
  --triage-report .rtl-agent/triage-report.json \
  --output .rtl-agent/verification-strength.json \
  --fail-on-insufficient
```

The assessment is deterministic, bounded, and artifact-only. It scores evidence from passed command coverage, acceptance-criteria references, changed-file relevance, retry history, review outcome, and triage availability for simulator-like failures. It flags weak patterns such as no validation, failed latest validation, smoke-only validation, missing acceptance coverage, failed review, missing triage for simulator failures, and validation evidence unrelated to changed files. It does not mutate files, execute commands, inspect waveform contents, run mutation tests, or call a model provider.

## Benchmark Suite

`run-benchmark` reads a local benchmark manifest and runs compact cases through existing named-command execution and run artifacts:

```bash
rtl-agent run-benchmark \
  --manifest examples/benchmarks/local-smoke.yaml \
  --fail-on-unmet-expected
```

Manifests declare bounded resources, local config files, named commands, per-step timeout overrides, and expected observed statuses: `passed`, `failed`, `timeout`, or `infrastructure_error`. The runner writes a versioned benchmark report under the manifest's configured run-artifact directory:

```text
.rtl-agent/runs/<run-id>/
├── commands/
└── benchmarks/
    └── report.json
```

The runner reuses `CommandRunner` and `RunStore`; it does not fetch external repositories, call model providers, create pull requests, require CI, or copy large RTL projects.

## Evidence Bundle Export

`export-evidence` reads an existing run directory and writes a compact local index:

```bash
rtl-agent export-evidence \
  --run-dir .rtl-agent/runs/<run-id> \
  --output-dir .rtl-agent/bundles/<run-id> \
  --fail-on-failed-export
```

The export writes:

```text
.rtl-agent/bundles/<run-id>/
├── manifest.json
└── bundle.json
```

The bundle preserves artifact provenance, relative paths, SHA-256 hashes, byte sizes, and JSON schema versions where present. It references command logs and waveform-like files as omitted local artifacts instead of copying their contents. Missing optional artifacts are warnings; missing required `run.json` produces a failed export result. The exporter does not execute commands, mutate source files, call providers, upload artifacts, sign bundles, add cloud storage, or include large logs and waveforms.

## Schema Examples

Compact public-schema examples live under `examples/schema-artifacts/`. They cover representative repository-map, task-contract, implementation-report, review-report, triage-report, verification-strength-report, benchmark-report, and evidence-bundle-report artifacts.

These fixtures are intended for compatibility tests and documentation. They validate through the current typed Pydantic models and are kept free of generated run directories, logs, waveforms, secrets, external repository snapshots, and volatile values such as real timestamps, UUIDs, absolute paths, durations, and hashes.

## Run Artifacts

Command runs write evidence under the configured artifact directory:

```text
.rtl-agent/runs/<run-id>/
├── run.json
├── events.jsonl
└── commands/
    └── <command-id>/
        ├── result.json
        ├── stdout.log
        └── stderr.log
```

Large command output stays on disk and result metadata points to the saved files.

## Milestone Workflow

Future agent sessions must follow `AGENTS.md` and use these project-control files:

- `project/current.md` - exactly one active milestone;
- `project/roadmap.md` - staged product plan;
- `project/history.md` - compact completed-milestone evidence;
- `AGENTS.md` - repository-wide agent instructions.

When a milestone completes, the agent records history, updates the roadmap, replaces `project/current.md` with the next concrete milestone, and returns the standardized handoff.
