// Small synthesizable AXI-stream pipeline stage used to generate real simulator
// waveforms. It captures an incoming payload into a held register under a lock
// and must keep it stable while downstream backpressure is asserted.
//
// The seeded fault is a compile-time define: when INJECT_FAULT is defined the
// held payload is corrupted (driven to x) under backpressure instead of being
// held stable. Compiling once without the define and once with it yields a
// genuine passing-vs-failing waveform pair from the same stimulus.
module axi_pipe #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] payload_in,
    input  logic             valid_in,
    input  logic             ready_downstream,
    output logic [WIDTH-1:0] payload_out,
    output logic             valid_out
);
    logic [WIDTH-1:0] payload_reg;
    logic             locked;

    assign payload_out = payload_reg;
    assign valid_out   = locked & ready_downstream;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            payload_reg <= '0;
            locked      <= 1'b0;
        end else if (valid_in && !locked) begin
            payload_reg <= payload_in;
            locked      <= 1'b1;
        end else if (locked && !ready_downstream) begin
`ifdef INJECT_FAULT
            // Seeded bug: the locked payload is corrupted under backpressure.
            payload_reg <= 'x;
`else
            // Correct behaviour: hold the locked payload stable.
            payload_reg <= payload_reg;
`endif
        end else if (locked && ready_downstream) begin
            locked <= 1'b0;
        end
    end
endmodule
