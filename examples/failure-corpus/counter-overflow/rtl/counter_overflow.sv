// Realistic failure-corpus example: counter/state-update overflow bug.
//
// A saturating event counter. Each `send` increments the count. At the
// saturation boundary the correct design holds the maximum; with the seeded
// fault (compile-time INJECT_FAULT) the boundary update corrupts the count to x
// instead of saturating, so the minimal failing subsequence is exactly the four
// increments needed to reach the boundary. Textual fixture only; never product
// runtime.
`timescale 1ns / 1ns
module counter_overflow #(
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
    localparam logic [WIDTH-1:0] LIMIT = 8'd3;

    logic [WIDTH-1:0] count;

    assign payload_out = count;
    assign valid_out   = (count != '0);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= '0;
        end else if (valid_in && ready_downstream) begin
            if (count == LIMIT) begin
`ifdef INJECT_FAULT
                count <= 'x;
`else
                count <= LIMIT;
`endif
            end else begin
                count <= count + 1'b1;
            end
        end
    end
endmodule
