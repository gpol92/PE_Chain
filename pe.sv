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


// V6 PE: register each partial sum. Reset is synchronous and active high.
module pe_v6 #(
	parameter int DATA_WIDTH = 8,
	parameter int ACC_WIDTH = 2 * DATA_WIDTH
)(
	input logic clk,
	input logic rst,
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [ACC_WIDTH-1:0] acc_in,
	output logic signed [ACC_WIDTH-1:0] y
);
	always_ff @(posedge clk) begin
		if (rst)
			y <= '0;
		else
			y <= acc_in + (a * b);
	end
endmodule


// V7 PE: register the partial sum and its validity together. Invalid inputs
// create bubbles in the pipeline and produce a deterministic zero data value.
module pe_v7 #(
	parameter int DATA_WIDTH = 8,
	parameter int ACC_WIDTH = 2 * DATA_WIDTH
)(
	input logic clk,
	input logic rst,
	input logic valid_in,
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [ACC_WIDTH-1:0] acc_in,
	output logic signed [ACC_WIDTH-1:0] y,
	output logic valid_out
);
	always_ff @(posedge clk) begin
		if (rst) begin
			y <= '0;
			valid_out <= 1'b0;
		end else begin
			valid_out <= valid_in;
			if (valid_in)
				y <= acc_in + (a * b);
			else
				y <= '0;
		end
	end
endmodule
