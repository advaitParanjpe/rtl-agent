# Counterexample AXI fixture (project-authored)

Compact, project-owned fixture for the Counterexample Stimulus Minimization
Foundation pilot. A small AXI-stream pipeline stage (`rtl/axi_pipe.sv`, with the
seeded fault behind `` `ifdef INJECT_FAULT ``) corrupts its held payload to `x`
when a stall immediately follows a send, so the minimal failing subsequence is
`send` then `stall`.

- `tb/axi_pipe_prog_tb.sv` — program-driven testbench: it loads an ordered
  stimulus program from a hex memory file (materialized by the minimizer from
  the structured stimulus JSON) and applies one action per cycle
  (`send` / `stall` / `idle`), dumps a VCD, emits a stable timestamped marker on
  the observed corruption, and terminates non-zero.
- `sim/run.sh` — the named `structured-failure` command: compiles fault-free and
  faulted builds and runs both over the materialized `sim/stimulus.mem`, dumping
  `passing.vcd` and `failing.vcd`.
- `sim/stimulus.mem` — the hex program for the checked-in `failing-stimulus.json`
  (regenerate with `rtl_agent.stimulus.to_hex_program`).
- `rtl-agent.yaml` — config exposing the `structured-failure` command.
- `failing-stimulus.json` — the baseline structured stimulus: three warmup idles,
  the `send`/`stall` failing core, and two cooldown idles. The minimizer removes
  the irrelevant idles while preserving the observed failure family; one warmup
  is retained because removing it would push the fault into the reset window and
  change the observed waveform.

The pilot copies this fixture into a temporary Git repository and never modifies
these checked-in files. It requires Icarus Verilog and is skipped when the
simulator is absent.
