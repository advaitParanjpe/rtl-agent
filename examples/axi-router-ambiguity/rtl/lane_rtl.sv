// RTL view of the `lane` child module. The repository deliberately contains a
// second definition of a module with the SAME name `lane` in a separate file,
// creating a genuine, non-contrived ambiguity: a signal path component `lane`
// matches more than one declaration. This RTL is a textual fixture only and is
// never elaborated or simulated by the pipeline.
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

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_hold <= '0;
        end else if (accept) begin
            data_hold <= data_in;
        end
    end
endmodule
