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

mode.add_argument(
    "--positive",
    action=argparse.BooleanOptionalAction,
    default=True,
    help = "Default positive values. Use --no-positive to fail"

)

mode.add_argument(
    "--zero",
    action="store_true",
    help="Use zero as the first operand"
)

mode.add_argument(
    "--warning",
    action="store_true",
    help="Show only Cocotb warnings and errors"
)

if __name__ == "__main__":
    args = mode.parse_args()
    passed_value = "1" if args.passed else "0"
    positive_value = "1" if args.positive else "0"
    zero_value = "1" if args.zero else "0"
else:
    passed_value = "1" 
    positive_value = "1"
    zero_value = "0"

@cocotb.test()
async def test_product(dut):
    positive = os.getenv("TEST_POSITIVE_VALUES", "1") == "1"
    zero = os.getenv("TEST_ZERO_VALUES", "0") == "1"
    a = 0 if zero else (1 if positive else -1)
    b = 2
    dut.a.value = a
    dut.b.value = b
    
    is_passed = os.getenv("TEST_PASSED_STATUS", "1") == "1"

    if is_passed:
        expected = a * b
    else:
        expected = a * b + 1
    
    await Timer(1, unit="ns")
    
    actual_value = dut.y.value.to_signed()
    
    assert actual_value == expected, f"[FAIL] Dot product different from expected (Got {actual_value}, Expected {expected})"
    print(f"[OK] Dot product value equal to expected ({actual_value})")

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
            "COCOTB_LOG_LEVEL": "WARNING" if args.warning else "INFO",
            "GPI_LOG_LEVEL": "ERROR",
            "TEST_PASSED_STATUS": passed_value,
            "TEST_POSITIVE_VALUES": positive_value,
            "TEST_ZERO_VALUES": zero_value,
        },
    )
