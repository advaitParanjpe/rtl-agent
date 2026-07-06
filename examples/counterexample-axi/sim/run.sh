#!/bin/sh
# Deterministic simulation runner for the counterexample-minimization fixture.
# It compiles the design + program-driven testbench twice — once fault-free (the
# passing reference) and once with the seeded fault — and runs both over the
# materialized stimulus program, dumping passing.vcd and failing.vcd. The final
# faulted run's exit status marks whether the seeded failure reproduced.
# All paths are relative to the command's working directory (the worktree).
set -e
iverilog -g2012 -o pass.vvp rtl/axi_pipe.sv tb/axi_pipe_prog_tb.sv
iverilog -g2012 -DINJECT_FAULT -o fail.vvp rtl/axi_pipe.sv tb/axi_pipe_prog_tb.sv
vvp pass.vvp +vcd=passing.vcd +stim=sim/stimulus.mem
exec vvp fail.vvp +vcd=failing.vcd +stim=sim/stimulus.mem
