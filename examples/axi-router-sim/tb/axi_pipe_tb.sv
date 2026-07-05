// Deterministic testbench that drives axi_pipe and dumps a VCD. The same
// stimulus is used for both the passing and the seeded-failing build (the fault
// is selected at compile time via the INJECT_FAULT define), so the two VCDs
// differ only where the seeded bug manifests. The dump path is taken from a
// +vcd=<path> plusarg so the generator can place the two runs side by side.
//
// The testbench module is intentionally kept out of the inspected RTL
// repository, so signal-source mapping resolves the DUT scope to the axi_pipe
// module rather than to the testbench.
module axi_pipe_tb;
    localparam int WIDTH = 8;

    logic             clk;
    logic             rst_n;
    logic [WIDTH-1:0] payload_in;
    logic             valid_in;
    logic             ready_downstream;
    logic [WIDTH-1:0] payload_out;
    logic             valid_out;

    // Instance named to match the module so the dump hierarchy exposes an
    // `axi_pipe` scope for source mapping.
    axi_pipe #(.WIDTH(WIDTH)) axi_pipe (
        .clk(clk),
        .rst_n(rst_n),
        .payload_in(payload_in),
        .valid_in(valid_in),
        .ready_downstream(ready_downstream),
        .payload_out(payload_out),
        .valid_out(valid_out)
    );

    // 10ns clock.
    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin : dump
        string vcd_path;
        if (!$value$plusargs("vcd=%s", vcd_path)) vcd_path = "dump.vcd";
        $dumpfile(vcd_path);
        $dumpvars(0, axi_pipe_tb);
    end

    initial begin : stimulus
        rst_n            = 1'b0;
        payload_in       = 8'h00;
        valid_in         = 1'b0;
        ready_downstream = 1'b1;

        // Hold reset, then release.
        #20 rst_n = 1'b1;

        // Present a packet to be captured and locked.
        #10 payload_in = 8'hAA;
            valid_in   = 1'b1;

        // Deassert valid once the packet is accepted.
        #10 valid_in = 1'b0;

        // Apply downstream backpressure: the locked payload must hold stable.
        ready_downstream = 1'b0;

        // Hold backpressure for a few cycles, then release and finish.
        #40 ready_downstream = 1'b1;
        #20 $finish;
    end
endmodule
