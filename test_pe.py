import cocotb
from cocotb_tools.runner import get_runner
from cocotb.triggers import Timer
from pathlib import Path
import logging


@cocotb.test()
async def test_product(dut):
    dut.a.value = 1
    dut.b.value = 2
    expected = 2
    await Timer(1, unit="ns")

    assert dut.y.value == expected, "[FAIL] Dot product different from expected"
    print("[OK] Dot product value equal to expected", flush=True)

if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parent
    runner = get_runner("icarus")
    runner.build(
        sources=[project_dir / "pe.sv"],
        hdl_toplevel="pe",
        always=True,
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="pe", test_module="test_pe",
        extra_env={
            "COCOTB_LOG_LEVEL": "ERROR",
            "GPI_LOG_LEVEL": "ERROR",
        },
    )
