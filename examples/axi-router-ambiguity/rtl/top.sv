// Top module of the ambiguity fixture. It instantiates the `lane` child module
// more than once (repeated child-module instances). Because `lane` is defined
// in two separate files, both the duplicate declaration and the repeated
// instances exercise the pipeline's ambiguity handling. Textual fixture only.
module top #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic [WIDTH-1:0] data_in,
    input  logic             accept,
    output logic [WIDTH-1:0] data_out
);
    logic [WIDTH-1:0] shadow_out;

    // First instance of `lane` (the one observed in the waveforms).
    lane #(.WIDTH(WIDTH)) lane (
        .clk(clk),
        .rst_n(rst_n),
        .data_in(data_in),
        .accept(accept),
        .data_out(data_out)
    );

    // A repeated instance of the same child module.
    lane #(.WIDTH(WIDTH)) lane_shadow (
        .clk(clk),
        .rst_n(rst_n),
        .data_in(data_in),
        .accept(accept),
        .data_out(shadow_out)
    );
endmodule
