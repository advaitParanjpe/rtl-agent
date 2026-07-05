// Route child of the hierarchical AXI-stream router. It registers the staged
// payload driven by the ingress child into the observable output one cycle
// later, so the seeded fault propagates across the module boundary from
// `payload_staged` (ingress) into `payload_out` (route). It also drives a
// continuous grant and a small routing state machine.
module route #(
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
    // Continuous driver.
    assign grant = staged_valid & ready_downstream;

    // Procedural driver: register the cross-module staged payload.
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            payload_out <= '0;
        end else begin
            payload_out <= payload_staged;
        end
    end

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
