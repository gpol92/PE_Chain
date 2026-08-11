import cocotb
from cocotb_tools.runner import get_runner
from cocotb.triggers import Timer
from pathlib import Path
import logging
import argparse
import sys
import os 

mode = argparse.ArgumentParser(description="Set the expected value to make the test pass or fail")
mode.add_argument(
    "--passed", 
    action=argparse.BooleanOptionalAction, 
    default=True, 
    help="Default status PASS. Use --no-passed to fail."
)

if __name__ == "__main__":
    args = mode.parse_args()
    passed_value = "1" if args.passed else "0"
else:
    passed_value = "1" 

@cocotb.test()
async def test_product(dut):
    dut.a.value = 1
    dut.b.value = 2
    
    is_passed = os.getenv("TEST_PASSED_STATUS", "1") == "1"

    if is_passed:
        expected = 2
    else:
        expected = 3
    
    await Timer(1, unit="ns")
    
    # Estrarre il valore numerico intero (evita la stampa in formato binario)
    actual_value = dut.y.value.integer
    
    assert actual_value == expected, f"[FAIL] Dot product different from expected (Got {actual_value}, Expected {expected})"
    dut._log.info(f"[OK] Dot product value equal to expected ({actual_value})")

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
            "COCOTB_LOG_LEVEL": "INFO",  # <--- IMPOSTATO SU INFO PER VEDERE LA STAMPA DEL LOG DI OK E IL SUMMARY
            "GPI_LOG_LEVEL": "ERROR",
            "TEST_PASSED_STATUS": passed_value,
        },
    )
