"""Independent cocotb scenarios for each PE implementation family."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer

from pe_test_config import TestConfig
from pe_test_helpers import (
    assert_signal_equals,
    dot_product,
    pack_vector,
    signed_truncate,
)


def _vector(start: int, length: int) -> tuple[int, ...]:
    return tuple(start + index for index in range(length))


def _test_vectors(num_pe: int):
    return (
        (_vector(2, num_pe), _vector(-4, num_pe)),
        (_vector(3, num_pe), _vector(5, num_pe)),
    )


def _drive_chain_vectors(dut, data, weights, data_width: int) -> None:
    dut.chain_data_vector.value = pack_vector(data, data_width)
    dut.chain_weight_vector.value = pack_vector(weights, data_width)


async def run_product_test(dut, config: TestConfig) -> None:
    """Dispatch to the scenario selected through the runner environment."""
    scenario = {
        "v6": run_v6_pipeline,
        "v7": run_v7_valid_pipeline,
        "v8": run_memory_system,
        "v9": run_memory_system,
        "v10": run_memory_system,
        "v11": run_memory_system,
        "v12": run_v12_system,
        "vspecial": run_vspecial,
    }.get(config.version, run_combinational)
    await scenario(dut, config)


async def _start_and_reset_clocked_dut(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
    dut.a.value = 0
    dut.b.value = 0
    dut.acc_in.value = 0
    dut.chain_data_vector.value = 0
    dut.chain_weight_vector.value = 0
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
    transactions = [
        (_vector(2, config.num_pe), _vector(3, config.num_pe)),
        (_vector(-4, config.num_pe), _vector(5, config.num_pe)),
        (_vector(9, config.num_pe), _vector(3, config.num_pe)),
    ]
    data_width = len(dut.a)
    expected_results = [
        dot_product(data, weights, data_width)
        for data, weights in transactions
    ]

    if not config.passed:
        expected_results[0] += 1

    for cycle in range(len(transactions) + config.num_pe - 1):
        data, weights = (
            transactions[cycle]
            if cycle < len(transactions)
            else ((0,) * config.num_pe, (0,) * config.num_pe)
        )
        _drive_chain_vectors(dut, data, weights, data_width)
        await RisingEdge(dut.clk)
        await ReadOnly()
        completed_cycle = cycle - (config.num_pe - 1)
        if 0 <= completed_cycle < len(expected_results):
            assert_signal_equals(
                "pechain_v6", dut.y_pe_chain_v6, expected_results[completed_cycle]
            )
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
        (_vector(2, config.num_pe), _vector(3, config.num_pe), True),
        (_vector(9, config.num_pe), _vector(-9, config.num_pe), False),
        (_vector(-4, config.num_pe), _vector(5, config.num_pe), True),
        (_vector(9, config.num_pe), _vector(3, config.num_pe), True),
        (_vector(7, config.num_pe), _vector(9, config.num_pe), False),
    ]
    driven = []
    data_width = len(dut.a)

    for cycle in range(len(transactions) + config.num_pe - 1):
        transaction = (
            transactions[cycle]
            if cycle < len(transactions)
            else ((0,) * config.num_pe, (0,) * config.num_pe, False)
        )
        data, weights, valid = transaction
        _drive_chain_vectors(dut, data, weights, data_width)
        dut.valid_in.value = valid
        driven.append((data, weights, valid))

        await RisingEdge(dut.clk)
        await ReadOnly()

        completed_cycle = cycle - (config.num_pe - 1)
        completed = (
            driven[completed_cycle]
            if completed_cycle >= 0
            else ((0,) * config.num_pe, (0,) * config.num_pe, False)
        )
        expected_data, expected_weights, expected_valid = completed
        actual_valid = bool(dut.valid_out_pe_chain_v7.value)
        assert actual_valid == expected_valid, (
            f"V7 valid mismatch at cycle {cycle}: got {actual_valid}, expected {expected_valid}"
        )

        if expected_valid:
            if config.calculus:
                print(
                    f"[CALCULUS] V7 data={expected_data}, "
                    f"weights={expected_weights} "
                    f"({config.num_pe} PEs)"
                )
                _show_vector_calculation(
                    expected_data, expected_weights, label="V7"
                )
            assert_signal_equals(
                "pechain_v7",
                dut.y_pe_chain_v7,
                dot_product(expected_data, expected_weights, data_width),
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
    version = config.version
    _assert_memory_reset(dut, version)
    if version == "v8":
        await _test_standalone_ram(dut)

    data_width = len(dut.a)
    data_vectors, weight_vectors = _test_vectors(config.num_pe)
    await _load_vectors(dut, data_width, data_vectors, weight_vectors)
    await FallingEdge(dut.clk)
    dut.memory_load_we.value = 0
    dut.rst.value = 0

    if version == "v8":
        await _run_v8_transactions(
            dut, config, data_width, data_vectors, weight_vectors
        )
    elif version == "v9":
        await _run_v9_transactions(
            dut, config, data_width, data_vectors, weight_vectors
        )
    elif version == "v10":
        await _run_v10_transactions(
            dut, config, data_width, data_vectors, weight_vectors
        )
    else:
        await _verify_v11_memories(dut, data_width, data_vectors, weight_vectors)
        await _run_v11_transactions(
            dut, config, data_width, data_vectors, weight_vectors
        )


async def _initialize_memory_system(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
    dut.a.value = 0
    dut.b.value = 0
    dut.acc_in.value = 0
    dut.chain_data_vector.value = 0
    dut.chain_weight_vector.value = 0
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
    dut.special_valid_in.value = 0
    dut.special_data_vectors.value = 0
    dut.special_weight_vectors.value = 0
    dut.special_biases.value = 0
    dut.special_result_addr.value = 0
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
    elif version == "v11":
        assert dut.valid_out_pe_chain_v11.value == 0, "V11 valid_out was not reset"
        assert dut.y_pe_chain_v11.value.to_signed() == 0, "V11 output was not reset"
    else:
        assert dut.busy_v12.value == 0, "V12 busy was not cleared by reset"
        assert dut.done_v12.value == 0, "V12 done was not cleared by reset"
        assert dut.error_v12.value == 0, "V12 error was not cleared by reset"
        assert dut.result_v12.value.to_signed() == 0, "V12 result was not cleared by reset"


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


async def _load_vectors(dut, data_width: int, data_vectors, weight_vectors) -> None:
    for load_weights, vectors in ((False, data_vectors), (True, weight_vectors)):
        for address, values in enumerate(vectors):
            await FallingEdge(dut.clk)
            dut.memory_load_we.value = 1
            dut.memory_load_weights.value = load_weights
            dut.memory_load_addr.value = address
            dut.memory_load_data.value = pack_vector(values, data_width)
            await RisingEdge(dut.clk)
            await ReadOnly()


async def _run_v8_transactions(
    dut, config: TestConfig, data_width: int, data_vectors, weight_vectors
) -> None:
    transactions = [(0, True), (1, True), (0, False)]
    driven = []
    for cycle in range(len(transactions) + config.num_pe - 1):
        transaction = transactions[cycle] if cycle < len(transactions) else (0, False)
        address, valid = transaction
        dut.data_addr.value = address
        dut.weight_addr.value = address
        dut.v8_valid_in.value = valid
        driven.append(transaction)

        await RisingEdge(dut.clk)
        await ReadOnly()
        completed_cycle = cycle - (config.num_pe - 1)
        completed_address, expected_valid = (
            driven[completed_cycle] if completed_cycle >= 0 else (0, False)
        )
        actual_valid = bool(dut.valid_out_pe_chain_v8.value)
        assert actual_valid == expected_valid, (
            f"V8 valid mismatch at cycle {cycle}: got {actual_valid}, expected {expected_valid}"
        )
        if expected_valid:
            expected = dot_product(
                data_vectors[completed_address], weight_vectors[completed_address], data_width
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


async def _verify_v11_memories(
    dut, data_width: int, data_vectors, weight_vectors
) -> None:
    for address, (data, weights) in enumerate(zip(data_vectors, weight_vectors)):
        dut.data_addr.value = address
        dut.weight_addr.value = address
        await Timer(1, unit="ps")
        assert int(dut.a_read_data_v11.value) == pack_vector(data, data_width), (
            f"V11 data memory mismatch at address {address}"
        )
        assert int(dut.b_read_data_v11.value) == pack_vector(weights, data_width), (
            f"V11 weight memory mismatch at address {address}"
        )


async def _run_v11_transactions(
    dut, config: TestConfig, data_width: int, data_vectors, weight_vectors
) -> None:
    transactions = [(0, True), (1, True)]
    for cycle in range(len(transactions) + config.num_pe - 1):
        address, valid = transactions[cycle] if cycle < len(transactions) else (0, False)
        dut.data_addr.value = address
        dut.weight_addr.value = address
        dut.v11_valid_in.value = valid

        await RisingEdge(dut.clk)
        await ReadOnly()
        completed_cycle = cycle - (config.num_pe - 1)
        expected_valid = completed_cycle >= 0
        assert bool(dut.valid_out_pe_chain_v11.value) == expected_valid, (
            f"V11 valid mismatch at cycle {cycle}"
        )
        if expected_valid:
            completed_address = transactions[completed_cycle][0]
            expected = dot_product(
                data_vectors[completed_address],
                weight_vectors[completed_address],
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


async def _run_v9_transactions(
    dut, config: TestConfig, data_width: int, data_vectors, weight_vectors
) -> None:
    first_expected = dot_product(data_vectors[0], weight_vectors[0], data_width)
    if not config.passed:
        first_expected += 1
    await _run_v9_command(
        dut, 0, first_expected, config.num_pe, hold_start=True
    )
    await _run_v9_command(
        dut,
        1,
        dot_product(data_vectors[1], weight_vectors[1], data_width),
        config.num_pe,
    )

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    _assert_memory_reset(dut, "v9")


async def _run_v9_command(
    dut, address: int, expected: int, num_pe: int, hold_start: bool = False
) -> None:
    dut.data_addr.value = address
    dut.weight_addr.value = address
    dut.start.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    _show_v9_status(dut, "start")
    await FallingEdge(dut.clk)
    if not hold_start:
        dut.start.value = 0

    for _ in range(num_pe + 4):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.done_v9.value == 1:
            assert_signal_equals("V9 result", dut.result_v9, expected)
            _show_v9_status(dut, "done")
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
            print(f"[OK] V9 FSM completed with expected result ({expected})")
            await FallingEdge(dut.clk)
            return
        await FallingEdge(dut.clk)
    assert False, "V9 timed out waiting for done"


def _show_v9_status(dut, phase: str) -> None:
    print(
        f"[STATUS] V9 phase={phase} "
        f"start={int(dut.start.value)} "
        f"done={int(dut.done_v9.value)} "
        f"result={dut.result_v9.value.to_signed()}"
    )


async def _run_v10_transactions(
    dut, config: TestConfig, data_width: int, data_vectors, weight_vectors
) -> None:
    await _run_v10_command(
        dut,
        0,
        data_width,
        config.num_pe,
        data_vectors,
        weight_vectors,
        try_retrigger=False,
    )
    await _run_v10_command(
        dut,
        1,
        data_width,
        config.num_pe,
        data_vectors,
        weight_vectors,
        try_retrigger=True,
    )


async def _run_v10_command(
    dut,
    address: int,
    data_width: int,
    num_pe: int,
    data_vectors,
    weight_vectors,
    try_retrigger: bool,
) -> None:
    expected = dot_product(data_vectors[address], weight_vectors[address], data_width)
    await FallingEdge(dut.clk)
    dut.data_addr.value = address
    dut.weight_addr.value = address
    dut.start.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.busy_v10.value == 1, "V10 did not assert busy for an accepted command"
    assert dut.done_v10.value == 0, "V10 asserted done before the result was ready"
    _show_v10_status(dut, "start")

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

    for _ in range(num_pe + 4):
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
    _show_v10_status(dut, "done")

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


def _show_v10_status(dut, phase: str) -> None:
    print(
        f"[STATUS] V10 phase={phase} "
        f"start={int(dut.start.value)} "
        f"done={int(dut.done_v10.value)} "
        f"busy={int(dut.busy_v10.value)} "
        f"result={dut.result_v10.value.to_signed()}"
    )


async def run_v12_system(dut, config: TestConfig) -> None:
    await _initialize_memory_system(dut)
    _assert_memory_reset(dut, "v12")

    await FallingEdge(dut.clk)
    dut.rst.value = 0

    # Neither a B write nor start may skip the required A -> B load order.
    dut.memory_load_we.value = 1
    dut.memory_load_weights.value = 1
    dut.memory_load_addr.value = 0
    dut.memory_load_data.value = pack_vector([9] * config.num_pe, len(dut.a))
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.busy_v12.value == 0, "V12 accepted B before entering LOAD_A"

    await FallingEdge(dut.clk)
    dut.memory_load_we.value = 0
    dut.start.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.busy_v12.value == 0, "V12 accepted start before loading operands"
    assert dut.done_v12.value == 0, "V12 completed without loaded operands"
    await FallingEdge(dut.clk)
    dut.start.value = 0

    data_width = len(dut.a)
    data_vectors, weight_vectors = _test_vectors(config.num_pe)
    for address in range(len(data_vectors)):
        await _run_v12_transaction(
            dut, address, data_width, config, data_vectors, weight_vectors
        )

    await FallingEdge(dut.clk)
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    _assert_memory_reset(dut, "v12")


async def _run_v12_transaction(
    dut,
    address: int,
    data_width: int,
    config: TestConfig,
    data_vectors,
    weight_vectors,
) -> None:
    # Load all A vectors first, then all B vectors, as required by the FSM.
    for write_address, values in enumerate(data_vectors):
        await FallingEdge(dut.clk)
        dut.memory_load_we.value = 1
        dut.memory_load_weights.value = 0
        dut.memory_load_addr.value = write_address
        dut.memory_load_data.value = pack_vector(values, data_width)
        await RisingEdge(dut.clk)
        await ReadOnly()

    for write_address, values in enumerate(weight_vectors):
        await FallingEdge(dut.clk)
        dut.memory_load_we.value = 1
        dut.memory_load_weights.value = 1
        dut.memory_load_addr.value = write_address
        dut.memory_load_data.value = pack_vector(values, data_width)
        await RisingEdge(dut.clk)
        await ReadOnly()

    _show_v12_status(dut, "load")

    # Once LOAD_B has started, a late A write must not alter operand memory.
    await FallingEdge(dut.clk)
    dut.memory_load_we.value = 1
    dut.memory_load_weights.value = 0
    dut.memory_load_addr.value = address
    dut.memory_load_data.value = pack_vector([9] * config.num_pe, data_width)
    await RisingEdge(dut.clk)
    await ReadOnly()

    await FallingEdge(dut.clk)
    dut.memory_load_we.value = 0
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.busy_v12.value == 0, "V12 became busy before start"

    await FallingEdge(dut.clk)
    dut.data_addr.value = address
    dut.weight_addr.value = address
    dut.start.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.busy_v12.value == 1, "V12 did not enter START_CALC"
    assert dut.done_v12.value == 0, "V12 asserted done before starting the pipeline"
    _show_v12_status(dut, "start")

    await FallingEdge(dut.clk)
    dut.start.value = 0
    await RisingEdge(dut.clk)
    await ReadOnly()
    expected_error = int(config.overlap and address > 0)
    assert int(dut.error_v12.value) == expected_error, (
        "V12 overlap error did not retain its expected state"
    )

    if config.overlap and address == 0:
        await FallingEdge(dut.clk)
        dut.data_addr.value = 1 - address
        dut.weight_addr.value = 1 - address
        dut.start.value = 1
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.busy_v12.value == 1, "V12 was not busy during the overlap attempt"
        assert dut.error_v12.value == 1, "V12 did not flag the overlap attempt"
        _show_v12_status(dut, "overlap")
        await FallingEdge(dut.clk)
        dut.start.value = 0

    for _ in range(config.num_pe + 3):
        await FallingEdge(dut.clk)
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.done_v12.value == 1:
            break
        assert dut.busy_v12.value == 1, "V12 left WAIT_PIPELINE before valid_out"
    else:
        assert False, "V12 timed out waiting for the pipeline"

    expected = dot_product(data_vectors[address], weight_vectors[address], data_width)
    if not config.passed and address == 0:
        expected += 1
    assert_signal_equals("V12 result", dut.result_v12, expected)
    assert dut.busy_v12.value == 0, "V12 remained busy after capturing the result"
    _show_v12_status(dut, "done")

    await FallingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.done_v12.value == 0, "V12 did not return to IDLE after start was released"
    print(f"[OK] V12 load/execute sequence completed ({expected})")


def _show_v12_status(dut, phase: str) -> None:
    print(
        f"[STATUS] V12 phase={phase} "
        f"load={int(dut.memory_load_we.value)} "
        f"start={int(dut.start.value)} "
        f"done={int(dut.done_v12.value)} "
        f"busy={int(dut.busy_v12.value)} "
        f"error={int(dut.error_v12.value)} "
        f"result={dut.result_v12.value.to_signed()}"
    )


def _pack_unit_vectors(vectors, width: int) -> int:
    vector_width = len(vectors[0]) * width
    return sum(
        pack_vector(vector, width) << (unit_index * vector_width)
        for unit_index, vector in enumerate(vectors)
    )


async def run_vspecial(dut, config: TestConfig) -> None:
    await _initialize_memory_system(dut)
    assert dut.busy_vspecial.value == 0, "VSpecial busy was not cleared by reset"
    assert dut.done_vspecial.value == 0, "VSpecial done was not cleared by reset"

    data_width = len(dut.a)
    acc_width = len(dut.special_biases) // config.num_dots
    base_data_vectors = tuple(_vector(start, config.num_pe) for start in (2, -4, 9))
    base_weight_vectors = tuple(_vector(start, config.num_pe) for start in (3, 5, -9))
    base_biases = (7, -9, 9)
    data_vectors = tuple(
        base_data_vectors[unit_index % len(base_data_vectors)]
        for unit_index in range(config.num_dots)
    )
    weight_vectors = tuple(
        base_weight_vectors[unit_index % len(base_weight_vectors)]
        for unit_index in range(config.num_dots)
    )
    biases = tuple(
        base_biases[unit_index % len(base_biases)]
        for unit_index in range(config.num_dots)
    )
    expected_results = [
        dot_product(data, weights, data_width) + bias
        for data, weights, bias in zip(data_vectors, weight_vectors, biases)
    ]
    if config.calculus:
        for unit_index, (data, weights, bias) in enumerate(
            zip(data_vectors, weight_vectors, biases)
        ):
            _show_vspecial_calculation(
                unit_index, data, weights, bias, data_width
            )
    if not config.passed:
        expected_results[0] += 1

    await FallingEdge(dut.clk)
    dut.special_data_vectors.value = _pack_unit_vectors(data_vectors, data_width)
    dut.special_weight_vectors.value = _pack_unit_vectors(weight_vectors, data_width)
    bias_mask = (1 << acc_width) - 1
    dut.special_biases.value = sum(
        (bias & bias_mask) << (index * acc_width)
        for index, bias in enumerate(biases)
    )

    dut.rst.value = 0
    dut.special_valid_in.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.busy_vspecial.value == 1, "VSpecial did not accept the request"
    assert dut.done_vspecial.value == 0, "VSpecial completed too early"

    await FallingEdge(dut.clk)
    dut.special_valid_in.value = 0
    # Inputs are captured with the accepted request and may change while busy.
    dut.special_data_vectors.value = 0
    dut.special_weight_vectors.value = 0
    dut.special_biases.value = 0
    for _ in range(config.num_dots * (config.num_pe + 1) + 4):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.done_vspecial.value == 1:
            break
        assert dut.busy_vspecial.value == 1, "VSpecial dropped busy before completion"
        await FallingEdge(dut.clk)
    else:
        assert False, "VSpecial timed out waiting for completion"

    assert dut.busy_vspecial.value == 0, "VSpecial remained busy after completion"
    await FallingEdge(dut.clk)
    for address, expected in enumerate(expected_results):
        dut.special_result_addr.value = address
        await Timer(1, unit="ps")
        assert_signal_equals(
            f"VSpecial result RAM address {address}", dut.result_vspecial, expected
        )

    await FallingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.done_vspecial.value == 0, "VSpecial done was not a one-cycle pulse"
    print(f"[OK] VSpecial stored biased dot products {expected_results}")


async def run_combinational(dut, config: TestConfig) -> None:
    v5 = config.version == "v5"
    if config.zero:
        a = 0
    elif v5:
        a = 6 if config.positive else -6
    else:
        a = 1 if config.positive else -1
    b = 3 if v5 else 2
    acc_in = 3
    dut.a.value = a
    dut.b.value = b
    dut.acc_in.value = acc_in

    data_width = len(dut.a)
    chain_data = _vector(a, config.num_pe)
    chain_weights = _vector(b, config.num_pe)
    _drive_chain_vectors(dut, chain_data, chain_weights, data_width)
    array_expected = [
        value * weight for value, weight in zip(chain_data, chain_weights)
    ]
    dot_product_expected = dot_product(chain_data, chain_weights, data_width)
    offset = 0 if config.passed else 1
    array_expected[0] += offset
    dot_product_expected += offset

    shows_array_results = config.version == "v4" or (
        config.version == "all" and config.pechain and config.arrays
    )
    if config.calculus and (shows_array_results or config.version == "v5"):
        if v5:
            _show_vector_calculation(chain_data, chain_weights, label="V5")
        else:
            _show_calculation_passes(a, b, data_width, False, 4)

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


def _show_calculation_passes(
    a: int, b: int, data_width: int, accumulate: bool, num_pe: int
) -> None:
    running_total = 0
    for index in range(num_pe):
        value = signed_truncate(a + index, data_width)
        weight = signed_truncate(b + index, data_width)
        product = value * weight
        if accumulate:
            previous_total = running_total
            running_total += product
            print(
                f"[CALCULUS] pass {index}: {previous_total} + "
                f"a[{index}] * b[{index}] = {previous_total} + "
                f"{value} * {weight} = {running_total}"
            )
        else:
            print(
                f"[CALCULUS] pass {index}: a[{index}] * b[{index}] = "
                f"{value} * {weight} = {product}"
            )


def _show_vector_calculation(data, weights, label: str) -> None:
    running_total = 0
    for index, (value, weight) in enumerate(zip(data, weights)):
        previous_total = running_total
        running_total += value * weight
        print(
            f"[CALCULUS] {label} pass {index}: {previous_total} + "
            f"data[{index}] * weight[{index}] = {previous_total} + "
            f"{value} * {weight} = {running_total}"
        )


def _show_vspecial_calculation(
    unit_index: int,
    data: tuple[int, ...],
    weights: tuple[int, ...],
    bias: int,
    data_width: int,
) -> None:
    running_total = bias
    print(f"[CALCULUS] VSpecial unit {unit_index}: bias = {bias}")
    for pass_index, (raw_value, raw_weight) in enumerate(zip(data, weights)):
        value = signed_truncate(raw_value, data_width)
        weight = signed_truncate(raw_weight, data_width)
        previous_total = running_total
        running_total += value * weight
        print(
            f"[CALCULUS] unit {unit_index} pass {pass_index}: "
            f"{previous_total} + a[{pass_index}] * b[{pass_index}] = "
            f"{previous_total} + {value} * {weight} = {running_total}"
        )


def _select_checks(checks: dict, config: TestConfig) -> dict:
    version_checks = {
        "v0": ("v0",),
        "v1": ("v1",),
        "v2": ("pechain_manual_2",),
        "v3": ("pechain_2", "pechain_4"),
        "v4": tuple(f"pearray_{index}" for index in range(4)),
        "v5": ("pechain_v5",),
        "pe": ("pe",),
    }
    if config.version == "all":
        if config.pechain and config.arrays:
            selected = version_checks["v4"]
        elif config.pechain:
            selected = (
                *version_checks["v2"],
                *version_checks["v3"],
            )
        else:
            selected = ("v0", "v1", "pe")
    else:
        selected = version_checks[config.version]
    return {name: checks[name] for name in selected}
