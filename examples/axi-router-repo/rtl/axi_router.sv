// Top module of the multi-file AXI-stream router fixture. It instantiates the
// ingress and routing child modules from their separate files and wires the
// staged payload and its valid handshake across the module boundary, so that
// the observable output depends on state driven in a different file.
module axi_router #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] payload_in,
    input  logic             valid_in,
    input  logic             ready_downstream,
    output logic [WIDTH-1:0] payload_out,
    output logic             grant
);
    logic [WIDTH-1:0] payload_staged;
    logic             staged_valid;
    logic [1:0]       route_state;
    logic             hold;

    assign hold = ~ready_downstream;

    axi_ingress #(.WIDTH(WIDTH)) u_ingress (
        .clk(clk),
        .rst_n(rst_n),
        .payload_in(payload_in),
        .valid_in(valid_in),
        .hold(hold),
        .payload_staged(payload_staged),
        .staged_valid(staged_valid)
    );

    axi_route #(.WIDTH(WIDTH)) u_route (
        .clk(clk),
        .rst_n(rst_n),
        .payload_staged(payload_staged),
        .staged_valid(staged_valid),
        .ready_downstream(ready_downstream),
        .payload_out(payload_out),
        .grant(grant),
        .route_state(route_state)
    );
endmodule
