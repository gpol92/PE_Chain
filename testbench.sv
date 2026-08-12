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

module pe_testbench #(parameter int DATA_WIDTH = 8) (
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [DATA_WIDTH-1:0] acc_in,
	output logic signed [(2*DATA_WIDTH)-1:0] y_v0,
	output logic signed [(2*DATA_WIDTH)-1:0] y_v1,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe_chain
);
	pe_v0 #(.DATA_WIDTH(DATA_WIDTH)) v0_dut (.a(a), .b(b), .y(y_v0));
	pe_v1 #(.DATA_WIDTH(DATA_WIDTH)) v1_dut (.a(a), .b(b), .acc_in(acc_in), .y(y_v1));
	// The actual implementation under test; available in cocotb as dut.pe_dut.
	pe #(.DATA_WIDTH(DATA_WIDTH)) pe_dut (.a(a), .b(b), .acc_in(acc_in), .y(y_pe));
	pe_chain #(.DATA_WIDTH(DATA_WIDTH)) pe_chain_dut(.a(a), .b(b), .acc_in(acc_in), .y(y_pe_chain));
endmodule


module pe_chain #(parameter int DATA_WIDTH = 8) (
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [DATA_WIDTH-1:0] acc_in,
	output logic signed [(2*DATA_WIDTH)-1:0] y_pe_chain,
	output logic signed [(2*DATA_WIDTH)-1:0] y
);
	pe_v1 #(.DATA_WIDTH(DATA_WIDTH)) pe_v1_dut_0 (.a(a), .b(b), .acc_in(acc_in), .y(y_pe_chain));
	pe_v1 #(.DATA_WIDTH(DATA_WIDTH)) pe_v1_dut_1 (.a(a), .b(y_pe_chain[DATA_WIDTH-1:0]), .acc_in(acc_in), .y(y));
endmodule
