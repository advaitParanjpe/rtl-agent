// Deterministic testbench that drives axi_pipe, dumps a VCD, and emits a stable,
// timestamped assertion-failure marker when the held payload becomes unknown
// under backpressure. The same stimulus is used for the passing and the
// seeded-failing build (the fault is a compile-time define in axi_pipe); only
// the faulted build trips the check. On a detected failure the run ends with a
// non-zero terminal status ($fatal), after the full VCD has been written, so the
// existing command runner and triage services capture a real failing run.
`timescale 1ns / 1ns
module axi_pipe_tb;
    localparam int WIDTH = 8;

    logic             clk;
    logic             rst_n;
    logic [WIDTH-1:0] payload_in;
    logic             valid_in;
    logic             ready_downstream;
    logic [WIDTH-1:0] payload_out;
    logic             valid_out;

    logic             fail_flag;

    axi_pipe #(.WIDTH(WIDTH)) axi_pipe (
        .clk(clk),
        .rst_n(rst_n),
        .payload_in(payload_in),
        .valid_in(valid_in),
        .ready_downstream(ready_downstream),
        .payload_out(payload_out),
        .valid_out(valid_out)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin : dump
        string vcd_path;
        if (!$value$plusargs("vcd=%s", vcd_path)) vcd_path = "dump.vcd";
        $dumpfile(vcd_path);
        $dumpvars(1, axi_pipe);
    end

    // Stable failure marker: fires exactly when the observable payload goes
    // unknown after reset. It reports the assertion label and the timestamp in
    // ns so the existing triage/link services can recover the failure time.
    initial fail_flag = 1'b0;
    always @(payload_out) begin
        if (rst_n === 1'b1 && $isunknown(payload_out) && !fail_flag) begin
            fail_flag = 1'b1;
            $display("assertion payload_stable failed at time=%0d ns", $time);
        end
    end

    initial begin : stimulus
        rst_n            = 1'b0;
        payload_in       = 8'h00;
        valid_in         = 1'b0;
        ready_downstream = 1'b1;

        #20 rst_n = 1'b1;

        #10 payload_in = 8'hAA;
            valid_in   = 1'b1;

        #10 valid_in         = 1'b0;
            ready_downstream = 1'b0;

        #40 ready_downstream = 1'b1;

        // Let the full waveform be written, then terminate with a non-zero
        // status if the seeded failure was observed.
        #20 if (fail_flag) begin
            $fatal(1, "seeded payload instability detected");
        end else begin
            $finish;
        end
    end
endmodule
