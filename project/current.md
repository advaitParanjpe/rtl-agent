# External RTL Mapping Accuracy Follow-up

## Objective

Fix the real-code accuracy gaps exposed by the external verilog-axis repository pilot while preserving existing schemas and honest ambiguity reporting.

## Scope

- Correct declaration line reporting so module/interface/package declaration locations use the keyword/name line rather than leading blank or masked comment lines.
- Improve signal-source mapping primary candidate selection for nested instance paths such as `tb.axis_arb_mux.arbiter.grant_reg`, so the declaring inner module is preferred when evidence supports it while ambiguity is still preserved.
- Prevent driver-trace dependency expansion from conflating same-named identifiers across unrelated files/modules.
- Add focused tests using existing fixtures and the vendored external snapshot where useful.
- Keep artifact schemas, CLI command names, provider behavior, and workflow features unchanged unless a tiny internal model field is strictly required and remains backward compatible.

## Acceptance Criteria

- Existing synthetic ambiguity behavior remains honest; no false-confident single answer is introduced.
- The external verilog-axis check can assert the corrected declaration line and nested primary mapping behavior without fixture-specific special cases.
- Dependency edges for same-named identifiers remain scoped to the relevant declaring file/module where the available textual evidence supports that scope.
- Existing discovery, signal-source mapping, driver-tracing, failure-intelligence, external-repository, example, packaging, and workflow-portability checks continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not fetch/clone/download anything during the default validation run; no network access at check time.
- Do not add semantic elaboration, simulator requirements, causal claims, root-cause conclusions, model-provider integration, or a broad dependency-graph redesign.
- Do not add a simulator requirement for this milestone, real model-provider integration, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not hard-code external-repository expected answers into product services or create a parallel analysis path.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
