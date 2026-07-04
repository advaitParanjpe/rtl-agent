// Compact AXI-stream router fragment used as a failure-intelligence fixture.
// It drives real internal signals with continuous and procedural assignments so
// that static driver tracing has genuine evidence to cite. It is intentionally
// small and is never elaborated or simulated by the pipeline.
module axi_stream_router #(
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
    // Protocol and state signals.
    logic             packet_locked;
    logic [1:0]       state;
    logic [WIDTH-1:0] payload_reg;

    localparam logic [1:0] S_IDLE = 2'd0;
    localparam logic [1:0] S_LOCK = 2'd1;
    localparam logic [1:0] S_SEND = 2'd2;

    // Continuous drivers: the visible outputs are functions of held state.
    assign payload_out = payload_reg;
    assign valid_out   = packet_locked & ready_downstream;

    // Sequential capture. Under backpressure the locked payload must be held
    // stable until the downstream sink accepts it.
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= S_IDLE;
            packet_locked <= 1'b0;
            payload_reg   <= '0;
        end else begin
            case (state)
                S_IDLE: begin
                    if (valid_in) begin
                        payload_reg   <= payload_in;
                        packet_locked <= 1'b1;
                        state         <= S_LOCK;
                    end
                end
                S_LOCK: begin
                    if (ready_downstream) begin
                        state <= S_SEND;
                    end
                end
                S_SEND: begin
                    packet_locked <= 1'b0;
                    state         <= S_IDLE;
                end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
