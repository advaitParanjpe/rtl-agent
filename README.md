# rtl-agent

`rtl-agent` is the foundation for an open-source, vendor-neutral agent orchestration platform for RTL engineering.

The long-term product will take a real Verilog/SystemVerilog repository plus a bounded engineering issue and coordinate AI agents, Git worktrees, verification environments, and EDA tools to produce either:

- a reproducible, evidence-backed verified Git diff; or
- an honest, evidence-backed failure report.

The principle is: **Models propose. Tools decide.**

## Current State

This bootstrap contains deterministic infrastructure only:

- milestone-driven project-control files;
- typed YAML configuration;
- installable `rtl-agent` CLI;
- durable JSON/JSONL run artifacts;
- named command execution with timeout and output logs;
- narrow Git worktree helpers;
- deterministic RTL repository discovery with a versioned JSON repository map;
- deterministic issue parsing with a versioned JSON task contract;
- tests, linting, formatting, and type checking.

It does not yet contain an AI coding agent, model-provider integration, autonomous implementation, review agents, waveform analysis, mutation testing, pull requests, dashboards, queues, databases, or containers.

## Installation

Use Python 3.12 or newer.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Quick Start

```bash
rtl-agent --help
rtl-agent init
rtl-agent inspect-config --config examples/rtl-agent.yaml
rtl-agent inspect-repo --repo examples/simple-rtl --output .rtl-agent/simple-rtl-map.json
rtl-agent parse-issue --issue examples/issues/reset-behavior.md --repository-map .rtl-agent/simple-rtl-map.json --output .rtl-agent/reset-task-contract.json
rtl-agent discover --config examples/rtl-agent.yaml
rtl-agent run-command --config examples/rtl-agent.yaml --command smoke
```

Module invocation also works:

```bash
python3 -m rtl_agent --help
python3 -m rtl_agent inspect-config --config examples/rtl-agent.yaml
python3 -m rtl_agent inspect-repo --repo examples/simple-rtl --output .rtl-agent/simple-rtl-map.json
python3 -m rtl_agent parse-issue --issue examples/issues/reset-behavior.md --repository-map .rtl-agent/simple-rtl-map.json --output .rtl-agent/reset-task-contract.json
python3 -m rtl_agent discover --config examples/rtl-agent.yaml
python3 -m rtl_agent run-command --config examples/rtl-agent.yaml --command smoke
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
