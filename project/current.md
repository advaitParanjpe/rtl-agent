# External RTL Port-Connection Evidence Follow-up

## Objective

Extend the external verilog-axis validation to real instance port-connection evidence across the existing vendored hierarchy while preserving textual evidence and honest unresolved cases.

## Scope

- Use the existing vendored verilog-axis subset; do not fetch or vendor new upstream files unless a minimal, attributed addition is genuinely required.
- Identify representative real instance port connections in the existing hierarchy (`axis_arb_mux` to `arbiter`, and `arbiter` to `priority_encoder`) and validate how existing `trace-drivers` records them.
- Add or adjust focused assertions/tests so port-connection evidence cites real source files, lines, ports, expressions, and unresolved identifiers honestly.
- Preserve existing schemas and CLI behavior where practical.
- Keep the check deterministic, hermetic, and bounded.

## Acceptance Criteria

- Real external RTL port-connection evidence is validated without fixture-specific or AXI-specific product heuristics.
- Existing ambiguity and unresolved behavior remains honest; no semantic elaboration or connectivity inference is added.
- External-repository, discovery, signal-source mapping, driver-tracing, failure-intelligence, example, packaging, and workflow-portability checks continue to pass.

## Required Validation Commands

- `python3 scripts/check.py`
- `git diff --check`
- `git status --short`

## Exclusions

- Do not fetch/clone/download anything during the default validation run; no network access at check time.
- Do not add semantic elaboration, preprocessing, simulator requirements, causal claims, root-cause conclusions, model-provider integration, or a broad dependency-graph redesign.
- Do not add a simulator requirement for this milestone, real model-provider integration, CI automation, containers, dashboards, databases, queues, or a web UI.
- Do not hard-code external-repository expected answers into product services or create a parallel analysis path.
- Do not implement the still-deferred Prohibited-Shortcut Review Finding Example Check in this milestone.

## Completion State

Active.
