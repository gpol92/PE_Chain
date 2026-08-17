// VSpecial dot-product unit. The PE pipeline retains the full dot-product
// accumulator width; one additional result bit preserves the subsequent
// signed bias addition.
module dot_product_unit_vspecial #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 4,
	parameter int ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE),
	parameter int BIAS_WIDTH = ACC_WIDTH,
	parameter int RESULT_WIDTH = ACC_WIDTH + 1
)(
	input logic clk,
	input logic rst,
	input logic valid_in,
	input logic signed [DATA_WIDTH-1:0] data [0:NUM_PE-1],
	input logic signed [DATA_WIDTH-1:0] weights [0:NUM_PE-1],
	input logic signed [BIAS_WIDTH-1:0] bias,
	output logic signed [RESULT_WIDTH-1:0] result,
	output logic valid_out
);
	logic signed [ACC_WIDTH-1:0] dot_product;
	logic signed [RESULT_WIDTH-1:0] extended_dot_product;
	logic signed [RESULT_WIDTH-1:0] extended_bias;

	pe_chain_v7 #(
		.DATA_WIDTH(DATA_WIDTH),
		.NUM_PE(NUM_PE),
		.ACC_WIDTH(ACC_WIDTH)
	) dot_product_pipeline (
		.clk(clk),
		.rst(rst),
		.valid_in(valid_in),
		.a(data),
		.b(weights),
		.y(dot_product),
		.valid_out(valid_out)
	);

	assign extended_dot_product = {
		{(RESULT_WIDTH-ACC_WIDTH){dot_product[ACC_WIDTH-1]}}, dot_product
	};
	assign extended_bias = {
		{(RESULT_WIDTH-BIAS_WIDTH){bias[BIAS_WIDTH-1]}}, bias
	};
	assign result = extended_dot_product + extended_bias;
endmodule


// VSpecial chains complete dot-product units. Each unit consumes its own data
// vector, weight vector, and bias. Completion advances the valid token to the
// next unit and writes the biased result to that unit's result-RAM address.
module dot_product_chain_vspecial #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 4,
	parameter int NUM_UNITS = 3,
	parameter int ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE),
	parameter int BIAS_WIDTH = ACC_WIDTH,
	parameter int RESULT_WIDTH = ACC_WIDTH + 1,
	parameter int RESULT_ADDR_WIDTH = (NUM_UNITS <= 1) ? 1 : $clog2(NUM_UNITS)
)(
	input logic clk,
	input logic rst,
	input logic valid_in,
	input logic signed [DATA_WIDTH-1:0] data [0:NUM_UNITS-1][0:NUM_PE-1],
	input logic signed [DATA_WIDTH-1:0] weights [0:NUM_UNITS-1][0:NUM_PE-1],
	input logic signed [BIAS_WIDTH-1:0] biases [0:NUM_UNITS-1],
	input logic [RESULT_ADDR_WIDTH-1:0] result_read_addr,
	output logic signed [RESULT_WIDTH-1:0] result_read_data,
	output logic busy,
	output logic done
);
	logic accepted_valid;
	logic launch_valid;
	logic unit_valid [0:NUM_UNITS];
	logic signed [RESULT_WIDTH-1:0] unit_result [0:NUM_UNITS-1];
	logic signed [DATA_WIDTH-1:0] captured_data [0:NUM_UNITS-1][0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] captured_weights [0:NUM_UNITS-1][0:NUM_PE-1];
	logic signed [BIAS_WIDTH-1:0] captured_biases [0:NUM_UNITS-1];
	logic result_write_enable;
	logic [RESULT_ADDR_WIDTH-1:0] result_write_addr;
	logic [RESULT_WIDTH-1:0] result_write_data;
	logic [RESULT_WIDTH-1:0] result_read_data_unsigned;

	assign accepted_valid = valid_in && !busy;
	assign unit_valid[0] = launch_valid;
	assign result_read_data = $signed(result_read_data_unsigned);

	genvar unit_index;
	generate
		for (unit_index = 0; unit_index < NUM_UNITS; unit_index++) begin : gen_units
			wire signed [DATA_WIDTH-1:0] unit_data [0:NUM_PE-1];
			wire signed [DATA_WIDTH-1:0] unit_weights [0:NUM_PE-1];
			for (genvar element_index = 0; element_index < NUM_PE; element_index++) begin : gen_elements
				assign unit_data[element_index] = captured_data[unit_index][element_index];
				assign unit_weights[element_index] = captured_weights[unit_index][element_index];
			end

			dot_product_unit_vspecial #(
				.DATA_WIDTH(DATA_WIDTH),
				.NUM_PE(NUM_PE),
				.ACC_WIDTH(ACC_WIDTH),
				.BIAS_WIDTH(BIAS_WIDTH),
				.RESULT_WIDTH(RESULT_WIDTH)
			) unit (
				.clk(clk),
				.rst(rst),
				.valid_in(unit_valid[unit_index]),
				.data(unit_data),
				.weights(unit_weights),
				.bias(captured_biases[unit_index]),
				.result(unit_result[unit_index]),
				.valid_out(unit_valid[unit_index+1])
			);
		end
	endgenerate

	// Unit completions cannot overlap because only one request may occupy the
	// chain. Select the completing unit as the single result-RAM write source.
	always_comb begin
		result_write_enable = 1'b0;
		result_write_addr = '0;
		result_write_data = '0;
		for (integer i = 0; i < NUM_UNITS; i++) begin
			if (unit_valid[i+1]) begin
				result_write_enable = 1'b1;
				result_write_addr = i;
				result_write_data = unit_result[i];
			end
		end
	end

	simple_ram #(
		.DATA_WIDTH(RESULT_WIDTH),
		.ADDR_WIDTH(RESULT_ADDR_WIDTH)
	) result_ram (
		.clk(clk),
		.we(result_write_enable),
		.write_addr(result_write_addr),
		.write_data(result_write_data),
		.read_addr(result_read_addr),
		.read_data(result_read_data_unsigned)
	);

	always_ff @(posedge clk) begin
		if (rst) begin
			busy <= 1'b0;
			done <= 1'b0;
			launch_valid <= 1'b0;
			for (integer unit_number = 0; unit_number < NUM_UNITS; unit_number++) begin
				captured_biases[unit_number] <= '0;
				for (integer element_number = 0; element_number < NUM_PE; element_number++) begin
					captured_data[unit_number][element_number] <= '0;
					captured_weights[unit_number][element_number] <= '0;
				end
			end
		end else begin
			done <= unit_valid[NUM_UNITS];
			launch_valid <= accepted_valid;
			if (accepted_valid) begin
				busy <= 1'b1;
				for (integer unit_number = 0; unit_number < NUM_UNITS; unit_number++) begin
					captured_biases[unit_number] <= biases[unit_number];
					for (integer element_number = 0; element_number < NUM_PE; element_number++) begin
						captured_data[unit_number][element_number] <= data[unit_number][element_number];
						captured_weights[unit_number][element_number] <= weights[unit_number][element_number];
					end
				end
			end else if (unit_valid[NUM_UNITS]) begin
				busy <= 1'b0;
			end
		end
	end
endmodule
