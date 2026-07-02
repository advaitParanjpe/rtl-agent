# Preserve Example Define

## Requested Behavior

- Keep `rtl/defs.svh` defining `SIMPLE_RTL_EXAMPLE` as `1`.

## Scope

- `rtl/defs.svh`

## Acceptance Criteria

- [ ] `rtl/defs.svh` contains `` `define SIMPLE_RTL_EXAMPLE 1 ``.

## Validation Commands

```bash
rtl-agent run-command --config examples/simple-rtl-agent.yaml --command check-define
```

## Evidence Requirements

- Include validation command results in the final handoff.
