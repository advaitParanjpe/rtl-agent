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
- tests, linting, formatting, and type checking.

It does not yet contain an AI coding agent, model-provider integration, RTL discovery, EDA-specific parsing, autonomous branch management, commits, pushes, pull requests, dashboards, queues, databases, or containers.

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
rtl-agent run-command --config examples/rtl-agent.yaml --command smoke
```

Module invocation also works:

```bash
python3 -m rtl_agent --help
python3 -m rtl_agent inspect-config --config examples/rtl-agent.yaml
python3 -m rtl_agent run-command --config examples/rtl-agent.yaml --command smoke
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

Commands are executed by name only. The runner does not invoke a shell.

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
