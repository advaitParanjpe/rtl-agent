// Top module of the hierarchical AXI-stream router. It instantiates the ingress
// and route child modules from their separate files and wires the staged
// payload and its valid handshake across the module boundary, so the observable
// routed output depends on state driven in a different file.
module top #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] data_in,
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

    ingress #(.WIDTH(WIDTH)) ingress (
        .clk(clk),
        .rst_n(rst_n),
        .data_in(data_in),
        .valid_in(valid_in),
        .hold(hold),
        .payload_staged(payload_staged),
        .staged_valid(staged_valid)
    );

    route #(.WIDTH(WIDTH)) route (
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
