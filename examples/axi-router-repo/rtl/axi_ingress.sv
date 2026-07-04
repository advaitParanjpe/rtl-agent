// Ingress stage of a small multi-file AXI-stream router fixture.
// It captures an incoming payload into a staged register under a lock, and is
// held stable while downstream backpressure is asserted. The staged payload is
// exported to the routing stage through the top module. This RTL is a textual
// fixture only; it is never elaborated or simulated by the pipeline.
module axi_ingress #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] payload_in,
    input  logic             valid_in,
    input  logic             hold,
    output logic [WIDTH-1:0] payload_staged,
    output logic             staged_valid
);
    logic staged_lock;

    assign staged_valid = staged_lock & ~hold;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            payload_staged <= '0;
            staged_lock    <= 1'b0;
        end else if (valid_in && !staged_lock) begin
            payload_staged <= payload_in;
            staged_lock    <= 1'b1;
        end else if (!hold) begin
            staged_lock    <= 1'b0;
        end
    end
endmodule
