module pe #(
	parameter int DATA_WIDTH = 8
)(
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	output logic signed [(2*DATA_WIDTH)-1:0] y
);
	assign y = a*b;
endmodule
