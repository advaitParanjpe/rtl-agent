// Simulatable AXI-stream pipeline stage used to generate a real failing
// simulation with captured logs and a VCD. It captures an incoming payload
// under a lock and must hold it stable under backpressure. The seeded fault is a
// compile-time define: with INJECT_FAULT the held payload is corrupted to x
// under backpressure. An explicit timescale is set so simulator log timestamps
// and the VCD share ns units. Textual fixture only; never product runtime.
`timescale 1ns / 1ns
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
            payload_reg <= 'x;
`else
            payload_reg <= payload_reg;
`endif
        end else if (locked && ready_downstream) begin
            locked <= 1'b0;
        end
    end
endmodule
