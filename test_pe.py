import cocotb
from cocotb_tools.runner import get_runner
from cocotb.triggers import Timer
from pathlib import Path
import argparse
import sys
import os
import logging

# Keep the test output focused on the message emitted for a failed check.
logging.getLogger("cocotb.regression").setLevel(logging.ERROR)
test_logger = logging.getLogger(__name__)

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

mode.add_argument(
    "--version",
    choices=("v0", "v1", "pe", "all"),
    default="all",
    help="DUT to check (default: all; pe is the implementation in pe.sv)",
)

mode.add_argument(
    "--pechain",
    action="store_true",
    help="Test the manual and parameterized pe_chain implementations",
)

mode.add_argument(
    "--arrays",
    action="store_true",
    help="With --pechain, test the V4 array implementation",
)

if __name__ == "__main__":
    args = mode.parse_args()
    if args.arrays and not args.pechain:
        mode.error("--arrays requires --pechain")
    passed_value = "1" if args.passed else "0"
    positive_value = "1" if args.positive else "0"
    zero_value = "1" if args.zero else "0"
    version_value = args.version
    pechain_value = "1" if args.pechain else "0"
    arrays_value = "1" if args.arrays else "0"
else:
    passed_value = "1" 
    positive_value = "1"
    zero_value = "0"
    version_value = "all"
    pechain_value = "0"
    arrays_value = "0"


def signed_truncate(value, width):
    raw_value = value & ((1 << width) - 1)
    sign_bit = 1 << (width - 1)
    return raw_value - (1 << width) if raw_value & sign_bit else raw_value

@cocotb.test()
async def test_product(dut):
    positive = os.getenv("TEST_POSITIVE_VALUES", "1") == "1"
    zero = os.getenv("TEST_ZERO_VALUES", "0") == "1"
    a = 0 if zero else (1 if positive else -1)
    b = 2
    acc_in = 3
    dut.a.value = a
    dut.b.value = b
    dut.acc_in.value = acc_in
    
    is_passed = os.getenv("TEST_PASSED_STATUS", "1") == "1"

    data_width = len(dut.a)
    array_expected = [
        signed_truncate(a + index, data_width)
        * signed_truncate(b + index, data_width)
        for index in range(4)
    ]
    if not is_passed:
        array_expected[0] += 1

    if is_passed:
        expected_v0 = a * b
        expected_v1 = a * b + acc_in
        expected_pechain_2 = acc_in + 2 * a * b
        expected_pechain_4 = acc_in + 4 * a * b
    else:
        expected_v0 = a * b + 1
        expected_v1 = a * b + acc_in + 1
        expected_pechain_2 = acc_in + 2 * a * b + 1
        expected_pechain_4 = acc_in + 4 * a * b + 1
    
    await Timer(1, unit="ns")
    
    checks = {
        "v0": (dut.y_v0, expected_v0),
        "v1": (dut.y_v1, expected_v1),
        "pe": (dut.y_pe, expected_v1),
        "pechain_manual_2": (dut.y_pe_chain_manual_2, expected_pechain_2),
        "pechain_2": (dut.y_pe_chain_2, expected_pechain_2),
        "pechain_4": (dut.y_pe_chain_4, expected_pechain_4),
        "pearray_0": (dut.y_pe_array_0, array_expected[0]),
        "pearray_1": (dut.y_pe_array_1, array_expected[1]),
        "pearray_2": (dut.y_pe_array_2, array_expected[2]),
        "pearray_3": (dut.y_pe_array_3, array_expected[3]),
    }
    if os.getenv("TEST_PECHAIN", "0") == "1":
        if os.getenv("TEST_ARRAYS", "0") == "1":
            selected = {
                name: check for name, check in checks.items()
                if name.startswith("pearray_")
            }
        else:
            selected = {
                name: check for name, check in checks.items()
                if name.startswith("pechain_")
            }
    else:
        selected_version = os.getenv("TEST_VERSION", "all")
        default_checks = {
            name: check for name, check in checks.items()
            if not name.startswith(("pechain_", "pearray_"))
        }
        selected = default_checks if selected_version == "all" else {selected_version: checks[selected_version]}
    for name, (signal, expected) in selected.items():
        actual_value = signal.value.to_signed()
        if actual_value != expected:
            message = f"[FAIL] {name} value different from expected (Got {actual_value}, Expected {expected})"
            test_logger.error(message)
            assert actual_value == expected, message
        print(f"[OK] {name} value equal to expected ({actual_value})")

if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parent
    runner = get_runner("icarus")
    runner.build(
        sources=[
            project_dir / "pe.sv",
            project_dir / "pe_chain.sv",
            project_dir / "testbench.sv",
        ],
        hdl_toplevel="pe_testbench",
        always=True,
        timescale=("1ns", "1ps"),
    )

    runner.test(
        hdl_toplevel="pe_testbench", test_module="test_pe",
        extra_env={
            "COCOTB_LOG_LEVEL": "WARNING" if args.warning else "ERROR",
            "GPI_LOG_LEVEL": "ERROR",
            "TEST_PASSED_STATUS": passed_value,
            "TEST_POSITIVE_VALUES": positive_value,
            "TEST_ZERO_VALUES": zero_value,
            "TEST_VERSION": version_value,
            "TEST_PECHAIN": pechain_value,
            "TEST_ARRAYS": arrays_value,
        },
    )
