// A second, independent definition of module `lane` (an alternate view kept in
// the tree). It declares the same ports and the same internal signal names
// (`data_hold`, `data_out`) as the RTL view, so those signal names are
// genuinely non-unique across files. The pipeline must preserve both source
// candidates rather than silently pick one. Textual fixture only.
module lane #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] data_in,
    input  logic             accept,
    output logic [WIDTH-1:0] data_out
);
    logic [WIDTH-1:0] data_hold;

    assign data_out = data_hold;

    always_ff @(posedge clk) begin
        data_hold <= accept ? data_in : data_hold;
    end
endmodule
