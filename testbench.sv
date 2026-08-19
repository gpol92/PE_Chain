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

module pe_testbench #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 4,
	parameter int NUM_EL = 4,
	parameter int NUM_DOT_UNITS = 3,
	parameter int V7_ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE),
	parameter int V14_ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE),
	parameter int V15_ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_EL),
	parameter int V16_RESULT_ADDR_WIDTH = 2,
	parameter int SPECIAL_ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE),
	parameter int SPECIAL_RESULT_WIDTH = SPECIAL_ACC_WIDTH + 1,
	parameter int SPECIAL_ADDR_WIDTH = (NUM_DOT_UNITS <= 1) ? 1 : $clog2(NUM_DOT_UNITS)
) (
	input logic clk,
	input logic rst,
	input logic valid_in,
	input logic ram_we,
	input logic [1:0] ram_write_addr,
	input logic [DATA_WIDTH-1:0] ram_write_data,
	input logic [1:0] ram_read_addr,
	input logic memory_load_we,
	input logic memory_load_weights,
	input logic [1:0] memory_load_addr,
	input logic [(NUM_PE*DATA_WIDTH)-1:0] memory_load_data,
	input logic [1:0] data_addr,
	input logic [1:0] weight_addr,
	input logic v8_valid_in,
	input logic v11_valid_in,
	input logic special_valid_in,
	input logic [(NUM_DOT_UNITS*NUM_PE*DATA_WIDTH)-1:0] special_data_vectors,
	input logic [(NUM_DOT_UNITS*NUM_PE*DATA_WIDTH)-1:0] special_weight_vectors,
	input logic [(NUM_DOT_UNITS*SPECIAL_ACC_WIDTH)-1:0] special_biases,
	input logic [SPECIAL_ADDR_WIDTH-1:0] special_result_addr,
	input logic start,
	input logic signed [DATA_WIDTH-1:0] a,
	input logic signed [DATA_WIDTH-1:0] b,
	input logic signed [DATA_WIDTH-1:0] acc_in,
	input logic [(NUM_PE*DATA_WIDTH)-1:0] chain_data_vector,
	input logic [(NUM_PE*DATA_WIDTH)-1:0] chain_weight_vector,
	input logic v15_valid_in,
	input logic [(NUM_PE*DATA_WIDTH)-1:0] v15_data_vector,
	input logic [(NUM_PE*DATA_WIDTH)-1:0] v15_weight_vector,
	input logic [(NUM_PE*V15_ACC_WIDTH)-1:0] v15_acc_vector,
	input logic v16_valid_in,
	input logic [(NUM_PE*DATA_WIDTH)-1:0] v16_data_vector,
	input logic [(NUM_PE*DATA_WIDTH)-1:0] v16_weight_vector,
	input logic [(NUM_PE*V15_ACC_WIDTH)-1:0] v16_acc_vector,
	input logic [V16_RESULT_ADDR_WIDTH-1:0] v16_result_addr,
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
	output logic signed [(2*DATA_WIDTH)+$clog2(NUM_PE)-1:0] y_pe_chain_v5,
	output logic signed [(2*DATA_WIDTH)+$clog2(NUM_PE)-1:0] y_pe_chain_v6,
	output logic signed [V7_ACC_WIDTH-1:0] y_pe_chain_v7,
	output logic valid_out_pe_chain_v7,
	output logic error_out_pe_chain_v7,
	output logic [NUM_PE-1:0] overflow_out_pe_chain_v7,
	output logic [(NUM_PE*DATA_WIDTH)-1:0] v7_pe_data_trace,
	output logic [(NUM_PE*DATA_WIDTH)-1:0] v7_pe_weight_trace,
	output logic [NUM_PE-1:0] v7_pe_valid_trace,
	output logic [DATA_WIDTH-1:0] ram_read_data,
	output logic signed [(2*DATA_WIDTH)+$clog2(NUM_PE)-1:0] y_pe_chain_v8,
	output logic valid_out_pe_chain_v8,
	output logic signed [(2*DATA_WIDTH)+$clog2(NUM_PE)-1:0] result_v9,
	output logic done_v9,
	output logic signed [(2*DATA_WIDTH)+$clog2(NUM_PE)-1:0] result_v10,
	output logic busy_v10,
	output logic done_v10,
	output logic [(NUM_PE*DATA_WIDTH)-1:0] a_read_data_v11,
	output logic [(NUM_PE*DATA_WIDTH)-1:0] b_read_data_v11,
	output logic signed [(2*DATA_WIDTH)+$clog2(NUM_PE)-1:0] y_pe_chain_v11,
	output logic valid_out_pe_chain_v11,
	output logic signed [(2*DATA_WIDTH)+$clog2(NUM_PE)-1:0] result_v12,
	output logic busy_v12,
	output logic done_v12,
	output logic error_v12,
	output logic signed [SPECIAL_RESULT_WIDTH-1:0] result_v13,
	output logic busy_v13,
	output logic done_v13,
	output logic error_v13,
	output logic [(NUM_DOT_UNITS*NUM_PE)-1:0] overflow_v13,
	output logic signed [V14_ACC_WIDTH-1:0] y_pe_chain_v14,
	output logic valid_out_pe_chain_v14,
	output logic error_out_pe_chain_v14,
	output logic [NUM_PE-1:0] overflow_out_pe_chain_v14,
	output logic [(NUM_PE*2*DATA_WIDTH)-1:0] v14_pe_product_trace,
	output logic [(NUM_PE*V15_ACC_WIDTH)-1:0] v15_result_vector,
	output logic valid_out_pe_chain_v15,
	output logic [(NUM_PE*V15_ACC_WIDTH)-1:0] v16_result_vector,
	output logic [(NUM_PE*V15_ACC_WIDTH)-1:0] v16_ram_result_vector,
	output logic valid_out_pe_chain_v16,
	output logic error_out_pe_chain_v16,
	output logic [NUM_PE-1:0] overflow_out_pe_chain_v16,
	output logic signed [SPECIAL_RESULT_WIDTH-1:0] result_vspecial,
	output logic busy_vspecial,
	output logic done_vspecial
);
	logic signed [DATA_WIDTH-1:0] array_a_v4 [0:3];
	logic signed [DATA_WIDTH-1:0] array_b_v4 [0:3];
	logic signed [(2*DATA_WIDTH)-1:0] array_y_v4 [0:3];
	logic signed [DATA_WIDTH-1:0] array_a [0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] array_b [0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] special_data [0:NUM_DOT_UNITS-1][0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] special_weights [0:NUM_DOT_UNITS-1][0:NUM_PE-1];
	logic signed [SPECIAL_ACC_WIDTH-1:0] special_bias [0:NUM_DOT_UNITS-1];
	logic signed [(2*DATA_WIDTH)-1:0] v14_products [0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] v15_data [0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] v15_weights [0:NUM_PE-1];
	logic signed [V15_ACC_WIDTH-1:0] v15_acc [0:NUM_PE-1];
	logic signed [V15_ACC_WIDTH-1:0] v15_results [0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] v16_data [0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] v16_weights [0:NUM_PE-1];
	logic signed [V15_ACC_WIDTH-1:0] v16_acc [0:NUM_PE-1];
	logic signed [V15_ACC_WIDTH-1:0] v16_results [0:NUM_PE-1];

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
		for (i = 0; i < 4; i++) begin : gen_v4_array_inputs
			assign array_a_v4[i] = chain_data_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
			assign array_b_v4[i] = chain_weight_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
		end
		for (i = 0; i < NUM_PE; i++) begin : gen_array_inputs
			assign array_a[i] = chain_data_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
			assign array_b[i] = chain_weight_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
		end
		for (i = 0; i < NUM_PE; i++) begin : gen_v15_inputs
			assign v15_data[i] = v15_data_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
			assign v15_weights[i] = v15_weight_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
			assign v15_acc[i] = v15_acc_vector[(i * V15_ACC_WIDTH) +: V15_ACC_WIDTH];
		end
		for (i = 0; i < NUM_PE; i++) begin : gen_v16_inputs
			assign v16_data[i] = v16_data_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
			assign v16_weights[i] = v16_weight_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
			assign v16_acc[i] = v16_acc_vector[(i * V15_ACC_WIDTH) +: V15_ACC_WIDTH];
		end
		for (i = 0; i < NUM_DOT_UNITS; i++) begin : gen_special_units
			assign special_bias[i] = special_biases[(i * SPECIAL_ACC_WIDTH) +: SPECIAL_ACC_WIDTH];
			for (genvar j = 0; j < NUM_PE; j++) begin : gen_special_elements
				assign special_data[i][j] = special_data_vectors[
					((i * NUM_PE + j) * DATA_WIDTH) +: DATA_WIDTH];
				assign special_weights[i][j] = special_weight_vectors[
					((i * NUM_PE + j) * DATA_WIDTH) +: DATA_WIDTH];
			end
		end
	endgenerate

	pe_chain_arrays #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(4)) pe_chain_arrays_4_dut (
		.a(array_a_v4), .b(array_b_v4), .y(array_y_v4)
	);
	pe_chain_v5 #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE)) pe_chain_v5_dut (
		.a(array_a), .b(array_b), .y(y_pe_chain_v5)
	);
	pe_chain_v6 #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE)) pe_chain_v6_dut (
		.clk(clk), .rst(rst), .a(array_a), .b(array_b), .y(y_pe_chain_v6)
	);
	pe_chain_v7 #(
		.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .ACC_WIDTH(V7_ACC_WIDTH)
	) pe_chain_v7_dut (
		.clk(clk), .rst(rst), .valid_in(valid_in), .a(array_a), .b(array_b),
		.y(y_pe_chain_v7), .valid_out(valid_out_pe_chain_v7),
		.error_out(error_out_pe_chain_v7),
		.overflow_out(overflow_out_pe_chain_v7)
	);
	// Flatten the operands present at each V7 PE so the cocotb test can prove
	// the temporal mapping PE[i] <- input_vector[iteration-i].
	generate
		for (genvar trace_index = 0; trace_index < NUM_PE; trace_index++) begin : gen_v7_trace
			assign v7_pe_data_trace[(trace_index * DATA_WIDTH) +: DATA_WIDTH] =
				pe_chain_v7_dut.gen_pipeline_pe[trace_index].stage_a;
			assign v7_pe_weight_trace[(trace_index * DATA_WIDTH) +: DATA_WIDTH] =
				pe_chain_v7_dut.gen_pipeline_pe[trace_index].stage_b;
			assign v7_pe_valid_trace[trace_index] =
				pe_chain_v7_dut.chain_valid[trace_index];
		end
	endgenerate

	simple_ram #(.DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(2)) ram_dut (
		.clk(clk), .we(ram_we), .write_addr(ram_write_addr),
		.write_data(ram_write_data), .read_addr(ram_read_addr),
		.read_data(ram_read_data)
	);
	pe_chain_v8 #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .ADDR_WIDTH(2)) pe_chain_v8_dut (
		.clk(clk), .rst(rst), .load_we(memory_load_we),
		.load_weights(memory_load_weights), .load_addr(memory_load_addr),
		.load_data(memory_load_data), .data_addr(data_addr),
		.weight_addr(weight_addr), .valid_in(v8_valid_in),
		.y(y_pe_chain_v8), .valid_out(valid_out_pe_chain_v8)
	);
	pe_system_v9 #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .ADDR_WIDTH(2)) pe_system_v9_dut (
		.clk(clk), .rst(rst), .load_we(memory_load_we),
		.load_weights(memory_load_weights), .load_addr(memory_load_addr),
		.load_data(memory_load_data), .data_addr(data_addr),
		.weight_addr(weight_addr), .start(start),
		.result(result_v9), .done(done_v9)
	);
	pe_system_v10 #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .ADDR_WIDTH(2)) pe_system_v10_dut (
		.clk(clk), .rst(rst), .load_we(memory_load_we),
		.load_weights(memory_load_weights), .load_addr(memory_load_addr),
		.load_data(memory_load_data), .data_addr(data_addr),
		.weight_addr(weight_addr), .start(start),
		.busy(busy_v10), .done(done_v10), .result(result_v10)
	);
	pe_chain_v11 #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .ADDR_WIDTH(2)) pe_chain_v11_dut (
		.clk(clk), .rst(rst),
		.a_write_enable(memory_load_we && !memory_load_weights),
		.b_write_enable(memory_load_we && memory_load_weights),
		.write_addr(memory_load_addr), .write_data(memory_load_data),
		.a_read_addr(data_addr), .b_read_addr(weight_addr),
		.valid_in(v11_valid_in), .a_read_data(a_read_data_v11),
		.b_read_data(b_read_data_v11), .y(y_pe_chain_v11),
		.valid_out(valid_out_pe_chain_v11)
	);
	pe_system_v12 #(.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .ADDR_WIDTH(2)) pe_system_v12_dut (
		.clk(clk), .rst(rst), .load_we(memory_load_we),
		.load_weights(memory_load_weights), .load_addr(memory_load_addr),
		.load_data(memory_load_data), .data_addr(data_addr),
		.weight_addr(weight_addr), .start(start), .busy(busy_v12),
		.done(done_v12), .error(error_v12), .result(result_v12)
	);
	pe_system_v13 #(
		.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .NUM_UNITS(NUM_DOT_UNITS),
		.ACC_WIDTH(SPECIAL_ACC_WIDTH), .RESULT_WIDTH(SPECIAL_RESULT_WIDTH),
		.RESULT_ADDR_WIDTH(SPECIAL_ADDR_WIDTH)
	) pe_system_v13_dut (
		.clk(clk), .rst(rst), .valid_in(special_valid_in),
		.data(special_data), .weights(special_weights), .biases(special_bias),
		.result_read_addr(special_result_addr), .result_read_data(result_v13),
		.busy(busy_v13), .done(done_v13), .error(error_v13),
		.overflow_out(overflow_v13)
	);
	pe_chain_v14 #(
		.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .ACC_WIDTH(V14_ACC_WIDTH)
	) pe_chain_v14_dut (
		.clk(clk), .rst(rst), .valid_in(valid_in), .a(array_a), .b(array_b),
		.y(y_pe_chain_v14), .valid_out(valid_out_pe_chain_v14),
		.error_out(error_out_pe_chain_v14),
		.overflow_out(overflow_out_pe_chain_v14),
		.products(v14_products)
	);
	generate
		for (genvar v14_index = 0; v14_index < NUM_PE; v14_index++) begin : gen_v14_trace
			assign v14_pe_product_trace[(v14_index * 2 * DATA_WIDTH) +: (2 * DATA_WIDTH)] =
				v14_products[v14_index];
		end
	endgenerate
	pe_chain_v15 #(
		.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .NUM_EL(NUM_EL),
		.ACC_WIDTH(V15_ACC_WIDTH)
	) pe_chain_v15_dut (
		.clk(clk), .rst(rst), .valid_in(v15_valid_in),
		.a(v15_data), .b(v15_weights), .acc_in(v15_acc),
		.results(v15_results),
		.valid_out(valid_out_pe_chain_v15)
	);
	generate
		for (genvar v15_index = 0; v15_index < NUM_PE; v15_index++) begin : gen_v15_outputs
			assign v15_result_vector[(v15_index * V15_ACC_WIDTH) +: V15_ACC_WIDTH] =
				v15_results[v15_index];
		end
	endgenerate
	pe_chain_v16 #(
		.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .NUM_EL(NUM_EL),
		.ACC_WIDTH(V15_ACC_WIDTH), .RESULT_ADDR_WIDTH(V16_RESULT_ADDR_WIDTH)
	) pe_chain_v16_dut (
		.clk(clk), .rst(rst), .valid_in(v16_valid_in),
		.a(v16_data), .b(v16_weights), .acc_in(v16_acc),
		.result_read_addr(v16_result_addr), .results(v16_results),
		.result_read_data(v16_ram_result_vector),
		.valid_out(valid_out_pe_chain_v16),
		.error_out(error_out_pe_chain_v16),
		.overflow_out(overflow_out_pe_chain_v16)
	);
	generate
		for (genvar v16_index = 0; v16_index < NUM_PE; v16_index++) begin : gen_v16_outputs
			assign v16_result_vector[(v16_index * V15_ACC_WIDTH) +: V15_ACC_WIDTH] =
				v16_results[v16_index];
		end
	endgenerate
	dot_product_chain_vspecial #(
		.DATA_WIDTH(DATA_WIDTH), .NUM_PE(NUM_PE), .NUM_UNITS(NUM_DOT_UNITS),
		.ACC_WIDTH(SPECIAL_ACC_WIDTH), .RESULT_WIDTH(SPECIAL_RESULT_WIDTH),
		.RESULT_ADDR_WIDTH(SPECIAL_ADDR_WIDTH)
	) dot_product_chain_vspecial_dut (
		.clk(clk), .rst(rst), .valid_in(special_valid_in),
		.data(special_data), .weights(special_weights), .biases(special_bias),
		.result_read_addr(special_result_addr), .result_read_data(result_vspecial),
		.busy(busy_vspecial), .done(done_vspecial)
	);

	assign y_pe_array_0 = array_y_v4[0];
	assign y_pe_array_1 = array_y_v4[1];
	assign y_pe_array_2 = array_y_v4[2];
	assign y_pe_array_3 = array_y_v4[3];
endmodule
