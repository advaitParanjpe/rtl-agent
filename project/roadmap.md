# Roadmap

## Product Principle

Models propose. Tools decide. The platform must produce either a reproducible verified Git diff or an honest evidence-backed failure report.

## Stages

1. **Deterministic Orchestration Foundation** - Completed bootstrap: Python project, CLI, typed config, run artifacts, named command execution, Git worktree foundation, validation workflow.
2. **RTL Repository Discovery and Structured Repository Model** - Completed deterministic repository scanner, lightweight SystemVerilog extraction, hierarchy candidate scoring, build-flow evidence discovery, JSON repository map, CLI, run artifacts, and tests.
3. **Issue Parsing and Task Contracts** - Active next milestone: convert bounded engineering issues into explicit typed contracts with scope, invariants, acceptance criteria, validation commands, prohibited shortcuts, and evidence requirements.
4. **Model Provider Abstraction and One Bounded Implementation Agent** - Add interchangeable model adapters and one tightly constrained implementation loop.
5. **Verification Execution and Failure Iteration** - Run configured verification, classify failures, and iterate within limits.
6. **Independent Reviewer** - Add separate review context for diff, evidence, risks, and acceptance criteria.
7. **Waveform and Assertion Triage** - Capture simulator outputs, waveforms, assertions, and failure summaries.
8. **Verification Strength and Mutation Assessment** - Estimate whether tests prove the intended behavior and detect weak validation.
9. **Benchmark Suite** - Evaluate across AXI router, TinyNPU, Sparrow-V, and later Sparrow-Cluster.
10. **CI and Optional Local UI Integrations** - Add reproducible CI workflows and a local evidence browser only when the CLI workflow is stable.

## Current Status

Stages 1 and 2 are complete. Stage 3 is active.
