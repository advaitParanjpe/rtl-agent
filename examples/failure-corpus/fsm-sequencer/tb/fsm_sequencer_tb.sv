// Program-driven testbench for the fsm-sequencer corpus example. It loads an
// ordered stimulus program from a hex memory file and applies one action per
// cycle (0x1 => send with payload, 0x2 => stall/backpressure, else idle),
// monitors payload_out for the seeded corruption, emits a stable timestamped
// marker on the observed fault, and terminates non-zero. The clean build is the
// passing reference.
`timescale 1ns / 1ns
module fsm_sequencer_tb;
    localparam int WIDTH = 8;
    localparam int MAX_ITEMS = 256;
    localparam logic [15:0] SENTINEL = 16'hffff;

    logic             clk;
    logic             rst_n;
    logic [WIDTH-1:0] payload_in;
    logic             valid_in;
    logic             ready_downstream;
    logic [WIDTH-1:0] payload_out;
    logic             valid_out;
    logic             fail_flag;

    logic [15:0] program_mem [0:MAX_ITEMS-1];
    integer      pc;

    fsm_sequencer #(.WIDTH(WIDTH)) fsm_sequencer (
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
        $dumpvars(1, fsm_sequencer);
    end

    initial fail_flag = 1'b0;
    always @(payload_out) begin
        if (rst_n === 1'b1 && $isunknown(payload_out) && !fail_flag) begin
            fail_flag = 1'b1;
            $display("assertion payload_stable failed at time=%0d ns", $time);
        end
    end

    initial begin : stimulus
        string stim_path;
        integer index;
        for (index = 0; index < MAX_ITEMS; index = index + 1) program_mem[index] = SENTINEL;
        if (!$value$plusargs("stim=%s", stim_path)) stim_path = "stimulus.mem";
        $readmemh(stim_path, program_mem);

        rst_n            = 1'b0;
        payload_in       = 8'h00;
        valid_in         = 1'b0;
        ready_downstream = 1'b1;
        #20 rst_n = 1'b1;

        pc = 0;
        while (pc < MAX_ITEMS && program_mem[pc] !== SENTINEL) begin
            @(negedge clk);
            case (program_mem[pc][15:12])
                4'h1: begin
                    valid_in         = 1'b1;
                    payload_in       = program_mem[pc][7:0];
                    ready_downstream = 1'b1;
                end
                4'h2: begin
                    valid_in         = 1'b0;
                    ready_downstream = 1'b0;
                end
                default: begin
                    valid_in         = 1'b0;
                    ready_downstream = 1'b1;
                end
            endcase
            @(posedge clk);
            pc = pc + 1;
        end

        @(negedge clk);
        valid_in         = 1'b0;
        ready_downstream = 1'b1;
        #20;
        if (fail_flag) begin
            $fatal(1, "seeded failure reproduced");
        end else begin
            $finish;
        end
    end
endmodule
