#!/bin/sh
# Deterministic simulation runner for the counterfactual fixture. It compiles the
# design and testbench with the seeded fault enabled and runs the simulation,
# dumping a VCD next to the run. The VCD path is echoed by the simulator so the
# existing triage service can recover the generated waveform. A non-zero exit
# (the testbench's terminal $fatal on the seeded failure) marks a failing run.
set -e
iverilog -g2012 -DINJECT_FAULT -o "$PWD/sim.vvp" rtl/axi_pipe.sv tb/axi_pipe_tb.sv
exec vvp "$PWD/sim.vvp" "+vcd=$PWD/sim.vcd"
