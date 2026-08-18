// V13 dot-product unit. The PE pipeline retains the full dot-product
// accumulator width; one additional result bit preserves the subsequent
// signed bias addition.
module dot_product_unit_v13 #(
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
	output logic valid_out,
	output logic error_out,
	output logic [NUM_PE-1:0] overflow_out
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
		.valid_out(valid_out),
		.error_out(error_out),
		.overflow_out(overflow_out)
	);

	assign extended_dot_product = {
		{(RESULT_WIDTH-ACC_WIDTH){dot_product[ACC_WIDTH-1]}}, dot_product
	};
	assign extended_bias = {
		{(RESULT_WIDTH-BIAS_WIDTH){bias[BIAS_WIDTH-1]}}, bias
	};
	assign result = valid_out ? extended_dot_product + extended_bias : '0;
endmodule


// V13 chains complete dot-product units. Each unit consumes its own data
// vector, weight vector, and bias. Completion advances the valid token to the
// next unit and writes the biased result to that unit's result-RAM address.
module dot_product_chain_v13 #(
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
	output logic done,
	output logic error,
	output logic [(NUM_UNITS*NUM_PE)-1:0] overflow_out
);
	logic accepted_valid;
	logic launch_valid;
	logic unit_start [0:NUM_UNITS-1];
	logic unit_valid [0:NUM_UNITS-1];
	logic unit_error [0:NUM_UNITS-1];
	logic unit_complete [0:NUM_UNITS-1];
	logic [NUM_PE-1:0] unit_overflow [0:NUM_UNITS-1];
	logic [NUM_PE-1:0] inactive_pe_mask;
	logic signed [RESULT_WIDTH-1:0] unit_result [0:NUM_UNITS-1];
	logic signed [DATA_WIDTH-1:0] captured_data [0:NUM_UNITS-1][0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] captured_weights [0:NUM_UNITS-1][0:NUM_PE-1];
	logic signed [BIAS_WIDTH-1:0] captured_biases [0:NUM_UNITS-1];
	logic result_write_enable;
	logic [RESULT_ADDR_WIDTH-1:0] result_write_addr;
	logic [RESULT_WIDTH-1:0] result_write_data;
	logic [RESULT_WIDTH-1:0] result_read_data_unsigned;

	assign accepted_valid = valid_in && !busy;
	assign unit_start[0] = launch_valid;
	assign result_read_data = $signed(result_read_data_unsigned);

	genvar unit_index;
	generate
		for (unit_index = 0; unit_index < NUM_UNITS; unit_index++) begin : gen_units
			wire [NUM_PE-1:0] unit_inactive_pe_mask;
			assign unit_complete[unit_index] =
				unit_valid[unit_index] || unit_error[unit_index];
			if (unit_index == 0) begin : gen_first_unit_mask
				assign unit_inactive_pe_mask = inactive_pe_mask;
			end else begin : gen_later_unit_mask
				// The next unit starts on the edge that records the preceding
				// overflow. Include that just-completed unit directly so the
				// new inactive bit takes effect without an extra launch cycle.
				assign unit_inactive_pe_mask = inactive_pe_mask |
					(unit_error[unit_index-1] ? unit_overflow[unit_index-1] : '0);
			end
			if (unit_index > 0) begin : gen_unit_start
				assign unit_start[unit_index] = unit_complete[unit_index-1];
			end

			wire signed [DATA_WIDTH-1:0] unit_data [0:NUM_PE-1];
			wire signed [DATA_WIDTH-1:0] unit_weights [0:NUM_PE-1];
			for (genvar element_index = 0; element_index < NUM_PE; element_index++) begin : gen_elements
				assign unit_data[element_index] = unit_inactive_pe_mask[element_index]
					? '0 : captured_data[unit_index][element_index];
				assign unit_weights[element_index] = unit_inactive_pe_mask[element_index]
					? '0 : captured_weights[unit_index][element_index];
			end

			dot_product_unit_v13 #(
				.DATA_WIDTH(DATA_WIDTH),
				.NUM_PE(NUM_PE),
				.ACC_WIDTH(ACC_WIDTH),
				.BIAS_WIDTH(BIAS_WIDTH),
				.RESULT_WIDTH(RESULT_WIDTH)
			) unit (
				.clk(clk),
				.rst(rst),
				.valid_in(unit_start[unit_index]),
				.data(unit_data),
				.weights(unit_weights),
				.bias(captured_biases[unit_index]),
				.result(unit_result[unit_index]),
				.valid_out(unit_valid[unit_index]),
				.error_out(unit_error[unit_index]),
				.overflow_out(unit_overflow[unit_index])
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
			if (unit_complete[i]) begin
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
			error <= 1'b0;
			overflow_out <= '0;
			inactive_pe_mask <= '0;
			launch_valid <= 1'b0;
			for (integer unit_number = 0; unit_number < NUM_UNITS; unit_number++) begin
				captured_biases[unit_number] <= '0;
				for (integer element_number = 0; element_number < NUM_PE; element_number++) begin
					captured_data[unit_number][element_number] <= '0;
					captured_weights[unit_number][element_number] <= '0;
				end
			end
		end else begin
			done <= unit_complete[NUM_UNITS-1];
			launch_valid <= accepted_valid;
			if (accepted_valid) begin
				busy <= 1'b1;
				error <= 1'b0;
				overflow_out <= '0;
				inactive_pe_mask <= '0;
				for (integer unit_number = 0; unit_number < NUM_UNITS; unit_number++) begin
					captured_biases[unit_number] <= biases[unit_number];
					for (integer element_number = 0; element_number < NUM_PE; element_number++) begin
						captured_data[unit_number][element_number] <= data[unit_number][element_number];
						captured_weights[unit_number][element_number] <= weights[unit_number][element_number];
					end
				end
			end else begin
				for (integer completed_unit = 0; completed_unit < NUM_UNITS; completed_unit++) begin
					if (unit_error[completed_unit]) begin
						error <= 1'b1;
						inactive_pe_mask <=
							inactive_pe_mask | unit_overflow[completed_unit];
						overflow_out[(completed_unit * NUM_PE) +: NUM_PE] <=
							unit_overflow[completed_unit];
					end
				end
				if (unit_complete[NUM_UNITS-1])
					busy <= 1'b0;
			end
		end
	end
endmodule


// Preserve the experimental VSpecial names as compatibility wrappers around
// the numbered V13 interface.
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
	dot_product_unit_v13 #(
		.DATA_WIDTH(DATA_WIDTH),
		.NUM_PE(NUM_PE),
		.ACC_WIDTH(ACC_WIDTH),
		.BIAS_WIDTH(BIAS_WIDTH),
		.RESULT_WIDTH(RESULT_WIDTH)
	) implementation (
		.clk(clk),
		.rst(rst),
		.valid_in(valid_in),
		.data(data),
		.weights(weights),
		.bias(bias),
		.result(result),
		.valid_out(valid_out),
		.error_out(),
		.overflow_out()
	);
endmodule


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
	dot_product_chain_v13 #(
		.DATA_WIDTH(DATA_WIDTH),
		.NUM_PE(NUM_PE),
		.NUM_UNITS(NUM_UNITS),
		.ACC_WIDTH(ACC_WIDTH),
		.BIAS_WIDTH(BIAS_WIDTH),
		.RESULT_WIDTH(RESULT_WIDTH),
		.RESULT_ADDR_WIDTH(RESULT_ADDR_WIDTH)
	) implementation (
		.clk(clk),
		.rst(rst),
		.valid_in(valid_in),
		.data(data),
		.weights(weights),
		.biases(biases),
		.result_read_addr(result_read_addr),
		.result_read_data(result_read_data),
		.busy(busy),
		.done(done),
		.error(),
		.overflow_out()
	);
endmodule


// System-level alias matching the naming used by the V9, V10 and V12 command
// controllers.  V13 commands carry operands directly and store one result per
// dot-product unit in the internal result RAM.
module pe_system_v13 #(
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
	output logic done,
	output logic error,
	output logic [(NUM_UNITS*NUM_PE)-1:0] overflow_out
);
	dot_product_chain_v13 #(
		.DATA_WIDTH(DATA_WIDTH),
		.NUM_PE(NUM_PE),
		.NUM_UNITS(NUM_UNITS),
		.ACC_WIDTH(ACC_WIDTH),
		.BIAS_WIDTH(BIAS_WIDTH),
		.RESULT_WIDTH(RESULT_WIDTH),
		.RESULT_ADDR_WIDTH(RESULT_ADDR_WIDTH)
	) implementation (
		.clk(clk),
		.rst(rst),
		.valid_in(valid_in),
		.data(data),
		.weights(weights),
		.biases(biases),
		.result_read_addr(result_read_addr),
		.result_read_data(result_read_data),
		.busy(busy),
		.done(done),
		.error(error),
		.overflow_out(overflow_out)
	);
endmodule
