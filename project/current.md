# RTL Repository Discovery and Structured Repository Model

## Objective

Inspect a Verilog/SystemVerilog repository efficiently and generate a machine-readable repository map covering source files, testbenches, build commands, top-level candidates, packages/interfaces, and available verification or synthesis flows.

## Scope

- Add deterministic repository discovery invoked from the CLI.
- Scan only configured allowed paths and respect protected paths.
- Identify Verilog/SystemVerilog source files, likely testbenches, package/interface declarations, module declarations, and top-level candidates with lightweight parsing.
- Detect common verification or synthesis entry points such as Makefiles, FuseSoC cores, scripts, simulator command files, and CI workflows without executing them.
- Persist a versioned repository map artifact as stable JSON.
- Add focused tests using temporary RTL repositories.

## Deliverables

- Discovery models and scanner modules under `src/rtl_agent/`.
- CLI command for repository discovery.
- JSON artifact schema for the repository map.
- Example or fixture RTL repository snippets in tests only.
- Updated README quick-start section for discovery.

## Acceptance Criteria

- Discovery produces stable JSON with paths relative to the inspected repository root.
- Discovery refuses paths outside configured allowed working paths and skips protected paths.
- Tests cover source classification, declaration extraction, top-level candidate heuristics, flow detection, and artifact writing.
- Existing command-runner and worktree tests continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `python3 -m rtl_agent discover --config examples/rtl-agent.yaml`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not execute EDA tools during discovery.
- Do not add model-provider or autonomous implementation-agent behavior.
- Do not implement full SystemVerilog parsing.
- Do not create commits, remotes, pull requests, databases, queues, dashboards, or containers.

## Completion State

Active.
