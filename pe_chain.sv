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


// Simplified V15 element-wise vector multiplier. NUM_EL sets both the length
// of the two vectors and the number of parallel PEs. Each PE produces its own
// result; this version intentionally has no reduction or post-processing.
module pe_chain_v15 #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_EL = 4
)(
	input logic signed [DATA_WIDTH-1:0] a [0:NUM_EL-1],
	input logic signed [DATA_WIDTH-1:0] b [0:NUM_EL-1],
	output logic signed [(2*DATA_WIDTH)-1:0] products [0:NUM_EL-1]
);
	genvar element_index;
	generate
		for (element_index = 0; element_index < NUM_EL; element_index++) begin : gen_element_pe
			pe_v15 #(.DATA_WIDTH(DATA_WIDTH)) pe_dut (
				.a(a[element_index]),
				.b(b[element_index]),
				.product(products[element_index])
			);
		end
	endgenerate
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


module pe_chain_v5 #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 2,
	parameter int ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE)
)(
	input logic signed [DATA_WIDTH-1:0] a [0:NUM_PE-1],
	input logic signed [DATA_WIDTH-1:0] b [0:NUM_PE-1],
	output logic signed [ACC_WIDTH-1:0] y
);
	logic signed [ACC_WIDTH-1:0] chain_acc [0:NUM_PE];

	assign chain_acc[0] = '0;

	genvar i;
	generate
		for (i = 0; i < NUM_PE; i++) begin : gen_dot_product_pe
			pe_v5 #(
				.DATA_WIDTH(DATA_WIDTH),
				.ACC_WIDTH(ACC_WIDTH)
			) pe_dut (
				.a(a[i]),
				.b(b[i]),
				.acc_in(chain_acc[i]),
				.y(chain_acc[i+1])
			);
		end
	endgenerate

	assign y = chain_acc[NUM_PE];
endmodule


// V6 dot-product pipeline. A new input vector can be accepted every cycle;
// its result appears NUM_PE rising edges later.
module pe_chain_v6 #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 2,
	parameter int ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE)
)(
	input logic clk,
	input logic rst,
	input logic signed [DATA_WIDTH-1:0] a [0:NUM_PE-1],
	input logic signed [DATA_WIDTH-1:0] b [0:NUM_PE-1],
	output logic signed [ACC_WIDTH-1:0] y
);
	logic signed [ACC_WIDTH-1:0] chain_acc [0:NUM_PE];
	logic signed [DATA_WIDTH-1:0] delayed_a [0:NUM_PE-1][0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] delayed_b [0:NUM_PE-1][0:NUM_PE-1];

	assign chain_acc[0] = '0;

	genvar stage;
	generate
		for (stage = 0; stage < NUM_PE; stage++) begin : gen_delay_stages
			always_ff @(posedge clk) begin
				if (rst) begin
					for (integer j = 0; j < NUM_PE; j++) begin
						delayed_a[stage][j] <= '0;
						delayed_b[stage][j] <= '0;
					end
				end else begin
					for (integer j = 0; j < NUM_PE; j++) begin
						if (stage == 0) begin
							delayed_a[stage][j] <= a[j];
							delayed_b[stage][j] <= b[j];
						end else begin
							delayed_a[stage][j] <= delayed_a[stage-1][j];
							delayed_b[stage][j] <= delayed_b[stage-1][j];
						end
					end
				end
			end
		end

		for (stage = 0; stage < NUM_PE; stage++) begin : gen_pipeline_pe
			wire signed [DATA_WIDTH-1:0] stage_a;
			wire signed [DATA_WIDTH-1:0] stage_b;

			if (stage == 0) begin : gen_first_stage_inputs
				assign stage_a = a[stage];
				assign stage_b = b[stage];
			end else begin : gen_delayed_stage_inputs
				assign stage_a = delayed_a[stage-1][stage];
				assign stage_b = delayed_b[stage-1][stage];
			end

			pe_v6 #(
				.DATA_WIDTH(DATA_WIDTH),
				.ACC_WIDTH(ACC_WIDTH)
			) pe_dut (
				.clk(clk),
				.rst(rst),
				.a(stage_a),
				.b(stage_b),
				.acc_in(chain_acc[stage]),
				.y(chain_acc[stage+1])
			);
		end
	endgenerate

	assign y = chain_acc[NUM_PE];
endmodule


// V7 dot-product pipeline. valid_in marks an accepted input vector and
// valid_out marks the corresponding result after it crosses every PE stage.
module pe_chain_v7 #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 2,
	parameter int ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE)
)(
	input logic clk,
	input logic rst,
	input logic valid_in,
	input logic signed [DATA_WIDTH-1:0] a [0:NUM_PE-1],
	input logic signed [DATA_WIDTH-1:0] b [0:NUM_PE-1],
	output logic signed [ACC_WIDTH-1:0] y,
	output logic valid_out,
	output logic error_out,
	output logic [NUM_PE-1:0] overflow_out
);
	logic signed [ACC_WIDTH-1:0] chain_acc [0:NUM_PE];
	logic chain_valid [0:NUM_PE];
	logic chain_error [0:NUM_PE];
	wire [NUM_PE-1:0] chain_overflow [0:NUM_PE];
	logic signed [DATA_WIDTH-1:0] delayed_a [0:NUM_PE-1][0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] delayed_b [0:NUM_PE-1][0:NUM_PE-1];

	assign chain_acc[0] = '0;
	assign chain_valid[0] = valid_in;
	assign chain_error[0] = 1'b0;
	assign chain_overflow[0] = '0;

	genvar stage;
	generate
		for (stage = 0; stage < NUM_PE; stage++) begin : gen_delay_stages
			always_ff @(posedge clk) begin
				if (rst) begin
					for (integer j = 0; j < NUM_PE; j++) begin
						delayed_a[stage][j] <= '0;
						delayed_b[stage][j] <= '0;
					end
				end else begin
					for (integer j = 0; j < NUM_PE; j++) begin
						if (stage == 0) begin
							delayed_a[stage][j] <= a[j];
							delayed_b[stage][j] <= b[j];
						end else begin
							delayed_a[stage][j] <= delayed_a[stage-1][j];
							delayed_b[stage][j] <= delayed_b[stage-1][j];
						end
					end
				end
			end
		end

		for (stage = 0; stage < NUM_PE; stage++) begin : gen_pipeline_pe
			wire signed [DATA_WIDTH-1:0] stage_a;
			wire signed [DATA_WIDTH-1:0] stage_b;
			wire stage_local_overflow;
			logic [NUM_PE-1:0] stage_overflow_out;
			localparam logic [NUM_PE-1:0] STAGE_OVERFLOW_MASK =
				({{(NUM_PE-1){1'b0}}, 1'b1} << stage);
			assign chain_overflow[stage+1] = stage_overflow_out;

			always_ff @(posedge clk) begin
				if (rst)
					stage_overflow_out <= '0;
				else if (stage_local_overflow)
					stage_overflow_out <=
						chain_overflow[stage] | STAGE_OVERFLOW_MASK;
				else
					stage_overflow_out <= chain_overflow[stage];
			end

			if (stage == 0) begin : gen_first_stage_inputs
				assign stage_a = a[stage];
				assign stage_b = b[stage];
			end else begin : gen_delayed_stage_inputs
				assign stage_a = delayed_a[stage-1][stage];
				assign stage_b = delayed_b[stage-1][stage];
			end

			pe_v7 #(
				.DATA_WIDTH(DATA_WIDTH),
				.ACC_WIDTH(ACC_WIDTH)
			) pe_dut (
				.clk(clk),
				.rst(rst),
				.valid_in(chain_valid[stage]),
				.error_in(chain_error[stage]),
				.a(stage_a),
				.b(stage_b),
				.acc_in(chain_acc[stage]),
				.y(chain_acc[stage+1]),
				.valid_out(chain_valid[stage+1]),
				.error_out(chain_error[stage+1]),
				.local_overflow(stage_local_overflow)
			);
		end
	endgenerate

	assign y = chain_acc[NUM_PE];
	assign valid_out = chain_valid[NUM_PE];
	assign error_out = chain_error[NUM_PE];
	assign overflow_out = chain_overflow[NUM_PE];
endmodule


// V14 parallel dot-product array. Unlike the systolic V6/V7 pipelines, every
// PE consumes the matching element of the same input vector concurrently.
// The products are reduced combinationally and the complete sum is registered
// on the edge that accepts valid_in, allowing a new vector on every cycle. If
// the reduction overflows, the result becomes an error token and overflow_out
// identifies the PE whose product first exceeded the accumulator range.
module pe_chain_v14 #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 4,
	parameter int ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE)
)(
	input logic clk,
	input logic rst,
	input logic valid_in,
	input logic signed [DATA_WIDTH-1:0] a [0:NUM_PE-1],
	input logic signed [DATA_WIDTH-1:0] b [0:NUM_PE-1],
	output logic signed [ACC_WIDTH-1:0] y,
	output logic valid_out,
	output logic error_out,
	output logic [NUM_PE-1:0] overflow_out,
	output logic signed [(2*DATA_WIDTH)-1:0] products [0:NUM_PE-1]
);
	logic signed [ACC_WIDTH-1:0] parallel_sum;
	logic signed [ACC_WIDTH:0] extended_parallel_sum;
	logic parallel_overflow;
	logic [NUM_PE-1:0] parallel_overflow_map;

	genvar pe_index;
	generate
		for (pe_index = 0; pe_index < NUM_PE; pe_index++) begin : gen_parallel_pe
			pe_v14 #(.DATA_WIDTH(DATA_WIDTH)) pe_dut (
				.a(a[pe_index]),
				.b(b[pe_index]),
				.product(products[pe_index])
			);
		end
	endgenerate

	always @* begin
		parallel_sum = '0;
		extended_parallel_sum = '0;
		parallel_overflow = 1'b0;
		parallel_overflow_map = '0;
		for (integer i = 0; i < NUM_PE; i++) begin
			if (!parallel_overflow) begin
				extended_parallel_sum =
					{parallel_sum[ACC_WIDTH-1], parallel_sum} +
					{{(ACC_WIDTH + 1 - (2*DATA_WIDTH)){
						products[i][(2*DATA_WIDTH)-1]}}, products[i]};
				if (extended_parallel_sum[ACC_WIDTH] !=
					extended_parallel_sum[ACC_WIDTH-1]) begin
					parallel_sum = '0;
					parallel_overflow = 1'b1;
					parallel_overflow_map[i] = 1'b1;
				end else begin
					parallel_sum = extended_parallel_sum[ACC_WIDTH-1:0];
				end
			end
		end
	end

	always_ff @(posedge clk) begin
		if (rst) begin
			y <= '0;
			valid_out <= 1'b0;
			error_out <= 1'b0;
			overflow_out <= '0;
		end else begin
			error_out <= 1'b0;
			overflow_out <= '0;
			if (valid_in && parallel_overflow) begin
				y <= '0;
				valid_out <= 1'b0;
				error_out <= 1'b1;
				overflow_out <= parallel_overflow_map;
			end else if (valid_in) begin
				y <= parallel_sum;
				valid_out <= 1'b1;
			end else begin
				y <= '0;
				valid_out <= 1'b0;
			end
		end
	end
endmodule
