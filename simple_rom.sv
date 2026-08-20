// Combinational read-only memory. Address zero occupies the least-significant
// DATA_WIDTH bits of CONTENT.
module simple_rom #(
	parameter int DATA_WIDTH = 8,
	parameter int ADDR_WIDTH = 2,
	parameter logic [(DATA_WIDTH * (1 << ADDR_WIDTH))-1:0] CONTENT = '0
)(
	input logic [ADDR_WIDTH-1:0] read_addr,
	output logic [DATA_WIDTH-1:0] read_data
);
	assign read_data = CONTENT[(read_addr * DATA_WIDTH) +: DATA_WIDTH];
endmodule
