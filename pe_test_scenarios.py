"""Independent cocotb scenarios for each PE implementation family."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer

from pe_test_config import TestConfig
from pe_test_helpers import (
    assert_signal_equals,
    chain_dot_product,
    dot_product,
    pack_vector,
    signed_truncate,
)


DATA_VECTORS = ([2, 3, 4, 5], [-4, -3, -2, -1])
WEIGHT_VECTORS = ([3, 4, 5, 6], [5, 6, 7, 8])
PIPELINE_LATENCY = 4


async def run_product_test(dut, config: TestConfig) -> None:
    """Dispatch to the scenario selected through the runner environment."""
    scenario = {
        "v6": run_v6_pipeline,
        "v7": run_v7_valid_pipeline,
        "v8": run_memory_system,
        "v9": run_memory_system,
        "v10": run_memory_system,
        "v11": run_memory_system,
    }.get(config.pipeline_version, run_combinational)
    await scenario(dut, config)


async def _start_and_reset_clocked_dut(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
    dut.a.value = 0
    dut.b.value = 0
    dut.acc_in.value = 0
    dut.valid_in.value = 0
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await ReadOnly()


async def run_v6_pipeline(dut, config: TestConfig) -> None:
    await _start_and_reset_clocked_dut(dut)
    assert dut.y_pe_chain_v6.value.to_signed() == 0, "V6 output was not cleared by reset"

    await FallingEdge(dut.clk)
    dut.rst.value = 0
    transactions = [(2, 3), (-4, 5), (50, 3)]
    data_width = len(dut.a)
    expected_results = []

    for a, b in transactions:
        dut.a.value = a
        dut.b.value = b
        expected_results.append(chain_dot_product(a, b, data_width))
        await RisingEdge(dut.clk)
        await ReadOnly()
        await FallingEdge(dut.clk)

    if not config.passed:
        expected_results[0] += 1

    dut.a.value = 0
    dut.b.value = 0
    for expected in expected_results:
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert_signal_equals("pechain_v6", dut.y_pe_chain_v6, expected)
        await FallingEdge(dut.clk)

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.y_pe_chain_v6.value.to_signed() == 0, "V6 output was not cleared by reset"


async def run_v7_valid_pipeline(dut, config: TestConfig) -> None:
    await _start_and_reset_clocked_dut(dut)
    assert dut.valid_out_pe_chain_v7.value == 0, "V7 valid_out was not cleared by reset"
    assert dut.y_pe_chain_v7.value.to_signed() == 0, "V7 output was not cleared by reset"

    await FallingEdge(dut.clk)
    dut.rst.value = 0
    transactions = [
        (2, 3, True),
        (99, -11, False),
        (-4, 5, True),
        (50, 3, True),
        (7, 9, False),
    ]
    driven = []
    data_width = len(dut.a)

    for cycle in range(len(transactions) + PIPELINE_LATENCY - 1):
        transaction = transactions[cycle] if cycle < len(transactions) else (0, 0, False)
        a, b, valid = transaction
        dut.a.value = a
        dut.b.value = b
        dut.valid_in.value = valid
        driven.append(transaction)

        await RisingEdge(dut.clk)
        await ReadOnly()

        completed_cycle = cycle - (PIPELINE_LATENCY - 1)
        completed = driven[completed_cycle] if completed_cycle >= 0 else (0, 0, False)
        expected_a, expected_b, expected_valid = completed
        actual_valid = bool(dut.valid_out_pe_chain_v7.value)
        assert actual_valid == expected_valid, (
            f"V7 valid mismatch at cycle {cycle}: got {actual_valid}, expected {expected_valid}"
        )

        if expected_valid:
            assert_signal_equals(
                "pechain_v7",
                dut.y_pe_chain_v7,
                chain_dot_product(expected_a, expected_b, data_width),
            )
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


async def run_memory_system(dut, config: TestConfig) -> None:
    await _initialize_memory_system(dut)
    version = config.pipeline_version
    _assert_memory_reset(dut, version)
    if version == "v8":
        await _test_standalone_ram(dut)

    data_width = len(dut.a)
    await _load_vectors(dut, data_width)
    await FallingEdge(dut.clk)
    dut.memory_load_we.value = 0
    dut.rst.value = 0

    if version == "v8":
        await _run_v8_transactions(dut, config, data_width)
    elif version == "v9":
        await _run_v9_transactions(dut, config, data_width)
    elif version == "v10":
        await _run_v10_transactions(dut, data_width)
    else:
        await _verify_v11_memories(dut, data_width)
        await _run_v11_transactions(dut, config, data_width)


async def _initialize_memory_system(dut) -> None:
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
    dut.v11_valid_in.value = 0
    dut.start.value = 0
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await ReadOnly()


def _assert_memory_reset(dut, version: str) -> None:
    if version == "v8":
        assert dut.valid_out_pe_chain_v8.value == 0, "V8 valid_out was not reset"
        assert dut.y_pe_chain_v8.value.to_signed() == 0, "V8 output was not reset"
    elif version == "v9":
        assert dut.done_v9.value == 0, "V9 done was not cleared by reset"
        assert dut.result_v9.value.to_signed() == 0, "V9 result was not cleared by reset"
    elif version == "v10":
        assert dut.busy_v10.value == 0, "V10 busy was not cleared by reset"
        assert dut.done_v10.value == 0, "V10 done was not cleared by reset"
        assert dut.result_v10.value.to_signed() == 0, "V10 result was not cleared by reset"
    else:
        assert dut.valid_out_pe_chain_v11.value == 0, "V11 valid_out was not reset"
        assert dut.y_pe_chain_v11.value.to_signed() == 0, "V11 output was not reset"


async def _test_standalone_ram(dut) -> None:
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


async def _load_vectors(dut, data_width: int) -> None:
    for load_weights, vectors in ((False, DATA_VECTORS), (True, WEIGHT_VECTORS)):
        for address, values in enumerate(vectors):
            await FallingEdge(dut.clk)
            dut.memory_load_we.value = 1
            dut.memory_load_weights.value = load_weights
            dut.memory_load_addr.value = address
            dut.memory_load_data.value = pack_vector(values, data_width)
            await RisingEdge(dut.clk)
            await ReadOnly()


async def _run_v8_transactions(dut, config: TestConfig, data_width: int) -> None:
    transactions = [(0, True), (1, True), (0, False)]
    driven = []
    for cycle in range(len(transactions) + PIPELINE_LATENCY - 1):
        transaction = transactions[cycle] if cycle < len(transactions) else (0, False)
        address, valid = transaction
        dut.data_addr.value = address
        dut.weight_addr.value = address
        dut.v8_valid_in.value = valid
        driven.append(transaction)

        await RisingEdge(dut.clk)
        await ReadOnly()
        completed_cycle = cycle - (PIPELINE_LATENCY - 1)
        completed_address, expected_valid = (
            driven[completed_cycle] if completed_cycle >= 0 else (0, False)
        )
        actual_valid = bool(dut.valid_out_pe_chain_v8.value)
        assert actual_valid == expected_valid, (
            f"V8 valid mismatch at cycle {cycle}: got {actual_valid}, expected {expected_valid}"
        )
        if expected_valid:
            expected = dot_product(
                DATA_VECTORS[completed_address], WEIGHT_VECTORS[completed_address], data_width
            )
            if not config.passed and completed_cycle == 0:
                expected += 1
            assert_signal_equals(
                (
                    "pechain_v8 "
                    f"data_addr={completed_address} weight_addr={completed_address}"
                ),
                dut.y_pe_chain_v8,
                expected,
            )
        else:
            assert dut.y_pe_chain_v8.value.to_signed() == 0, "V8 bubble data was not zero"
        await FallingEdge(dut.clk)


async def _verify_v11_memories(dut, data_width: int) -> None:
    for address, (data, weights) in enumerate(zip(DATA_VECTORS, WEIGHT_VECTORS)):
        dut.data_addr.value = address
        dut.weight_addr.value = address
        await Timer(1, unit="ps")
        assert int(dut.a_read_data_v11.value) == pack_vector(data, data_width), (
            f"V11 data memory mismatch at address {address}"
        )
        assert int(dut.b_read_data_v11.value) == pack_vector(weights, data_width), (
            f"V11 weight memory mismatch at address {address}"
        )


async def _run_v11_transactions(dut, config: TestConfig, data_width: int) -> None:
    transactions = [(0, True), (1, True)]
    for cycle in range(len(transactions) + PIPELINE_LATENCY - 1):
        address, valid = transactions[cycle] if cycle < len(transactions) else (0, False)
        dut.data_addr.value = address
        dut.weight_addr.value = address
        dut.v11_valid_in.value = valid

        await RisingEdge(dut.clk)
        await ReadOnly()
        completed_cycle = cycle - (PIPELINE_LATENCY - 1)
        expected_valid = completed_cycle >= 0
        assert bool(dut.valid_out_pe_chain_v11.value) == expected_valid, (
            f"V11 valid mismatch at cycle {cycle}"
        )
        if expected_valid:
            completed_address = transactions[completed_cycle][0]
            expected = dot_product(
                DATA_VECTORS[completed_address],
                WEIGHT_VECTORS[completed_address],
                data_width,
            )
            if not config.passed and completed_cycle == 0:
                expected += 1
            assert_signal_equals("pechain_v11", dut.y_pe_chain_v11, expected)
        else:
            assert dut.y_pe_chain_v11.value.to_signed() == 0, (
                "V11 bubble data was not zero"
            )
        await FallingEdge(dut.clk)


async def _run_v9_transactions(dut, config: TestConfig, data_width: int) -> None:
    first_expected = dot_product(DATA_VECTORS[0], WEIGHT_VECTORS[0], data_width)
    if not config.passed:
        first_expected += 1
    await _run_v9_command(dut, 0, first_expected, hold_start=True)
    await _run_v9_command(
        dut, 1, dot_product(DATA_VECTORS[1], WEIGHT_VECTORS[1], data_width)
    )

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    _assert_memory_reset(dut, "v9")


async def _run_v9_command(dut, address: int, expected: int, hold_start: bool = False) -> None:
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
            assert_signal_equals("V9 result", dut.result_v9, expected)
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


async def _run_v10_transactions(dut, data_width: int) -> None:
    await _run_v10_command(dut, 0, data_width, try_retrigger=False)
    await _run_v10_command(dut, 1, data_width, try_retrigger=True)


async def _run_v10_command(dut, address: int, data_width: int, try_retrigger: bool) -> None:
    expected = dot_product(DATA_VECTORS[address], WEIGHT_VECTORS[address], data_width)
    await FallingEdge(dut.clk)
    dut.data_addr.value = address
    dut.weight_addr.value = address
    dut.start.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.busy_v10.value == 1, "V10 did not assert busy for an accepted command"
    assert dut.done_v10.value == 0, "V10 asserted done before the result was ready"

    await FallingEdge(dut.clk)
    dut.start.value = 0
    if try_retrigger:
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.busy_v10.value == 1, "V10 dropped busy before completion"
        await FallingEdge(dut.clk)
        rejected_address = 1 - address
        dut.data_addr.value = rejected_address
        dut.weight_addr.value = rejected_address
        dut.start.value = 1

    for _ in range(8):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.done_v10.value == 1:
            break
        assert dut.busy_v10.value == 1, "V10 busy was low while the command was running"
        await FallingEdge(dut.clk)
    else:
        assert False, "V10 timed out waiting for done"

    assert dut.busy_v10.value == 0, "V10 kept busy high after completion"
    assert dut.result_v10.value.to_signed() == expected, (
        "V10 result did not match the accepted command"
    )

    await FallingEdge(dut.clk)
    if try_retrigger:
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.done_v10.value == 1, "V10 did not hold done for a held retrigger attempt"
        assert dut.busy_v10.value == 0, "V10 retriggered while waiting for start to be released"
        await FallingEdge(dut.clk)

    dut.start.value = 0
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.done_v10.value == 0, "V10 did not clear done after start was released"
    assert dut.busy_v10.value == 0, "V10 was busy without an accepted command"

    if try_retrigger:
        for _ in range(5):
            await RisingEdge(dut.clk)
            await ReadOnly()
            assert dut.busy_v10.value == 0, "V10 executed the rejected retrigger"
            assert dut.done_v10.value == 0, "V10 completed the rejected retrigger"
            assert dut.result_v10.value.to_signed() == expected, (
                "V10 changed result after rejecting a retrigger"
            )
            await FallingEdge(dut.clk)

    scenario = "with retrigger attempt" if try_retrigger else "without retrigger"
    print(f"[OK] V10 command completed {scenario} ({expected})")


async def run_combinational(dut, config: TestConfig) -> None:
    v5 = config.pipeline_version == "v5"
    if config.zero:
        a = 0
    elif v5:
        a = 50 if config.positive else -50
    else:
        a = 1 if config.positive else -1
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
    offset = 0 if config.passed else 1
    array_expected[0] += offset
    dot_product_expected += offset

    checks = {
        "v0": (dut.y_v0, a * b + offset),
        "v1": (dut.y_v1, a * b + acc_in + offset),
        "pe": (dut.y_pe, a * b + acc_in + offset),
        "pechain_manual_2": (dut.y_pe_chain_manual_2, acc_in + 2 * a * b + offset),
        "pechain_2": (dut.y_pe_chain_2, acc_in + 2 * a * b + offset),
        "pechain_4": (dut.y_pe_chain_4, acc_in + 4 * a * b + offset),
        **{
            f"pearray_{index}": (getattr(dut, f"y_pe_array_{index}"), expected)
            for index, expected in enumerate(array_expected)
        },
        "pechain_v5": (dut.y_pe_chain_v5, dot_product_expected),
    }
    await Timer(1, unit="ns")
    for name, (signal, expected) in _select_checks(checks, config).items():
        assert_signal_equals(name, signal, expected)


def _select_checks(checks: dict, config: TestConfig) -> dict:
    if config.pechain:
        if config.pipeline_version == "v5":
            return {"pechain_v5": checks["pechain_v5"]}
        prefix = "pearray_" if config.arrays else "pechain_"
        return {
            name: check
            for name, check in checks.items()
            if name.startswith(prefix) and name != "pechain_v5"
        }

    default_checks = {
        name: check
        for name, check in checks.items()
        if not name.startswith(("pechain_", "pearray_"))
    }
    if config.version == "all":
        return default_checks
    return {config.version: checks[config.version]}
