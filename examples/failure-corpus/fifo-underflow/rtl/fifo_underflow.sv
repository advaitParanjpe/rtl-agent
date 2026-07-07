// Realistic failure-corpus example: FIFO underflow bug.
//
// A small synchronous FIFO. A `send` pushes a payload; a `stall` (downstream not
// ready with no new push) pops. Popping while empty is an underflow. With the
// seeded fault (compile-time INJECT_FAULT) an underflowing pop drives the read
// data to x instead of returning a safe zero, so the minimal failing subsequence
// is a pop with the FIFO empty. Textual fixture only; never product runtime.
`timescale 1ns / 1ns
module fifo_underflow #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 4
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] payload_in,
    input  logic             valid_in,
    input  logic             ready_downstream,
    output logic [WIDTH-1:0] payload_out,
    output logic             valid_out
);
    localparam int AW = 2;

    logic [WIDTH-1:0] mem [0:DEPTH-1];
    logic [AW-1:0]    rd_ptr;
    logic [AW-1:0]    wr_ptr;
    logic [AW:0]      count;
    logic [WIDTH-1:0] data_out;

    logic push;
    logic pop;
    assign push = valid_in && (count < DEPTH[AW:0]);
    assign pop  = !valid_in && !ready_downstream;

    assign payload_out = data_out;
    assign valid_out   = (count != '0);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_ptr   <= '0;
            wr_ptr   <= '0;
            count    <= '0;
            data_out <= '0;
        end else begin
            if (push) begin
                mem[wr_ptr] <= payload_in;
                wr_ptr      <= wr_ptr + 1'b1;
            end
            if (pop) begin
                if (count == '0) begin
`ifdef INJECT_FAULT
                    data_out <= 'x;
`else
                    data_out <= '0;
`endif
                end else begin
                    data_out <= mem[rd_ptr];
                    rd_ptr   <= rd_ptr + 1'b1;
                end
            end
            case ({push, pop && (count != '0)})
                2'b10:   count <= count + 1'b1;
                2'b01:   count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
