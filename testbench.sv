// Cocotb wrapper exposing the two historical reference versions and the
// implementation from pe.sv as separate DUT handles.
module pe_v0 #(parameter int DATA_WIDTH = 8) (
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	output logic signed [(2*DATA_WIDTH)-1:0] y
);
	assign y = a * b;
endmodule

module pe_v1 #(parameter int DATA_WIDTH = 8) (
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [DATA_WIDTH-1:0] acc_in,
	output logic signed [(2*DATA_WIDTH)-1:0] y
);
	always_comb y = a * b + acc_in;
endmodule

// V2 reference circuit. It remains manually connected so that the generated
// NUM_PE=2 implementation can be checked against the previous architecture.
module pe_chain_manual_2 #(parameter int DATA_WIDTH = 8) (
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [DATA_WIDTH-1:0] acc_in,
	output logic signed [(2*DATA_WIDTH)-1:0] y
);
	logic signed [(2*DATA_WIDTH)-1:0] stage_0_y;

	pe #(.DATA_WIDTH(DATA_WIDTH)) pe_dut_0 (
		.a(a),
		.b(b),
		.acc_in(acc_in),
		.y(stage_0_y)
	);

	pe #(.DATA_WIDTH(DATA_WIDTH)) pe_dut_1 (
		.a(a),
		.b(b),
		.acc_in(stage_0_y[DATA_WIDTH-1:0]),
		.y(y)
	);
endmodule

module pe_testbench #(parameter int DATA_WIDTH = 8) (
	input logic clk,
	input logic rst,
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [DATA_WIDTH-1:0] acc_in,
	output logic signed [(2*DATA_WIDTH)-1:0] y_v0,
	output logic signed [(2*DATA_WIDTH)-1:0] y_v1,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe_chain_manual_2,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe_chain_2,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe_chain_4,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe_array_0,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe_array_1,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe_array_2,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe_array_3,
	output logic signed [(2*DATA_WIDTH)+$clog2(4)-1:0] y_pe_chain_v5,
	output logic signed [(2*DATA_WIDTH)+$clog2(4)-1:0] y_pe_chain_v6
);
	logic signed [DATA_WIDTH-1:0] array_a [0:3];
	logic signed [DATA_WIDTH-1:0] array_b [0:3];
	logic signed [(2*DATA_WIDTH)-1:0] array_y [0:3];

	pe_v0 #(.DATA_WIDTH(DATA_WIDTH)) v0_dut (.a(a), .b(b), .y(y_v0));
	pe_v1 #(.DATA_WIDTH(DATA_WIDTH)) v1_dut (.a(a), .b(b), .acc_in(acc_in), .y(y_v1));
	// The actual implementation under test; available in cocotb as dut.pe_dut.
	pe #(.DATA_WIDTH(DATA_WIDTH)) pe_dut (.a(a), .b(b), .acc_in(acc_in), .y(y_pe));

	pe_chain_manual_2 #(.DATA_WIDTH(DATA_WIDTH)) pe_chain_manual_2_dut (
		.a(a), .b(b), .acc_in(acc_in), .y(y_pe_chain_manual_2)
	);
	pe_chain #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(2)) pe_chain_2_dut (
		.a(a), .b(b), .acc_in(acc_in), .y(y_pe_chain_2)
	);
	pe_chain #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(4)) pe_chain_4_dut (
		.a(a), .b(b), .acc_in(acc_in), .y(y_pe_chain_4)
	);

	genvar i;
	generate
		for (i = 0; i < 4; i++) begin : gen_array_inputs
			assign array_a[i] = a + i;
			assign array_b[i] = b + i;
		end
	endgenerate

	pe_chain_arrays #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(4)) pe_chain_arrays_4_dut (
		.a(array_a), .b(array_b), .y(array_y)
	);
	pe_chain_v5 #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(4)) pe_chain_v5_dut (
		.a(array_a), .b(array_b), .y(y_pe_chain_v5)
	);
	pe_chain_v6 #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(4)) pe_chain_v6_dut (
		.clk(clk), .rst(rst), .a(array_a), .b(array_b), .y(y_pe_chain_v6)
	);

	assign y_pe_array_0 = array_y[0];
	assign y_pe_array_1 = array_y[1];
	assign y_pe_array_2 = array_y[2];
	assign y_pe_array_3 = array_y[3];
endmodule
