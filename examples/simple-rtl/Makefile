lint:
	verilator --lint-only rtl/top.sv

sim:
	iverilog -g2012 -o simv rtl/top.sv tb/top_tb.sv
