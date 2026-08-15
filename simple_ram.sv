// Single-port synchronous-write, asynchronous-read RAM.
module simple_ram #(
	parameter int DATA_WIDTH = 8,
	parameter int ADDR_WIDTH = 2
)(
	input logic clk,
	input logic we,
	input logic [ADDR_WIDTH-1:0] write_addr,
	input logic [DATA_WIDTH-1:0] write_data,
	input logic [ADDR_WIDTH-1:0] read_addr,
	output logic [DATA_WIDTH-1:0] read_data
);
	logic [DATA_WIDTH-1:0] memory [0:(1 << ADDR_WIDTH)-1];

	always_ff @(posedge clk) begin
		if (we)
			memory[write_addr] <= write_data;
	end

	always_comb begin
		read_data = memory[read_addr];
	end
endmodule
