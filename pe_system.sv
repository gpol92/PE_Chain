// V8 stores complete input and weight vectors in two RAMs. Each RAM word is
// unpacked into NUM_PE signed elements before entering the V7 pipeline.
module pe_chain_v8 #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 4,
	parameter int ADDR_WIDTH = 2,
	parameter int VECTOR_WIDTH = DATA_WIDTH * NUM_PE,
	parameter int ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE)
)(
	input logic clk,
	input logic rst,
	input logic load_we,
	input logic load_weights,
	input logic [ADDR_WIDTH-1:0] load_addr,
	input logic [VECTOR_WIDTH-1:0] load_data,
	input logic [ADDR_WIDTH-1:0] data_addr,
	input logic [ADDR_WIDTH-1:0] weight_addr,
	input logic valid_in,
	output logic signed [ACC_WIDTH-1:0] y,
	output logic valid_out
);
	logic [VECTOR_WIDTH-1:0] data_vector;
	logic [VECTOR_WIDTH-1:0] weight_vector;
	logic signed [DATA_WIDTH-1:0] chain_a [0:NUM_PE-1];
	logic signed [DATA_WIDTH-1:0] chain_b [0:NUM_PE-1];

	simple_ram #(
		.DATA_WIDTH(VECTOR_WIDTH),
		.ADDR_WIDTH(ADDR_WIDTH)
	) data_ram (
		.clk(clk),
		.we(load_we && !load_weights),
		.write_addr(load_addr),
		.write_data(load_data),
		.read_addr(data_addr),
		.read_data(data_vector)
	);

	simple_ram #(
		.DATA_WIDTH(VECTOR_WIDTH),
		.ADDR_WIDTH(ADDR_WIDTH)
	) weight_ram (
		.clk(clk),
		.we(load_we && load_weights),
		.write_addr(load_addr),
		.write_data(load_data),
		.read_addr(weight_addr),
		.read_data(weight_vector)
	);

	genvar i;
	generate
		for (i = 0; i < NUM_PE; i++) begin : gen_vector_elements
			assign chain_a[i] = data_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
			assign chain_b[i] = weight_vector[(i * DATA_WIDTH) +: DATA_WIDTH];
		end
	endgenerate

	pe_chain_v7 #(
		.DATA_WIDTH(DATA_WIDTH),
		.NUM_PE(NUM_PE),
		.ACC_WIDTH(ACC_WIDTH)
	) pipeline (
		.clk(clk),
		.rst(rst),
		.valid_in(valid_in),
		.a(chain_a),
		.b(chain_b),
		.y(y),
		.valid_out(valid_out)
	);
endmodule


// V9 controls the RAM-backed datapath with a simple start/done handshake.
// A request is accepted in IDLE, RUN waits for the pipeline result, and DONE
// remains asserted while start is high before returning to IDLE.
module pe_system_v9 #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 4,
	parameter int ADDR_WIDTH = 2,
	parameter int VECTOR_WIDTH = DATA_WIDTH * NUM_PE,
	parameter int ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE)
)(
	input logic clk,
	input logic rst,
	input logic load_we,
	input logic load_weights,
	input logic [ADDR_WIDTH-1:0] load_addr,
	input logic [VECTOR_WIDTH-1:0] load_data,
	input logic [ADDR_WIDTH-1:0] data_addr,
	input logic [ADDR_WIDTH-1:0] weight_addr,
	input logic start,
	output logic signed [ACC_WIDTH-1:0] result,
	output logic done
);
	typedef enum logic [1:0] {
		IDLE,
		RUN,
		DONE
	} state_t;

	state_t state;
	logic pipeline_valid_in;
	logic pipeline_valid_out;
	logic signed [ACC_WIDTH-1:0] pipeline_y;

	assign pipeline_valid_in = (state == IDLE) && start;

	pe_chain_v8 #(
		.DATA_WIDTH(DATA_WIDTH),
		.NUM_PE(NUM_PE),
		.ADDR_WIDTH(ADDR_WIDTH),
		.VECTOR_WIDTH(VECTOR_WIDTH),
		.ACC_WIDTH(ACC_WIDTH)
	) datapath (
		.clk(clk),
		.rst(rst),
		.load_we(load_we),
		.load_weights(load_weights),
		.load_addr(load_addr),
		.load_data(load_data),
		.data_addr(data_addr),
		.weight_addr(weight_addr),
		.valid_in(pipeline_valid_in),
		.y(pipeline_y),
		.valid_out(pipeline_valid_out)
	);

	always_ff @(posedge clk) begin
		if (rst) begin
			state <= IDLE;
			result <= '0;
			done <= 1'b0;
		end else begin
			case (state)
				IDLE: begin
					done <= 1'b0;
					if (start)
						state <= RUN;
				end
				RUN: begin
					if (pipeline_valid_out) begin
						result <= pipeline_y;
						done <= 1'b1;
						state <= DONE;
					end
				end
				DONE: begin
					done <= 1'b1;
					if (!start) begin
						done <= 1'b0;
						state <= IDLE;
					end
				end
				default: begin
					state <= IDLE;
					result <= '0;
					done <= 1'b0;
				end
			endcase
		end
	end
endmodule


// V10 exposes an explicit command interface around the RAM-backed datapath.
// A command is accepted only in IDLE. busy is asserted for the whole RUN
// phase, and done is asserted when result is captured. DONE waits for start to
// be released, preventing a held command or a command presented while busy
// from starting another operation.
module pe_system_v10 #(
	parameter int DATA_WIDTH = 8,
	parameter int NUM_PE = 4,
	parameter int ADDR_WIDTH = 2,
	parameter int VECTOR_WIDTH = DATA_WIDTH * NUM_PE,
	parameter int ACC_WIDTH = (2 * DATA_WIDTH) + $clog2(NUM_PE)
)(
	input logic clk,
	input logic rst,
	input logic load_we,
	input logic load_weights,
	input logic [ADDR_WIDTH-1:0] load_addr,
	input logic [VECTOR_WIDTH-1:0] load_data,
	input logic [ADDR_WIDTH-1:0] data_addr,
	input logic [ADDR_WIDTH-1:0] weight_addr,
	input logic start,
	output logic busy,
	output logic done,
	output logic signed [ACC_WIDTH-1:0] result
);
	typedef enum logic [1:0] {
		IDLE,
		RUN,
		DONE
	} state_t;

	state_t state;
	logic pipeline_valid_in;
	logic pipeline_valid_out;
	logic signed [ACC_WIDTH-1:0] pipeline_y;

	assign pipeline_valid_in = (state == IDLE) && start;
	assign busy = (state == RUN);

	pe_chain_v8 #(
		.DATA_WIDTH(DATA_WIDTH),
		.NUM_PE(NUM_PE),
		.ADDR_WIDTH(ADDR_WIDTH),
		.VECTOR_WIDTH(VECTOR_WIDTH),
		.ACC_WIDTH(ACC_WIDTH)
	) datapath (
		.clk(clk),
		.rst(rst),
		.load_we(load_we),
		.load_weights(load_weights),
		.load_addr(load_addr),
		.load_data(load_data),
		.data_addr(data_addr),
		.weight_addr(weight_addr),
		.valid_in(pipeline_valid_in),
		.y(pipeline_y),
		.valid_out(pipeline_valid_out)
	);

	always_ff @(posedge clk) begin
		if (rst) begin
			state <= IDLE;
			result <= '0;
			done <= 1'b0;
		end else begin
			case (state)
				IDLE: begin
					done <= 1'b0;
					if (start)
						state <= RUN;
				end
				RUN: begin
					done <= 1'b0;
					if (pipeline_valid_out) begin
						result <= pipeline_y;
						done <= 1'b1;
						state <= DONE;
					end
				end
				DONE: begin
					done <= 1'b1;
					if (!start) begin
						done <= 1'b0;
						state <= IDLE;
					end
				end
				default: begin
					state <= IDLE;
					result <= '0;
					done <= 1'b0;
				end
			endcase
		end
	end
endmodule
