// Deterministic testbench that drives the hierarchical top module and dumps a
// VCD. The same stimulus is used for both the passing and the seeded-failing
// build (the fault is selected at compile time via INJECT_FAULT in the ingress
// child), so the two VCDs differ only where the seeded bug manifests and
// propagates. The dump path is taken from a +vcd=<path> plusarg.
//
// The testbench is intentionally kept out of the inspected RTL repository, and
// the child instances are named after their modules, so signal-source mapping
// resolves each observed signal to its own child file.
module top_tb;
    localparam int WIDTH = 8;

    logic             clk;
    logic             rst_n;
    logic [WIDTH-1:0] data_in;
    logic             valid_in;
    logic             ready_downstream;
    logic [WIDTH-1:0] payload_out;
    logic             grant;

    top #(.WIDTH(WIDTH)) dut (
        .clk(clk),
        .rst_n(rst_n),
        .data_in(data_in),
        .valid_in(valid_in),
        .ready_downstream(ready_downstream),
        .payload_out(payload_out),
        .grant(grant)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin : dump
        string vcd_path;
        if (!$value$plusargs("vcd=%s", vcd_path)) vcd_path = "dump.vcd";
        $dumpfile(vcd_path);
        // Dump each child scope (level 1) so every observed signal resolves to
        // exactly one child module, rather than also appearing as redundant
        // port copies at the top/testbench levels.
        $dumpvars(1, dut.ingress);
        $dumpvars(1, dut.route);
    end

    initial begin : stimulus
        rst_n            = 1'b0;
        data_in          = 8'h00;
        valid_in         = 1'b0;
        ready_downstream = 1'b1;

        #20 rst_n = 1'b1;

        // Present a packet to be captured and locked by the ingress child.
        #10 data_in  = 8'hAA;
            valid_in = 1'b1;

        // Deassert valid and apply downstream backpressure.
        #10 valid_in         = 1'b0;
            ready_downstream = 1'b0;

        // Hold backpressure for a few cycles, then release and finish.
        #40 ready_downstream = 1'b1;
        #20 $finish;
    end
endmodule
