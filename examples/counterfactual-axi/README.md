# Counterfactual AXI fixture (project-authored)

Compact, project-owned fixture for the Manual Counterfactual Intervention Runner
pilot. It is a small AXI-stream pipeline stage whose held payload is corrupted
to `x` under backpressure when compiled with the `INJECT_FAULT` define (the
seeded baseline failure).

Contents:

- `rtl/axi_pipe.sv` — the design (fault behind `` `ifdef INJECT_FAULT ``).
- `tb/axi_pipe_tb.sv` — testbench: dumps a VCD, emits a stable timestamped
  assertion marker on the observed corruption, and terminates non-zero.
- `sim/run.sh` — the named `seeded-failure` command: compiles with the fault and
  runs the simulation, dumping `sim.vcd`.
- `rtl-agent.yaml` — config exposing the `seeded-failure` command.
- `interventions/remove-fault.diff` — a unified diff that replaces the corrupting
  `payload_reg <= 'x;` assignment with a stable hold, i.e. the manual
  intervention exercised by the pilot.

The pilot copies this fixture into a temporary Git repository (so the worktree
machinery has a real repo to branch from) and never modifies these checked-in
files. It requires Icarus Verilog and is skipped when the simulator is absent.
