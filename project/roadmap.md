# Roadmap

## Product Principle

Models propose. Tools decide. The platform must produce either a reproducible verified Git diff or an honest evidence-backed failure report.

## Stages

1. **Deterministic Orchestration Foundation** - Completed bootstrap: Python project, CLI, typed config, run artifacts, named command execution, Git worktree foundation, validation workflow.
2. **RTL Repository Discovery and Structured Repository Model** - Completed deterministic repository scanner, lightweight SystemVerilog extraction, hierarchy candidate scoring, build-flow evidence discovery, JSON repository map, CLI, run artifacts, and tests.
3. **Issue Parsing and Task Contracts** - Completed deterministic issue-to-contract parser with explicit scope, invariants, acceptance criteria, validation commands, prohibited shortcuts, evidence requirements, warnings, CLI, and tests.
4. **Model Provider Abstraction and One Bounded Implementation Agent** - Completed typed provider interface, deterministic stub provider, bounded implementation loop, explicit permissions, structured tool calls, named-command validation, run artifacts, reports, CLI, and tests.
5. **Verification Execution and Failure Iteration** - Completed deterministic validation classification, bounded retry iteration, concise failure evidence, retry/stop decisions, report fields, CLI summary, examples, and tests.
6. **Independent Reviewer** - Completed read-only review reports with deterministic findings, optional provider finding separation, evidence citations, validation gating, scope checks, CLI, examples, and tests.
7. **Waveform and Assertion Triage** - Completed bounded assertion, simulator-context, waveform-reference, and missing-waveform triage from command artifacts with review integration, CLI, examples, and tests.
8. **Verification Strength and Mutation Assessment** - Completed deterministic artifact-only verification-strength scoring, weak validation pattern detection, CLI, README usage, and tests. Mutation execution remains intentionally out of scope.
9. **Benchmark Suite** - Completed deterministic local benchmark manifests, bounded named-command runner, expected-outcome reporting, run artifacts, README usage, and tests.
10. **Evidence Bundle Export** - Completed deterministic local evidence-bundle indexes with artifact provenance, hashes, schema versions, omitted-artifact references, CLI usage, and tests.
11. **Schema Examples and Compatibility Fixtures** - Completed compact checked-in public-schema examples plus compatibility tests that validate them through current typed models.
12. **CLI Documentation Consistency Pass** - Completed README cleanup, installed-CLI command verification, source-tree invocation guidance, and README command help coverage tests.
13. **Packaging Smoke Verification** - Completed bounded local wheel/install smoke verification for console-script and module invocation as part of the canonical check workflow.
14. **Compact End-to-End Example Check** - Completed compact local scripted example check across checked-in fixtures, deterministic implementation retry, review, verification-strength, benchmark, evidence export, and schema-backed artifact assertions.
15. **Failure Report Example Check** - Completed compact local scripted example check for the honest terminal-failure path, failed report artifact, command evidence, review disposition, verification-strength result, and evidence-bundle export.
16. **Tool Failure Report Example Check** - Completed compact local scripted example check for deterministic structured-tool failure reporting, failed tool-result evidence, absent validation execution, review disposition, verification-strength result, and evidence-bundle export.
17. **Example Script Helper Consolidation** - Completed shared `scripts/_example_check.py` helper for repository root, venv-aware interpreter, source-path setup, and the `run_cli` CLI subprocess helper; the end-to-end, failure, and tool-failure example scripts now reuse it without changing workflow behavior.
18. **No-Change Implementation Example Check** - Completed compact local example check for the deterministic no-op (no-change) implementation path, covering a successful `replace_text` application with identical old/new content that still ends in an unacceptable review and insufficient verification strength because no validation command ran.
19. **VCD Failure Window Extraction** - Completed the first deterministic RTL failure-intelligence capability: typed, versioned waveform-slice schema, deterministic textual-VCD parser and bounded window extractor, `extract-waveform-window` CLI, source metadata with SHA-256 and parse statistics, accurate scalar/vector/`x`/`z` representation, pre-window initial values, optional triage-report source resolution, checked-in VCD fixtures, README example, and tests. No causal or root-cause interpretation; textual VCD only.
20. **Assertion-to-Waveform Failure Linking** - Completed the deterministic linkage from triaged assertion failures to bounded VCD slices: typed, versioned linkage report, `link-assertion-waveform` CLI, stable assertion selection by id/index, timescale-aware simulator-time-to-tick conversion, reuse of the existing window extractor (via a shared `read_vcd_timescale` helper), honest failures for missing/ambiguous timestamps, multiple/missing/unsupported/malformed waveforms, a runnable triage fixture, README example, and tests. Never infers root cause; never silently resolves ambiguity.
21. **Waveform Evidence Bundle Integration** - Completed: the deterministic evidence-bundle exporter now recognizes, classifies, hashes, and records schema versions for waveform-slice and assertion-link artifacts under a run directory, reusing existing provenance and omitted-content handling with no export redesign or artifact-schema change.
22. **Automatic Relevant-Signal Reduction** - Active next milestone: deterministically reduce a waveform slice's signal set to a bounded, evidence-ranked relevant subset for a failure using only explicit textual and transition evidence (assertion-named signals, in-window transitions, `x`/`z` presence, hierarchical proximity to the assertion scope). Typed versioned report, CLI, fixtures/tests, README example. No dependency tracing, semantic interpretation, source localization, stimulus minimization, or causal claims.
23. **Prohibited-Shortcut Review Finding Example Check** - Deferred: add a compact local example check exercising the existing but currently untested `det-prohibited-shortcut-N` review finding, using a deliberate diff that textually conflicts with a task-contract prohibited shortcut. Remains intentionally deferred.

## Current Status

Stages 1 through 21 are complete. Stage 22 is active. Stage 23 is deferred.
