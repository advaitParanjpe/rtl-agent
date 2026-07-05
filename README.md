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

It also runs `scripts/e2e_example_check.py`, a compact local example check that copies the checked-in fixtures to a temporary workspace, exercises inspect, parse, bounded implementation with retry, triage, review, verification-strength, benchmark, and evidence export stages, and verifies stable artifact statuses through the existing schemas. `scripts/failure_example_check.py` covers the matching bounded terminal-failure path, `scripts/tool_failure_example_check.py` covers deterministic structured-tool failure reporting, and `scripts/no_change_example_check.py` covers a successful no-op edit that still ends in an unacceptable review and insufficient verification strength because no validation command was executed. `scripts/failure_intelligence_example_check.py` exercises the failure-intelligence pipeline end-to-end — waveform extraction, relevant-signal reduction, passing/failing comparison, repository discovery, signal-source mapping, static driver tracing, failure-divergence graph, and evidence-bundle export — over the checked-in waveform and RTL fixtures. `scripts/axi_router_seeded_failure_check.py` validates the same pipeline against a compact AXI-stream-router fixture (`examples/axi-stream-router/`) whose RTL drives real internal signals: it seeds a payload-instability-under-backpressure failure into the failing VCD and asserts the pipeline identifies `payload_out` as the earliest divergence, maps it to the router module, extracts the real `assign payload_out = payload_reg;` driver and its dependency chain into a connected divergence graph and failure report, exports and validates a portable package, and preserves ambiguity without claiming a root cause. `scripts/axi_router_repository_pilot_check.py` scales the same validation to a multi-file hierarchical repository (`examples/axi-router-repo/`) — a top module instantiating two child modules (`axi_ingress` and `axi_route`) across separate files — where a seeded fault corrupts the staged payload in the ingress child and propagates to the routed output in the route child; it asserts the pipeline resolves each signal to its own child file, reconstructs the `payload_out → payload_staged → payload_in` driver chain across module boundaries with edges cited to two different files, and localizes the earliest divergence without any new analysis behavior. `scripts/axi_router_ambiguity_pilot_check.py` is a robustness pilot over a deliberately ambiguous repository (`examples/axi-router-ambiguity/`) — a child module `lane` defined in two separate files and instantiated more than once, so the internal signal names are non-unique across files — and asserts the pipeline reports the divergent signal's source mapping as `ambiguous`, preserves both candidate files through the driver trace, divergence graph, and failure report, and explicitly records the ambiguity rather than selecting a false-confident single answer. `scripts/axi_router_simulated_failure_check.py` goes a step further and generates its waveforms with a real open-source simulator instead of authoring them: it compiles a checked-in design and testbench (`examples/axi-router-sim/`) with Icarus Verilog and runs the same stimulus twice — once clean and once with a compile-time-defined seeded fault — to produce a genuine passing-vs-failing VCD pair, then drives the existing pipeline over it and asserts the seeded divergence is localized to `axi_pipe.sv`. The simulator is a fixture-generation/dev dependency only: when `iverilog`/`vvp` are not on `PATH` the check skips cleanly, so the default validation suite stays hermetic and the simulator is never a product runtime dependency. `scripts/axi_router_simulated_multimodule_check.py` combines both threads — a real simulator over a hierarchical, multi-file design (`examples/axi-router-sim-hier/`): a top module instantiates `ingress` and `route` child modules from separate files, and the compile-time seeded fault corrupts the staged payload in the ingress child, which the route child registers into the output one cycle later. It asserts the existing pipeline finds the earliest divergence in `ingress.sv`, maps each signal to its own child file, reconstructs the cross-module `payload_out → payload_staged → data_in` driver chain with edges cited across both files, cites both source files in the failure report, and exports a verified package — with the same gating so it too is skipped when the simulator is absent. `scripts/axi_router_simulated_triage_check.py` wires the *whole* existing flow together over a genuinely failing simulation (`examples/axi-router-sim-triage/`): the testbench emits a stable, timestamped `assertion payload_stable failed at time=45 ns` marker and terminates with a non-zero status, the run is executed through the existing command runner (capturing its real logs and VCD), `triage-command` recovers the assertion timestamp and referenced waveform, `link-assertion-waveform` derives the failure timestamp (`45 ns` → tick 45) and the VCD path — the user provides neither — and those derived values drive the existing failure-intelligence orchestration, which localizes the divergence to `axi_pipe.sv`, inspects the run, and exports a verified package; the triaged failure and the localized divergence are asserted to describe one run. Same simulator gating applies. `scripts/external_axi_router_repo_check.py` validates the discovery, signal-source-mapping, and driver-tracing services against real third-party RTL: a minimal, pinned snapshot of [alexforencich/verilog-axis](https://github.com/alexforencich/verilog-axis) (MIT, Copyright (c) 2014-2018 Alex Forencich) is vendored verbatim under `examples/external/verilog-axis/upstream/` — the arbitrated AXI-stream mux router path (`axis_arb_mux` → `arbiter` → `priority_encoder`) plus `axis_demux` — so canonical validation performs no network access. The check first enforces provenance (pinned commit, license, attribution, and per-file SHA-256 from `PROVENANCE.json`, plus no unlisted upstream files) so the snapshot cannot silently drift, then asserts honest behaviour on the real hierarchy: module discovery and instantiation hierarchy, exact mapping where the waveform scope names the module, preserved multi-candidate evidence on nested instance paths, honest unresolved results, and real continuous/procedural driver statements at their actual source lines. It skips cleanly when the snapshot is absent, and `scripts/vendor_verilog_axis.py` is a manual, network-using re-vendoring helper that is never part of the default suite.

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

## Assertion-to-Waveform Failure Linking

`link-assertion-waveform` connects a triaged assertion failure to a bounded VCD slice, so you do not have to supply the failure timestamp and waveform path by hand:

```bash
rtl-agent link-assertion-waveform \
  --triage-report examples/waveforms/triage-report.json \
  --assertion-id assertion-0 \
  --before 15 \
  --after 5 \
  --signal-prefix top.dut \
  --slice-output .rtl-agent/waveform-slice.json \
  --output .rtl-agent/assertion-link.json
```

The command selects one assertion finding by stable id (`--assertion-id assertion-<index>`) or `--assertion-index`, resolves its associated VCD waveform reference, converts the assertion's simulator time into VCD tick units using the waveform's `$timescale`, and then invokes the existing waveform-window extractor. It emits a versioned linkage report recording the selected assertion, source triage report, selected waveform, timestamp-conversion details, generated waveform-slice path and hash, warnings, and unresolved ambiguities. It fails honestly when no assertion is selected, the assertion has no usable timestamp, no compatible textual VCD is associated, the timescale conversion is ambiguous, or the waveform is missing or malformed, and it never silently chooses between multiple candidate waveforms (use `--waveform-path` to disambiguate). It never infers root cause.

## Relevant-Signal Reduction

`reduce-signals` narrows a waveform slice to a bounded, evidence-ranked subset of signals most relevant to a failure, and writes a reduced slice alongside a scored report:

```bash
rtl-agent extract-waveform-window \
  --vcd examples/waveforms/failure.vcd \
  --failure-time 40 --before 15 --after 5 \
  --output .rtl-agent/waveform-slice.json

rtl-agent reduce-signals \
  --waveform-slice .rtl-agent/waveform-slice.json \
  --assertion-signal top.dut.valid \
  --reduced-slice-output .rtl-agent/reduced-slice.json \
  --output .rtl-agent/relevant-signals.json
```

Ranking is deterministic and uses only explicit textual and transition evidence already in the slice: whether the signal is named by the assertion (`--assertion-signal`/`--assertion-summary`, or an `--assertion-link` report), whether it has transitions in the window or exactly at the failure time, whether it carries unknown (`x`) or high-impedance (`z`) values, and whether it shares the assertion signal's parent scope. Each retained signal cites its matched criteria and a deterministic score; the reduced set is a strict subset of the input slice, bounded by `--max-signals`. It never traces signal dependencies, interprets waveform semantics, localizes RTL source, or claims root cause.

## Passing-vs-Failing Waveform Comparison

`compare-waveforms` compares a failing waveform slice against a passing (reference) slice over their shared signals and common time window, and writes a typed comparison report:

```bash
rtl-agent compare-waveforms \
  --failing-slice .rtl-agent/failing-slice.json \
  --passing-slice .rtl-agent/passing-slice.json \
  --output .rtl-agent/waveform-comparison.json
```

For each signal present in both slices it reconstructs the value timeline (initial value plus in-window transitions) and reports whether the timelines are identical, the first divergence time and the value on each side there, per-side transition counts, `x`/`z` differences, and the divergence duration and intervals. It also reports signals added or removed relative to the reference, the global earliest divergence, and a deterministic ranking of the most divergent signals. The time basis is explicit: identical timescales compare in shared ticks, differing-but-parseable timescales are normalized to femtoseconds (recorded in `time_basis`), and ambiguous or incompatible timescales are compared as raw ticks with a warning. Incompatible timescales, window mismatches, ambiguous duplicate names, and missing overlap are reported as warnings; incompatible traces are never silently aligned. It never claims causal meaning or localizes RTL source.

## Signal-to-RTL Source Mapping

`map-signals` maps hierarchical waveform signal names to candidate RTL declarations from an existing repository map:

```bash
rtl-agent inspect-repo \
  --repo examples/simple-rtl \
  --config examples/simple-rtl-agent.yaml \
  --output .rtl-agent/repo-map.json

rtl-agent map-signals \
  --repository-map .rtl-agent/repo-map.json \
  --signal top.u_child.clk \
  --signal top \
  --output .rtl-agent/signal-source-map.json
```

Signals can be given directly with `--signal`, or read from a `--waveform-slice` or a `--comparison` report. For each signal the command matches the hierarchical path components and leaf name against declaration names in the repository map (`module`/`interface`/`package`/`program`/`checker`, with file and line) and classifies the result as `exact` (an unambiguous scope-component match), `probable` (a weaker leaf or case-insensitive match), `ambiguous` (a name with multiple declarations — all candidates preserved), or `unresolved`. Every candidate carries a score and an explicit match reason. It consumes the existing repository-map and waveform artifacts only; it performs no semantic elaboration, preprocessing, connectivity or driver tracing, and makes no causal claims.

## Static RTL Driver and Dependency Tracing

`trace-drivers` extracts bounded, textual driver and dependency evidence for mapped signals from a signal-source-map report and a repository map:

```bash
rtl-agent trace-drivers \
  --signal-source-map .rtl-agent/signal-source-map.json \
  --repository-map .rtl-agent/repo-map.json \
  --max-depth 2 \
  --max-nodes 64 \
  --output .rtl-agent/driver-trace.json
```

For each mapped signal it scans the declaring RTL file(s) for statements that reference the signal's leaf name — continuous assignments (`assign`), procedural assignments (`<=`/`=`), and port connections — recording the file, line, statement kind, bounded text, LHS/RHS identifiers, the enclosing declaration, and the nearest conditional guard where practical. It then performs a bounded upstream dependency expansion (configurable `--max-depth` and `--max-nodes`) over the referenced right-hand-side identifiers, emitting edges labeled `textual` (identifier appears in a matched assignment) or `inferred_textual` (name-based port connection). Multiple drivers are all preserved and never collapsed; unresolved identifiers (inputs, constants, undriven nets) are reported explicitly. The scan is purely textual — it performs no elaboration, preprocessing, generate expansion, simulation, semantic connectivity, or causal reasoning.

## Failure Divergence Graph

`divergence-graph` composes the prior comparison, signal-source-map, and driver-trace artifacts into a single bounded graph rooted at the diverging signals:

```bash
rtl-agent divergence-graph \
  --comparison .rtl-agent/waveform-comparison.json \
  --signal-source-map .rtl-agent/signal-source-map.json \
  --driver-trace .rtl-agent/driver-trace.json \
  --max-depth 3 \
  --max-nodes 128 \
  --output .rtl-agent/divergence-graph.json
```

Root nodes are the comparison's diverging signals (mapped to their leaf identifiers), carrying their first divergence time, values, and divergence score. Each node also composes its mapping status and declaration location (from the signal-source map) and its driver-resolution status (from the driver trace). Edges are the driver-trace dependency edges, each retaining its `textual` / `inferred_textual` label and citing the source file and line. The graph is bounded from the roots by `--max-depth` and `--max-nodes` (truncation recorded), multiple drivers and unresolved identifiers are preserved, and cross-artifact mismatches are warned about. It is purely compositional — it performs no new RTL scanning, elaboration, or semantic dataflow, and makes no causal or root-cause claims.

## Failure Report Synthesis

`synthesize-failure-report` composes the failure-intelligence artifacts into a single evidence-cited failure report, emitting both a typed JSON report and a concise engineer-facing Markdown summary:

```bash
rtl-agent synthesize-failure-report \
  --divergence-graph .rtl-agent/divergence-graph.json \
  --reduction .rtl-agent/relevant-signals.json \
  --driver-trace .rtl-agent/driver-trace.json \
  --verification-strength .rtl-agent/verification-strength.json \
  --review .rtl-agent/review-report.json \
  --output .rtl-agent/failure-report.json
```

Only `--divergence-graph` is required; the reduction, driver-trace, verification-strength, and review inputs are optional. The report separates observed failure facts, earliest waveform divergence, ranked relevant signals, candidate RTL source locations, textual driver/dependency evidence, unresolved and ambiguous evidence, verification/review status, and artifact provenance (paths, schema versions, and SHA-256 hashes). Every statement cites its originating artifact, and the report never labels a signal or RTL statement as a root cause. The Markdown summary is written next to the JSON output (`--markdown-output` overrides its path). It is purely compositional over the existing artifacts — no new waveform, dependency, or semantic analysis.

## Failure Intelligence Run Orchestration

`run-failure-intelligence` invokes the failure-intelligence stages in one fixed sequence and writes every artifact under a single run directory:

```bash
rtl-agent run-failure-intelligence \
  --failing-vcd examples/waveforms/failure.vcd \
  --passing-vcd examples/waveforms/passing.vcd \
  --repo examples/simple-rtl \
  --config examples/simple-rtl-agent.yaml \
  --failure-time 40 --before 15 --after 15 \
  --run-root .rtl-agent/runs --run-id my-run
```

The command runs waveform extraction (failing and passing), comparison, repository discovery, signal-source mapping, driver tracing, divergence-graph composition, relevant-signal reduction, and failure-report synthesis, reusing each stage's existing service (it never reimplements a stage). It creates a `RunStore` run directory, persists every intermediate artifact under it, and emits one typed, versioned `run-manifest.json` recording each stage's disposition, inputs, outputs, duration, warnings, and failure reason, plus a linked list of all generated artifacts (each with its SHA-256). When every stage succeeds it produces the final JSON and Markdown failure report; on a terminal stage error it stops honestly, preserves the completed intermediate artifacts, records the failing stage, marks the remaining stages skipped, still writes the manifest, and exits non-zero. Optional `--verification-strength` and `--review` inputs flow through to report synthesis. Runs are deterministic for identical inputs apart from the run id and timestamps.

Re-run an existing run directory with `--resume` (reuse valid stage artifacts, running only the remaining or invalid stages) or `--replay-from <stage>` (regenerate from an explicitly named stage onward). Before reusing any artifact the run verifies its existence, its recorded SHA-256, its typed model and supported schema version, and that the prior run's inputs match the current inputs; a missing, stale, incompatible, or unprovenanced artifact is regenerated instead of trusted, and regenerating any stage invalidates and regenerates the stages after it. Each stage's disposition is recorded as `executed`, `reused`, `regenerated`, `skipped`, or `failed`, with an event explaining every reuse or invalidation decision. Requesting a replay stage that does not exist fails clearly.

The run directory is portable: artifacts inside it are recorded with run-relative paths (and each stage input is marked `run_relative` or `external`), so a run directory can be moved or copied and then inspected, resumed, or replayed from its new location — validation resolves run-relative paths against the current directory and still enforces hashes and typed-model checks. External inputs (the source VCDs, the repository, and any verification/review reports) are recorded explicitly with their absolute paths and existence; they must be supplied again and are never silently reinterpreted, and a recorded path that escapes the run directory is rejected rather than resolved.

`inspect-run` validates an existing run directory against its manifest, read-only, without re-running anything:

```bash
rtl-agent inspect-run --run-dir .rtl-agent/runs/my-run --output .rtl-agent/inspection.json
```

For each recorded artifact it resolves the run-relative path against the actual directory (rejecting traversal) and reports one of `valid`, `missing`, `hash_mismatch`, `schema_malformed`, `schema_unsupported`, or `unsafe_path`; each stage is reported as `valid`, `incomplete`, `stale` (own outputs valid but an upstream stage is invalid), or `invalid`. It also re-checks whether the recorded external inputs still exist. The command prints a concise summary and, with `--output`, writes a typed, versioned JSON inspection report; it exits non-zero when the run is invalid (still writing the report), and never modifies, regenerates, deletes, migrates, resumes, or replays anything.

`fingerprint-run` reads an existing run directory and writes a stable, typed failure fingerprint without re-running analysis:

```bash
rtl-agent fingerprint-run --run-dir .rtl-agent/runs/my-run --output .rtl-agent/fingerprints/my-run.json
```

`compare-fingerprints` compares two fingerprint JSON files and reports exact matches, same likely observed failure family, related-but-different failures, or insufficient evidence:

```bash
rtl-agent compare-fingerprints \
  --left .rtl-agent/fingerprints/baseline.json \
  --right .rtl-agent/fingerprints/intervention.json \
  --output .rtl-agent/fingerprints/comparison.json
```

Fingerprints are deterministic summaries of existing evidence: assertion identity, normalized failure-time characteristics, earliest divergent signals, ranked divergent/relevant signals, transition and `x`/`z` characteristics, mapped source/dependency shape, ambiguity/unresolved markers, divergence-graph shape, and terminal outcome. The digest excludes volatile metadata such as run IDs, execution timestamps, absolute paths, durations, UUID-like command IDs, and artifact hashes. It is a grouping/comparison aid, not a causal or root-cause claim.

`cluster-failures` groups many existing fingerprints from a regression run into a small set of recurring observed failure families, read-only and deterministically, without rerunning anything:

```bash
rtl-agent cluster-failures \
  --fingerprint run-001/fingerprint.json \
  --fingerprint run-002/fingerprint.json \
  --fingerprint run-003/fingerprint.json \
  --output regression-families

rtl-agent cluster-failures --fingerprint-dir collected-fingerprints --output regression-families
```

It reuses the existing fingerprint comparison semantics: primary family membership is equal `family_digest` (a stable, transitive rule), exact duplicates are equal `exact_digest` within a family, insufficient-evidence fingerprints are reported separately (never forced into a confident family), single-member families are unique outliers, and distinct families that still share evidence are recorded as related-family links. Each family gets one deterministic representative (most complete evidence; ties broken by canonical fields then digest, with the reason recorded) plus a concise evidence-grounded description, observed time range, assertion identities, earliest-divergence signals, relevant-signal union/intersection, mapped sources, and ambiguity markers. `--strict` fails on any invalid input; the default permissive mode excludes invalid inputs and records warnings. Counterfactual experiment reports may be supplied directly — their baseline and intervention runs are fingerprinted via the existing service. The command emits a typed JSON report, a concise Markdown report, and a terminal summary (total inputs, valid fingerprints, family count, exact duplicates, outliers, insufficient-evidence cases, excluded inputs). Grouping is order-independent and never labels a family a root cause. `scripts/failure_family_cluster_check.py` demonstrates nine regression seeds across three mechanisms collapsing into three families.

`export-failure-package` packages a validated run directory into a single self-contained, portable failure package (read-only):

```bash
rtl-agent export-failure-package --run-dir .rtl-agent/runs/my-run --output .rtl-agent/packages/my-run
```

Export is inspection-gated: it runs the same validation and refuses an invalid run by default. A failed-but-internally-consistent run (a run that ended in an honest terminal failure but whose recorded artifacts are all valid) can be exported only with `--allow-failed`, and the package is clearly marked `failed`. The package contains the run manifest, the freshly written inspection report, the JSON and Markdown failure report, and every validated, manifest-referenced evidence artifact at its run-relative path under `run/`; external inputs, run event logs, caches, and unrelated files are never included, and unsafe or missing artifacts are never packaged. It emits a typed, versioned `package-manifest.json` recording each file's package-relative path, source role, size, SHA-256, schema version (where applicable), and original run-relative provenance, and verifies every packaged file's hash before reporting success. All package paths are relative and traversal-safe, and the source run directory is never modified.

`run-counterfactual` runs the first experimental counterfactual-RTL-debugging capability: given a validated baseline failure-intelligence run and one user-supplied manual intervention, it applies the intervention in an isolated Git worktree, reruns a named configured command, analyzes the result with the existing pipeline, compares against the baseline, and emits a typed, versioned experiment report (plus Markdown):

```bash
rtl-agent run-counterfactual \
  --baseline-run .rtl-agent/runs/failure-001 \
  --repo ../axi-router \
  --config rtl-agent.yaml \
  --command seeded-failure \
  --patch intervention.diff \
  --allowed-file rtl/axi_pipe.sv \
  --output-run .rtl-agent/experiments/experiment-001
```

The intervention is one unified diff (`--patch`) or one structured `replace_text` edit (`--replace-file/--replace-old/--replace-new`), restricted to explicitly allowed files (`--allowed-file`), applied only inside the worktree — the baseline repository is never modified and nothing is committed, pushed, or altered on any remote; an unclean apply or a disallowed file fails honestly. The runner inspects and refuses an invalid baseline, enforces the command timeout, captures stdout/stderr/exit-code/duration/logs and the generated waveform, reuses the existing command runner, worktree, triage, waveform, comparison, failure-intelligence, and inspection services, and deterministically classifies the outcome as one of `failure_removed`, `failure_delayed`, `failure_advanced`, `failure_changed`, `no_observable_effect`, `new_failure_introduced`, `experiment_failed`, or `insufficient_evidence` — based only on explicit evidence (the original divergent signals and timestamp, command status, and artifact validity). The report preserves all intermediate evidence and states explicitly that it records an intervention outcome, not proven causality. `scripts/counterfactual_pilot_check.py` is a gated Icarus-backed pilot that removes a seeded backpressure fault via a patch and asserts the failure is removed while the source repository stays byte-for-byte unchanged; it skips cleanly when the simulator is absent.

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

The bundle preserves artifact provenance, relative paths, SHA-256 hashes, byte sizes, and JSON schema versions where present. It recognizes the typed reports found under a run directory — including the failure-intelligence artifacts (waveform slice, assertion-to-waveform linkage, relevant-signal reduction, waveform comparison, signal-source map, driver trace, and failure divergence graph) — and records their kinds, while unknown JSON and non-JSON artifacts are still hashed and referenced. It references command logs and waveform-like files as omitted local artifacts instead of copying their contents. Missing optional artifacts are warnings; missing required `run.json` produces a failed export result. The exporter does not execute commands, mutate source files, call providers, upload artifacts, sign bundles, add cloud storage, or include large logs and waveforms.

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
