// Routing stage of the multi-file AXI-stream router fixture. It drives the
// visible output payload from the cross-module staged payload and tracks a
// small routing state machine. The output payload therefore depends, across
// module boundaries, on a signal driven in the ingress stage.
module axi_route #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] payload_staged,
    input  logic             staged_valid,
    input  logic             ready_downstream,
    output logic [WIDTH-1:0] payload_out,
    output logic             grant,
    output logic [1:0]       route_state
);
    // Continuous drivers referencing the cross-module staged payload.
    assign payload_out = payload_staged;
    assign grant       = staged_valid & ready_downstream;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            route_state <= 2'd0;
        end else begin
            case (route_state)
                2'd0: if (staged_valid) route_state <= 2'd1;
                2'd1: if (ready_downstream) route_state <= 2'd2;
                default: route_state <= 2'd0;
            endcase
        end
    end
endmodule
