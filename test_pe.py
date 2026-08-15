import cocotb
from cocotb_tools.runner import get_results, get_runner
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer
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

mode.add_argument(
    "--v5",
    action="store_true",
    help="With --pechain --arrays, test the V5 dot-product chain",
)

mode.add_argument(
    "--v6",
    action="store_true",
    help="With --pechain --arrays, test the V6 clocked pipeline",
)

mode.add_argument(
    "--v7",
    action="store_true",
    help="With --pechain --arrays, test the V7 valid pipeline",
)

mode.add_argument(
    "--v8",
    action="store_true",
    help="With --pechain --arrays, test RAM and the V8 memory-backed chain",
)

mode.add_argument(
    "--v9",
    action="store_true",
    help="With --pechain --arrays, test the V9 FSM-controlled system",
)

if __name__ == "__main__":
    args = mode.parse_args()
    if args.arrays and not args.pechain:
        mode.error("--arrays requires --pechain")
    if args.v5 and not (args.pechain and args.arrays):
        mode.error("--v5 requires --pechain --arrays")
    if args.v6 and not (args.pechain and args.arrays):
        mode.error("--v6 requires --pechain --arrays")
    if args.v7 and not (args.pechain and args.arrays):
        mode.error("--v7 requires --pechain --arrays")
    if args.v8 and not (args.pechain and args.arrays):
        mode.error("--v8 requires --pechain --arrays")
    if args.v9 and not (args.pechain and args.arrays):
        mode.error("--v9 requires --pechain --arrays")
    if sum((args.v5, args.v6, args.v7, args.v8, args.v9)) > 1:
        mode.error("--v5 through --v9 are mutually exclusive")
    passed_value = "1" if args.passed else "0"
    positive_value = "1" if args.positive else "0"
    zero_value = "1" if args.zero else "0"
    version_value = args.version
    pechain_value = "1" if args.pechain else "0"
    arrays_value = "1" if args.arrays else "0"
    v5_value = "1" if args.v5 else "0"
    v6_value = "1" if args.v6 else "0"
    v7_value = "1" if args.v7 else "0"
    v8_value = "1" if args.v8 else "0"
    v9_value = "1" if args.v9 else "0"
else:
    passed_value = "1" 
    positive_value = "1"
    zero_value = "0"
    version_value = "all"
    pechain_value = "0"
    arrays_value = "0"
    v5_value = "0"
    v6_value = "0"
    v7_value = "0"
    v8_value = "0"
    v9_value = "0"


def signed_truncate(value, width):
    raw_value = value & ((1 << width) - 1)
    sign_bit = 1 << (width - 1)
    return raw_value - (1 << width) if raw_value & sign_bit else raw_value


def pack_vector(values, width):
    packed = 0
    mask = (1 << width) - 1
    for index, value in enumerate(values):
        packed |= (value & mask) << (index * width)
    return packed


def dot_product(values, weights, width):
    return sum(
        signed_truncate(value, width) * signed_truncate(weight, width)
        for value, weight in zip(values, weights)
    )

@cocotb.test()
async def test_product(dut):
    v5 = os.getenv("TEST_V5", "0") == "1"
    v6 = os.getenv("TEST_V6", "0") == "1"
    v7 = os.getenv("TEST_V7", "0") == "1"
    v8 = os.getenv("TEST_V8", "0") == "1"
    v9 = os.getenv("TEST_V9", "0") == "1"
    is_passed = os.getenv("TEST_PASSED_STATUS", "1") == "1"

    if v8 or v9:
        cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
        dut.a.value = 0
        dut.b.value = 0
        dut.acc_in.value = 0
        dut.valid_in.value = 0
        dut.ram_we.value = 0
        dut.ram_write_addr.value = 0
        dut.ram_write_data.value = 0
        dut.ram_read_addr.value = 0
        dut.memory_load_we.value = 0
        dut.memory_load_weights.value = 0
        dut.memory_load_addr.value = 0
        dut.memory_load_data.value = 0
        dut.data_addr.value = 0
        dut.weight_addr.value = 0
        dut.v8_valid_in.value = 0
        dut.start.value = 0
        dut.rst.value = 1
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        await ReadOnly()

        if v8:
            assert dut.valid_out_pe_chain_v8.value == 0, "V8 valid_out was not reset"
            assert dut.y_pe_chain_v8.value.to_signed() == 0, "V8 output was not reset"

            # Verify the standalone byte-wide RAM before testing RAM + PE chain.
            await FallingEdge(dut.clk)
            dut.ram_we.value = 1
            dut.ram_write_addr.value = 2
            dut.ram_write_data.value = 0xA5
            await RisingEdge(dut.clk)
            await ReadOnly()
            await FallingEdge(dut.clk)
            dut.ram_we.value = 0
            dut.ram_read_addr.value = 2
            await Timer(1, unit="ps")
            assert int(dut.ram_read_data.value) == 0xA5, "Standalone RAM read/write failed"
        else:
            assert dut.done_v9.value == 0, "V9 done was not cleared by reset"
            assert dut.result_v9.value.to_signed() == 0, "V9 result was not cleared by reset"

        data_vectors = ([2, 3, 4, 5], [-4, -3, -2, -1])
        weight_vectors = ([3, 4, 5, 6], [5, 6, 7, 8])
        data_width = len(dut.a)

        # Both the V8 wrapper and V9 system receive these writes. The RAMs do
        # not reset, so loading while the datapaths are held in reset is safe.
        for load_weights, vectors in ((False, data_vectors), (True, weight_vectors)):
            for address, values in enumerate(vectors):
                await FallingEdge(dut.clk)
                dut.memory_load_we.value = 1
                dut.memory_load_weights.value = load_weights
                dut.memory_load_addr.value = address
                dut.memory_load_data.value = pack_vector(values, data_width)
                await RisingEdge(dut.clk)
                await ReadOnly()

        await FallingEdge(dut.clk)
        dut.memory_load_we.value = 0
        dut.rst.value = 0

        if v8:
            transactions = [(0, True), (1, True), (0, False)]
            pipeline_latency = 4
            driven = []
            for cycle in range(len(transactions) + pipeline_latency - 1):
                if cycle < len(transactions):
                    address, valid = transactions[cycle]
                else:
                    address, valid = 0, False

                dut.data_addr.value = address
                dut.weight_addr.value = address
                dut.v8_valid_in.value = valid
                driven.append((address, valid))

                await RisingEdge(dut.clk)
                await ReadOnly()

                completed_cycle = cycle - (pipeline_latency - 1)
                if completed_cycle < 0:
                    expected_valid = False
                else:
                    completed_address, expected_valid = driven[completed_cycle]

                actual_valid = bool(dut.valid_out_pe_chain_v8.value)
                assert actual_valid == expected_valid, (
                    f"V8 valid mismatch at cycle {cycle}: "
                    f"got {actual_valid}, expected {expected_valid}"
                )
                if expected_valid:
                    expected = dot_product(
                        data_vectors[completed_address],
                        weight_vectors[completed_address],
                        data_width,
                    )
                    if not is_passed and completed_cycle == 0:
                        expected += 1
                    actual = dut.y_pe_chain_v8.value.to_signed()
                    if actual != expected:
                        message = (
                            f"[FAIL] pechain_v8 value different from expected "
                            f"(Got {actual}, Expected {expected})"
                        )
                        test_logger.error(message)
                        assert actual == expected, message
                    print(f"[OK] pechain_v8 valid result equal to expected ({actual})")
                else:
                    assert dut.y_pe_chain_v8.value.to_signed() == 0, "V8 bubble data was not zero"

                await FallingEdge(dut.clk)
            return

        async def run_v9(address, expected, hold_start=False):
            dut.data_addr.value = address
            dut.weight_addr.value = address
            dut.start.value = 1
            await RisingEdge(dut.clk)
            await ReadOnly()
            await FallingEdge(dut.clk)
            if not hold_start:
                dut.start.value = 0

            for _ in range(8):
                await RisingEdge(dut.clk)
                await ReadOnly()
                if dut.done_v9.value == 1:
                    actual = dut.result_v9.value.to_signed()
                    if actual != expected:
                        message = (
                            f"[FAIL] V9 result different from expected "
                            f"(Got {actual}, Expected {expected})"
                        )
                        test_logger.error(message)
                        assert actual == expected, message
                    print(f"[OK] V9 FSM completed with expected result ({actual})")
                    await FallingEdge(dut.clk)
                    if hold_start:
                        await RisingEdge(dut.clk)
                        await ReadOnly()
                        assert dut.done_v9.value == 1, "V9 left DONE while start was still asserted"
                        await FallingEdge(dut.clk)
                        dut.start.value = 0
                    await RisingEdge(dut.clk)
                    await ReadOnly()
                    assert dut.done_v9.value == 0, "V9 did not return from DONE to IDLE"
                    await FallingEdge(dut.clk)
                    return
                await FallingEdge(dut.clk)
            assert False, "V9 timed out waiting for done"

        first_expected = dot_product(data_vectors[0], weight_vectors[0], data_width)
        if not is_passed:
            first_expected += 1
        await run_v9(0, first_expected, hold_start=True)
        await run_v9(1, dot_product(data_vectors[1], weight_vectors[1], data_width))

        dut.rst.value = 1
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.done_v9.value == 0, "V9 done was not cleared by reset"
        assert dut.result_v9.value.to_signed() == 0, "V9 result was not cleared by reset"
        return

    if v7:
        cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
        dut.a.value = 0
        dut.b.value = 0
        dut.acc_in.value = 0
        dut.valid_in.value = 0
        dut.rst.value = 1
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.valid_out_pe_chain_v7.value == 0, "V7 valid_out was not cleared by reset"
        assert dut.y_pe_chain_v7.value.to_signed() == 0, "V7 output was not cleared by reset"

        await FallingEdge(dut.clk)
        dut.rst.value = 0

        # The False entries are pipeline bubbles; the two final True entries
        # verify that a completed result can be emitted on every clock.
        transactions = [
            (2, 3, True),
            (99, -11, False),
            (-4, 5, True),
            (50, 3, True),
            (7, 9, False),
        ]
        pipeline_latency = 4
        driven = []
        data_width = len(dut.a)

        for cycle in range(len(transactions) + pipeline_latency - 1):
            if cycle < len(transactions):
                a, b, valid = transactions[cycle]
            else:
                a, b, valid = 0, 0, False

            dut.a.value = a
            dut.b.value = b
            dut.valid_in.value = valid
            driven.append((a, b, valid))

            await RisingEdge(dut.clk)
            await ReadOnly()

            completed_cycle = cycle - (pipeline_latency - 1)
            if completed_cycle < 0:
                expected_valid = False
            else:
                expected_a, expected_b, expected_valid = driven[completed_cycle]

            actual_valid = bool(dut.valid_out_pe_chain_v7.value)
            assert actual_valid == expected_valid, (
                f"V7 valid mismatch at cycle {cycle}: "
                f"got {actual_valid}, expected {expected_valid}"
            )

            if expected_valid:
                expected = sum(
                    signed_truncate(expected_a + index, data_width)
                    * signed_truncate(expected_b + index, data_width)
                    for index in range(4)
                )
                actual = dut.y_pe_chain_v7.value.to_signed()
                assert actual == expected, (
                    f"[FAIL] pechain_v7 value different from expected "
                    f"(Got {actual}, Expected {expected})"
                )
                print(f"[OK] pechain_v7 valid result equal to expected ({actual})")
            else:
                assert dut.y_pe_chain_v7.value.to_signed() == 0, (
                    f"V7 bubble data was not zero at cycle {cycle}"
                )

            await FallingEdge(dut.clk)

        dut.rst.value = 1
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.valid_out_pe_chain_v7.value == 0, "V7 valid_out was not cleared by reset"
        assert dut.y_pe_chain_v7.value.to_signed() == 0, "V7 output was not cleared by reset"
        return

    if v6:
        cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
        dut.a.value = 0
        dut.b.value = 0
        dut.acc_in.value = 0
        dut.valid_in.value = 0
        dut.rst.value = 1
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.y_pe_chain_v6.value.to_signed() == 0, "V6 output was not cleared by reset"

        await FallingEdge(dut.clk)
        dut.rst.value = 0

        transactions = [(2, 3), (-4, 5), (50, 3)]
        expected_results = []
        data_width = len(dut.a)
        for a, b in transactions:
            dut.a.value = a
            dut.b.value = b
            expected_results.append(sum(
                signed_truncate(a + index, data_width)
                * signed_truncate(b + index, data_width)
                for index in range(4)
            ))
            await RisingEdge(dut.clk)
            await ReadOnly()
            await FallingEdge(dut.clk)

        if not is_passed:
            expected_results[0] += 1

        dut.a.value = 0
        dut.b.value = 0
        for expected in expected_results:
            await RisingEdge(dut.clk)
            await ReadOnly()
            actual = dut.y_pe_chain_v6.value.to_signed()
            if actual != expected:
                message = (
                    f"[FAIL] pechain_v6 value different from expected "
                    f"(Got {actual}, Expected {expected})"
                )
                test_logger.error(message)
                assert actual == expected, message
            print(f"[OK] pechain_v6 value equal to expected ({actual})")
            await FallingEdge(dut.clk)

        dut.rst.value = 1
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.y_pe_chain_v6.value.to_signed() == 0, "V6 output was not cleared by reset"
        return

    positive = os.getenv("TEST_POSITIVE_VALUES", "1") == "1"
    zero = os.getenv("TEST_ZERO_VALUES", "0") == "1"
    if zero:
        a = 0
    elif v5:
        a = 50 if positive else -50
    else:
        a = 1 if positive else -1
    b = 3 if v5 else 2
    acc_in = 3
    dut.a.value = a
    dut.b.value = b
    dut.acc_in.value = acc_in
    
    data_width = len(dut.a)
    array_expected = [
        signed_truncate(a + index, data_width)
        * signed_truncate(b + index, data_width)
        for index in range(4)
    ]
    dot_product_expected = sum(array_expected)
    if not is_passed:
        array_expected[0] += 1
        dot_product_expected += 1

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
        "pechain_v5": (dut.y_pe_chain_v5, dot_product_expected),
    }
    if os.getenv("TEST_PECHAIN", "0") == "1":
        if v5:
            selected = {"pechain_v5": checks["pechain_v5"]}
        elif os.getenv("TEST_ARRAYS", "0") == "1":
            selected = {
                name: check for name, check in checks.items()
                if name.startswith("pearray_")
            }
        else:
            selected = {
                name: check for name, check in checks.items()
                if name.startswith("pechain_") and name != "pechain_v5"
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
            project_dir / "simple_ram.sv",
            project_dir / "pe_system.sv",
            project_dir / "testbench.sv",
        ],
        hdl_toplevel="pe_testbench",
        always=True,
        timescale=("1ns", "1ps"),
    )

    results_file = runner.test(
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
            "TEST_V5": v5_value,
            "TEST_V6": v6_value,
            "TEST_V7": v7_value,
            "TEST_V8": v8_value,
            "TEST_V9": v9_value,
        },
    )
    _, failed_tests = get_results(results_file)
    if failed_tests:
        raise SystemExit(1)
