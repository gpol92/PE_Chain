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


// V14 PE: one lane of a parallel dot product. Every instantiated lane forms
// its product independently, so PE i and PE i+1 execute in the same cycle.
module pe_v14 #(
	parameter int DATA_WIDTH = 8
)(
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	output logic signed [(2*DATA_WIDTH)-1:0] product
);
	always_comb begin
		product = a * b;
	end
endmodule


// V15 PE: one independent multiply-accumulate lane. The first valid element
// of a vector starts from acc_in; following elements continue from y.
module pe_v15 #(
	parameter int DATA_WIDTH = 8,
	parameter int ACC_WIDTH = 2 * DATA_WIDTH
)(
	input logic clk,
	input logic rst,
	input logic enable,
	input logic first_element,
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [ACC_WIDTH-1:0] acc_in,
	output logic signed [ACC_WIDTH-1:0] y
);
	always_ff @(posedge clk) begin
		if (rst)
			y <= '0;
		else if (enable) begin
			if (first_element)
				y <= acc_in + (a * b);
			else
				y <= y + (a * b);
		end
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
// create bubbles. An overflowing transaction becomes a one-cycle error token;
// both invalid and erroneous transactions produce a deterministic zero value.
module pe_v7 #(
	parameter int DATA_WIDTH = 8,
	parameter int ACC_WIDTH = 2 * DATA_WIDTH
)(
	input logic clk,
	input logic rst,
	input logic valid_in,
	input logic error_in,
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [ACC_WIDTH-1:0] acc_in,
	output logic signed [ACC_WIDTH-1:0] y,
	output logic valid_out,
	output logic error_out,
	output logic local_overflow
);
	logic signed [(2*DATA_WIDTH)-1:0] product;
	logic signed [ACC_WIDTH:0] extended_acc;
	logic signed [ACC_WIDTH:0] extended_product;
	logic signed [ACC_WIDTH:0] extended_sum;
	logic mac_overflow;

	assign product = a * b;
	assign extended_acc = {acc_in[ACC_WIDTH-1], acc_in};
	assign extended_product = {
		{(ACC_WIDTH + 1 - (2*DATA_WIDTH)){product[(2*DATA_WIDTH)-1]}},
		product
	};
	assign extended_sum = extended_acc + extended_product;
	assign mac_overflow = extended_sum[ACC_WIDTH] != extended_sum[ACC_WIDTH-1];
	assign local_overflow = valid_in && !error_in && mac_overflow;

	always_ff @(posedge clk) begin
		if (rst) begin
			y <= '0;
			valid_out <= 1'b0;
			error_out <= 1'b0;
		end else begin
			error_out <= 1'b0;
			if (error_in) begin
				y <= '0;
				valid_out <= 1'b0;
				error_out <= 1'b1;
			end else if (local_overflow) begin
				y <= '0;
				valid_out <= 1'b0;
				error_out <= 1'b1;
			end else if (valid_in) begin
				y <= extended_sum[ACC_WIDTH-1:0];
				valid_out <= 1'b1;
			end else begin
				y <= '0;
				valid_out <= 1'b0;
			end
		end
	end
endmodule
