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
	output logic valid_out
);
	logic signed [ACC_WIDTH-1:0] chain_acc [0:NUM_PE];
	logic chain_valid [0:NUM_PE];
	logic signed [DATA_WIDTH-1:0] delayed_a [0:NUM_PE-1][0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] delayed_b [0:NUM_PE-1][0:NUM_PE-1];

	assign chain_acc[0] = '0;
	assign chain_valid[0] = valid_in;

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

			pe_v7 #(
				.DATA_WIDTH(DATA_WIDTH),
				.ACC_WIDTH(ACC_WIDTH)
			) pe_dut (
				.clk(clk),
				.rst(rst),
				.valid_in(chain_valid[stage]),
				.a(stage_a),
				.b(stage_b),
				.acc_in(chain_acc[stage]),
				.y(chain_acc[stage+1]),
				.valid_out(chain_valid[stage+1])
			);
		end
	endgenerate

	assign y = chain_acc[NUM_PE];
	assign valid_out = chain_valid[NUM_PE];
endmodule
