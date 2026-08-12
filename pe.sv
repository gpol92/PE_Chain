module pe #(
	parameter int DATA_WIDTH = 8
)(
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [DATA_WIDTH-1:0] acc_in
	output logic signed [(2*DATA_WIDTH)-1:0] y
);
	always_comb begin
		y = a*b + acc_in;
	end
endmodule
