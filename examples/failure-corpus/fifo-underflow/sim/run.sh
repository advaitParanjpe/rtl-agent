#!/bin/sh
# All paths are relative to the command's working directory (the worktree).
set -e
iverilog -g2012 -o pass.vvp rtl/fifo_underflow.sv tb/fifo_underflow_tb.sv
iverilog -g2012 -DINJECT_FAULT -o fail.vvp rtl/fifo_underflow.sv tb/fifo_underflow_tb.sv
vvp pass.vvp +vcd=passing.vcd +stim=sim/stimulus.mem
exec vvp fail.vvp +vcd=failing.vcd +stim=sim/stimulus.mem
