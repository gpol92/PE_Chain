module pe_chain #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 2
)(
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [DATA_WIDTH-1:0] acc_in,
	output logic signed [(2*DATA_WIDTH)-1:0] y
);
	logic signed [DATA_WIDTH-1:0] chain_acc [0:NUM_PE];
	logic signed [(2*DATA_WIDTH)-1:0] stage_y [0:NUM_PE-1];

	assign chain_acc[0] = acc_in;

	genvar i;
	generate
		for (i = 0; i < NUM_PE; i++) begin : gen_pe
			pe #(.DATA_WIDTH(DATA_WIDTH)) pe_dut (
				.a(a),
				.b(b),
				.acc_in(chain_acc[i]),
				.y(stage_y[i])
			);

			// Preserve the V2 behavior: acc_in is DATA_WIDTH bits wide.
			assign chain_acc[i+1] = stage_y[i][DATA_WIDTH-1:0];
		end
	endgenerate

	assign y = stage_y[NUM_PE-1];
endmodule


module pe_chain_arrays #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 2
)(
	input logic signed [DATA_WIDTH-1:0] a [0:NUM_PE-1],
	input logic signed [DATA_WIDTH-1:0] b [0:NUM_PE-1],
	output logic signed [(2*DATA_WIDTH)-1:0] y [0:NUM_PE-1]
);
	genvar i;
	generate
		for (i = 0; i < NUM_PE; i++) begin : gen_array_pe
			pe #(.DATA_WIDTH(DATA_WIDTH)) pe_dut (
				.a(a[i]),
				.b(b[i]),
				.acc_in('0),
				.y(y[i])
			);
		end
	endgenerate
endmodule
