# Fix Reset Behavior

## Requested Behavior

- Reset must clear the output-valid register in `rtl/top.sv`.

## Scope

- `rtl/top.sv`
- `tb/top_tb.sv`

## Invariants

- Do not change the module names in the example RTL repository.

## Acceptance Criteria

- [ ] Reset behavior is explicitly covered by a test.
- [ ] Existing discovery examples still run.

## Validation Commands

```bash
python3 scripts/check.py
rtl-agent inspect-repo --repo examples/simple-rtl --output .rtl-agent/simple-rtl-map.json
```

## Prohibited Shortcuts

- Do not remove the example testbench to make discovery pass.

## Evidence Requirements

- Include validation command results in the final handoff.
