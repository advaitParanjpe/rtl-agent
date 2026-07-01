# Roadmap

## Product Principle

Models propose. Tools decide. The platform must produce either a reproducible verified Git diff or an honest evidence-backed failure report.

## Stages

1. **Deterministic Orchestration Foundation** - Completed bootstrap: Python project, CLI, typed config, run artifacts, named command execution, Git worktree foundation, validation workflow.
2. **RTL Repository Discovery and Structured Repository Model** - Active next milestone: efficiently inspect Verilog/SystemVerilog repositories and emit a machine-readable map of sources, tests, tops, packages, interfaces, and flows.
3. **Issue Parsing and Task Contracts** - Convert bounded engineering issues into explicit scope, acceptance criteria, risks, and validation plans.
4. **Model Provider Abstraction and One Bounded Implementation Agent** - Add interchangeable model adapters and one tightly constrained implementation loop.
5. **Verification Execution and Failure Iteration** - Run configured verification, classify failures, and iterate within limits.
6. **Independent Reviewer** - Add separate review context for diff, evidence, risks, and acceptance criteria.
7. **Waveform and Assertion Triage** - Capture simulator outputs, waveforms, assertions, and failure summaries.
8. **Verification Strength and Mutation Assessment** - Estimate whether tests prove the intended behavior and detect weak validation.
9. **Benchmark Suite** - Evaluate across AXI router, TinyNPU, Sparrow-V, and later Sparrow-Cluster.
10. **CI and Optional Local UI Integrations** - Add reproducible CI workflows and a local evidence browser only when the CLI workflow is stable.

## Current Status

Stage 1 is complete. Stage 2 is active.
