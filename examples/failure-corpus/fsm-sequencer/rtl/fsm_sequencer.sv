// Realistic failure-corpus example: FSM transition bug.
//
// A small arm/drain sequencer. A `send` in IDLE captures the payload and arms
// the stage; the armed value must be drained (downstream ready with no new
// send) before the next capture. A premature second `send` while ARMED is a
// protocol violation. With the seeded fault (compile-time INJECT_FAULT) the
// illegal transition corrupts the held payload to x instead of ignoring the
// premature send, so the minimal failing subsequence is two back-to-back sends.
// Textual fixture only; never product runtime.
`timescale 1ns / 1ns
module fsm_sequencer #(
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
    localparam logic [1:0] S_IDLE = 2'd0;
    localparam logic [1:0] S_ARMED = 2'd1;
    localparam logic [1:0] S_FAULT = 2'd2;

    logic [1:0]       state;
    logic [WIDTH-1:0] payload_reg;

    assign payload_out = payload_reg;
    assign valid_out   = (state == S_ARMED);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            payload_reg <= '0;
        end else begin
            case (state)
                S_IDLE: begin
                    if (valid_in) begin
                        payload_reg <= payload_in;
                        state       <= S_ARMED;
                    end
                end
                S_ARMED: begin
                    if (valid_in) begin
`ifdef INJECT_FAULT
                        payload_reg <= 'x;
                        state       <= S_FAULT;
`else
                        state       <= S_ARMED;
`endif
                    end else if (ready_downstream) begin
                        state <= S_IDLE;
                    end
                end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
