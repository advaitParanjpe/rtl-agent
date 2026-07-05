// Ingress child of a hierarchical, simulatable AXI-stream router. It captures an
// incoming payload into a staged register under a lock and must hold it stable
// while downstream backpressure is asserted. The seeded fault is a compile-time
// define: with INJECT_FAULT the staged payload is corrupted to x under
// backpressure instead of being held. The fault therefore originates here and
// propagates, across the module boundary, into the route child.
module ingress #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] data_in,
    input  logic             valid_in,
    input  logic             hold,
    output logic [WIDTH-1:0] payload_staged,
    output logic             staged_valid
);
    logic staged_lock;

    // Continuous driver.
    assign staged_valid = staged_lock & ~hold;

    // Procedural driver of the staged payload.
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            payload_staged <= '0;
            staged_lock    <= 1'b0;
        end else if (valid_in && !staged_lock) begin
            payload_staged <= data_in;
            staged_lock    <= 1'b1;
        end else if (staged_lock && hold) begin
`ifdef INJECT_FAULT
            // Seeded bug: corrupt the locked payload under backpressure.
            payload_staged <= 'x;
`else
            // Correct behaviour: hold the locked payload stable.
            payload_staged <= payload_staged;
`endif
        end else if (staged_lock && !hold) begin
            staged_lock <= 1'b0;
        end
    end
endmodule
