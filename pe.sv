module pe #(
	parameter int DATA_WIDTH = 8
)(
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [DATA_WIDTH-1:0] acc_in,
	output logic signed [(2*DATA_WIDTH)-1:0] y
);
	always_comb begin
		y = a*b + acc_in;
	end
endmodule


// V5 PE: keep the product and the running sum at ACC_WIDTH bits so that
// intermediate dot-product results are not truncated between stages.
module pe_v5 #(
	parameter int DATA_WIDTH = 8,
	parameter int ACC_WIDTH = 2 * DATA_WIDTH
)(
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [ACC_WIDTH-1:0] acc_in,
	output logic signed [ACC_WIDTH-1:0] y
);
	always_comb begin
		y = acc_in + (a * b);
	end
endmodule
