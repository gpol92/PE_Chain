"""Independent cocotb scenarios for each PE implementation family."""

from random import randint

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

CLOCKED_INPUTS = (
    "a", "b", "acc_in", "chain_data_vector", "chain_weight_vector", "valid_in"
)
MEMORY_INPUTS = CLOCKED_INPUTS + (
    "ram_we", "ram_write_addr", "ram_write_data", "ram_read_addr",
    "memory_load_we", "memory_load_weights", "memory_load_addr", "memory_load_data",
    "data_addr", "weight_addr", "v8_valid_in", "v11_valid_in", "special_valid_in",
    "special_data_vectors", "special_weight_vectors", "special_biases",
    "special_result_addr", "start",
)
MEMORY_RESET_OUTPUTS = {
    "v8": ("valid_out_pe_chain_v8", "y_pe_chain_v8"),
    "v9": ("done_v9", "result_v9"),
    "v10": ("busy_v10", "done_v10", "result_v10"),
    "v11": ("valid_out_pe_chain_v11", "y_pe_chain_v11"),
    "v12": ("busy_v12", "done_v12", "error_v12", "result_v12"),
}


def _vector(start: int, length: int) -> tuple[int, ...]:
    return tuple(randint(start, start + length - 1) for _ in range(length))


def _test_vectors(num_pe: int):
    return (
        (_vector(2, num_pe), _vector(-4, num_pe)),
        (_vector(3, num_pe), _vector(5, num_pe)),
    )


def _drive_chain_vectors(dut, data, weights, data_width: int) -> None:
    dut.chain_data_vector.value = pack_vector(data, data_width)
    dut.chain_weight_vector.value = pack_vector(weights, data_width)


async def _tick(dut) -> None:
    """Advance to the next rising edge and sample settled signal values."""
    await RisingEdge(dut.clk)
    await ReadOnly()


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
        "v13": run_v13_system,
        "v14": run_v14_parallel,
        "v15": run_v15_element_array,
        "v16": run_v16_result_memory,
        "vspecial": run_vspecial,
    }.get(config.version, run_combinational)
    await scenario(dut, config)


async def _reset_dut(dut, inputs=CLOCKED_INPUTS) -> None:
    cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
    for name in inputs:
        getattr(dut, name).value = 0
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await _tick(dut)


async def run_v6_pipeline(dut, config: TestConfig) -> None:
    await _reset_dut(dut)
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
        await _tick(dut)
        completed_cycle = cycle - (config.num_pe - 1)
        if 0 <= completed_cycle < len(expected_results):
            assert_signal_equals(
                "pechain_v6", dut.y_pe_chain_v6, expected_results[completed_cycle]
            )
        await FallingEdge(dut.clk)

    dut.rst.value = 1
    await _tick(dut)
    assert dut.y_pe_chain_v6.value.to_signed() == 0, "V6 output was not cleared by reset"


async def run_v7_valid_pipeline(dut, config: TestConfig) -> None:
    await _reset_dut(dut)
    assert dut.valid_out_pe_chain_v7.value == 0, "V7 valid_out was not cleared by reset"
    assert dut.error_out_pe_chain_v7.value == 0, "V7 error_out was not cleared by reset"
    assert int(dut.overflow_out_pe_chain_v7.value) == 0, (
        "V7 overflow map was not cleared by reset"
    )
    assert dut.y_pe_chain_v7.value.to_signed() == 0, "V7 output was not cleared by reset"


    if config.overflow:
        await _run_v7_overflow_vector(dut, config)
        return

    await FallingEdge(dut.clk)
    dut.rst.value = 0
    valid_transactions = [
        (_vector(2, config.num_pe), _vector(3, config.num_pe), True),
        (_vector(9, config.num_pe), _vector(-9, config.num_pe), True),
        (_vector(-4, config.num_pe), _vector(5, config.num_pe), True),
        (_vector(9, config.num_pe), _vector(3, config.num_pe), True),
    ]
    valid_transactions.extend(
        (
            _vector(20 + vector_id, config.num_pe),
            _vector(-30 - vector_id, config.num_pe),
            True,
        )
        for vector_id in range(4, config.num_pe)
    )
    transactions = [
        *valid_transactions,
        (_vector(7, config.num_pe), _vector(9, config.num_pe), False),
    ]
    driven = []
    saw_full_pipeline = False
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

        # Immediately before this edge, PE i must hold element i of the
        # vector accepted i iterations earlier.  The origin indices are
        # cycle-i, so no two active PEs may be working on the same vector.
        await Timer(1, unit="ps")
        active_vector_ids = _assert_v7_pe_vector_mapping(
            dut, driven, cycle, config.num_pe, data_width
        )
        saw_full_pipeline |= len(active_vector_ids) == config.num_pe

        await _tick(dut)

        completed_cycle = cycle - (config.num_pe - 1)
        completed = (
            driven[completed_cycle]
            if completed_cycle >= 0
            else ((0,) * config.num_pe, (0,) * config.num_pe, False)
        )
        expected_data, expected_weights, expected_valid = completed
        actual_valid = bool(dut.valid_out_pe_chain_v7.value)
        actual_error = bool(dut.error_out_pe_chain_v7.value)
        actual_overflow_map = int(dut.overflow_out_pe_chain_v7.value)
        assert not actual_error, f"V7 raised an unexpected overflow at cycle {cycle}"
        assert actual_overflow_map == 0, (
            f"V7 raised unexpected per-PE overflow bits at cycle {cycle}: "
            f"0b{actual_overflow_map:0{config.num_pe}b}"
        )
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

    assert saw_full_pipeline, "V7 proof never observed every PE active simultaneously"

    dut.rst.value = 1
    await _tick(dut)
    assert dut.valid_out_pe_chain_v7.value == 0, "V7 valid_out was not cleared by reset"
    assert dut.error_out_pe_chain_v7.value == 0, "V7 error_out was not cleared by reset"
    assert int(dut.overflow_out_pe_chain_v7.value) == 0, (
        "V7 overflow map was not cleared by reset"
    )
    assert dut.y_pe_chain_v7.value.to_signed() == 0, "V7 output was not cleared by reset"


async def run_v14_parallel(dut, config: TestConfig) -> None:
    """Prove that all PE lanes multiply one vector in the same cycle."""
    await _reset_dut(dut)
    assert dut.valid_out_pe_chain_v14.value == 0, "V14 valid_out was not reset"
    assert dut.error_out_pe_chain_v14.value == 0, "V14 error_out was not reset"
    assert int(dut.overflow_out_pe_chain_v14.value) == 0, (
        "V14 overflow map was not reset"
    )
    assert dut.y_pe_chain_v14.value.to_signed() == 0, "V14 output was not reset"

    if config.overflow:
        await _run_v14_overflow_vector(dut, config)
        return

    await FallingEdge(dut.clk)
    dut.rst.value = 0
    data_width = len(dut.a)
    product_width = 2 * data_width
    transactions = [
        (_vector(2, config.num_pe), _vector(3, config.num_pe), True),
        (_vector(-4, config.num_pe), _vector(5, config.num_pe), True),
        (_vector(9, config.num_pe), _vector(-3, config.num_pe), True),
        ((0,) * config.num_pe, (0,) * config.num_pe, False),
    ]

    for cycle, (data, weights, valid) in enumerate(transactions):
        _drive_chain_vectors(dut, data, weights, data_width)
        dut.valid_in.value = valid
        await Timer(1, unit="ps")

        # Every slice must already contain a product from this same vector.
        product_trace = int(dut.v14_pe_product_trace.value)
        actual_products = []
        for pe_index, (value, weight) in enumerate(zip(data, weights)):
            actual_product = signed_truncate(
                product_trace >> (pe_index * product_width), product_width
            )
            actual_products.append(actual_product)
            expected_product = (
                signed_truncate(value, data_width)
                * signed_truncate(weight, data_width)
            )
            assert actual_product == expected_product, (
                f"V14 PE{pe_index} product mismatch in cycle {cycle}: "
                f"got {actual_product}, expected a[{pe_index}] * b[{pe_index}] "
                f"= {expected_product}"
            )

        await _tick(dut)
        assert bool(dut.valid_out_pe_chain_v14.value) == valid, (
            f"V14 valid mismatch in cycle {cycle}"
        )
        assert dut.error_out_pe_chain_v14.value == 0, (
            f"V14 raised an unexpected overflow in cycle {cycle}"
        )
        assert int(dut.overflow_out_pe_chain_v14.value) == 0, (
            f"V14 raised unexpected per-PE overflow bits in cycle {cycle}"
        )
        expected_sum = dot_product(data, weights, data_width) if valid else 0
        assert_signal_equals("pechain_v14", dut.y_pe_chain_v14, expected_sum)
        if config.calculus and valid:
            _show_v14_calculation(
                cycle,
                data,
                weights,
                actual_products,
                data_width,
                len(dut.y_pe_chain_v14),
                dut.y_pe_chain_v14.value.to_signed(),
                int(dut.overflow_out_pe_chain_v14.value),
            )
        await FallingEdge(dut.clk)

    print(
        f"[OK] V14 executed all {config.num_pe} indexed products concurrently"
    )


async def _run_v14_overflow_vector(dut, config: TestConfig) -> None:
    data_width = len(dut.a)
    max_operand = (1 << (data_width - 1)) - 1
    overflow_vector = (max_operand,) * config.num_pe
    expected_overflow_map = _expected_v7_overflow_map(
        overflow_vector,
        overflow_vector,
        data_width,
        len(dut.y_pe_chain_v14),
    )

    await FallingEdge(dut.clk)
    dut.rst.value = 0
    dut.valid_in.value = 1
    _drive_chain_vectors(dut, overflow_vector, overflow_vector, data_width)
    await _tick(dut)

    assert dut.error_out_pe_chain_v14.value == 1, "V14 did not flag vector overflow"
    assert dut.valid_out_pe_chain_v14.value == 0, "V14 overflow remained valid"
    assert dut.y_pe_chain_v14.value.to_signed() == 0, "V14 overflow data was not zero"
    actual_overflow_map = int(dut.overflow_out_pe_chain_v14.value)
    assert actual_overflow_map == expected_overflow_map, (
        f"V14 per-PE overflow map was 0b{actual_overflow_map:0{config.num_pe}b}, "
        f"expected 0b{expected_overflow_map:0{config.num_pe}b}"
    )

    if config.calculus:
        product_width = 2 * data_width
        product_trace = int(dut.v14_pe_product_trace.value)
        actual_products = [
            signed_truncate(
                product_trace >> (pe_index * product_width), product_width
            )
            for pe_index in range(config.num_pe)
        ]
        _show_v14_calculation(
            0,
            overflow_vector,
            overflow_vector,
            actual_products,
            data_width,
            len(dut.y_pe_chain_v14),
            dut.y_pe_chain_v14.value.to_signed(),
            actual_overflow_map,
        )

    for pe_index in range(config.num_pe):
        status = (
            "overflowing" if (actual_overflow_map >> pe_index) & 1
            else "not overflowing"
        )
        print(f"[OVERFLOW] V14 PE{pe_index}: {status}")
    print(
        f"[OK] pechain_v14 overflow map "
        f"0b{actual_overflow_map:0{config.num_pe}b} for {overflow_vector}"
    )


async def run_v15_element_array(dut, config: TestConfig) -> None:
    """Check one independent NUM_EL-element dot product in every PE."""
    data_width = len(dut.a)
    result_width = len(dut.v15_result_vector) // config.num_pe
    batch_count = 3 if config.stream else 1

    await _reset_dut(
        dut,
        inputs=(
            "v15_valid_in", "v15_data_vector", "v15_weight_vector",
            "v15_acc_vector",
        ),
    )
    await FallingEdge(dut.clk)
    dut.rst.value = 0

    for batch_index in range(batch_count):
        operand_streams = _v15_operand_streams(config.num_pe, config.num_el)
        initial_accumulators = tuple(randint(-10, 10) for _ in range(config.num_pe))
        expected_results = list(initial_accumulators)

        for element_index in range(config.num_el):
            await FallingEdge(dut.clk)
            if element_index == 0:
                dut.v15_acc_vector.value = pack_vector(
                    initial_accumulators, result_width
                )
            operands = tuple(stream[element_index] for stream in operand_streams)
            data = tuple(value for value, _ in operands)
            weights = tuple(weight for _, weight in operands)
            dut.v15_data_vector.value = pack_vector(data, data_width)
            dut.v15_weight_vector.value = pack_vector(weights, data_width)
            dut.v15_valid_in.value = 1

            await _tick(dut)
            expected_valid = element_index == config.num_el - 1
            assert bool(dut.valid_out_pe_chain_v15.value) == expected_valid, (
                f"V15 valid_out mismatch at batch {batch_index}, "
                f"element {element_index}"
            )

            packed_results = int(dut.v15_result_vector.value)
            for pe_index, (raw_value, raw_weight) in enumerate(operands):
                value = signed_truncate(raw_value, data_width)
                weight = signed_truncate(raw_weight, data_width)
                expected_results[pe_index] += value * weight
                actual = signed_truncate(
                    packed_results >> (pe_index * result_width), result_width
                )
                assert actual == expected_results[pe_index], (
                    f"V15 PE{pe_index} batch {batch_index}, element "
                    f"{element_index} mismatch: got {actual}, expected "
                    f"{expected_results[pe_index]}"
                )

        packed_results = int(dut.v15_result_vector.value)
        for pe_index, operand_stream in enumerate(operand_streams):
            data = tuple(value for value, _ in operand_stream)
            weights = tuple(weight for _, weight in operand_stream)
            dot_result = sum(
                signed_truncate(value, data_width)
                * signed_truncate(weight, data_width)
                for value, weight in operand_stream
            )
            actual = signed_truncate(
                packed_results >> (pe_index * result_width), result_width
            )
            print(
                f"[RESULT] V15 batch {batch_index} PE{pe_index}: "
                f"data={data}, weights={weights}, dot={dot_result}, "
                f"acc={initial_accumulators[pe_index]}, result={actual}"
            )

        print(
            f"[OK] V15 batch {batch_index}: {config.num_pe} PEs independently "
            f"computed {config.num_el}-element dot products"
        )

    await FallingEdge(dut.clk)
    dut.v15_valid_in.value = 0
    await _tick(dut)
    assert dut.valid_out_pe_chain_v15.value == 0, "V15 valid_out did not clear"


async def run_v16_result_memory(dut, config: TestConfig) -> None:
    """Check that V16 persists each result vector produced by its V15 core."""
    if config.overflow:
        await _run_v16_overflow_memory(dut, config)
        return

    data_width = len(dut.a)
    result_width = len(dut.v16_result_vector) // config.num_pe
    batch_count = 3 if config.stream else 1
    batches = []

    for _ in range(batch_count):
        operand_streams = _v15_operand_streams(config.num_pe, config.num_el)
        initial_accumulators = tuple(randint(-10, 10) for _ in range(config.num_pe))
        final_results = [
            initial_accumulators[pe_index]
            + sum(
                signed_truncate(value, data_width)
                * signed_truncate(weight, data_width)
                for value, weight in operand_streams[pe_index]
            )
            for pe_index in range(config.num_pe)
        ]
        batches.append((operand_streams, initial_accumulators, final_results))

    await _reset_dut(
        dut,
        inputs=(
            "v16_valid_in", "v16_data_vector", "v16_weight_vector",
            "v16_acc_vector", "v16_result_addr",
        ),
    )
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    assert dut.error_out_pe_chain_v16.value == 0, (
        "V16 error_out was not cleared by reset"
    )
    assert int(dut.overflow_out_pe_chain_v16.value) == 0, (
        "V16 overflow map was not cleared by reset"
    )

    for batch_index, (operand_streams, initial_accumulators, final_results) in enumerate(batches):
        running_results = list(initial_accumulators)
        for element_index in range(config.num_el):
            await FallingEdge(dut.clk)
            operands = tuple(stream[element_index] for stream in operand_streams)
            data = tuple(value for value, _ in operands)
            weights = tuple(weight for _, weight in operands)
            if element_index == 0:
                dut.v16_acc_vector.value = pack_vector(
                    initial_accumulators, result_width
                )
            dut.v16_data_vector.value = pack_vector(data, data_width)
            dut.v16_weight_vector.value = pack_vector(weights, data_width)
            dut.v16_valid_in.value = 1

            stores_previous_batch = batch_index > 0 and element_index == 0
            if stores_previous_batch:
                dut.v16_result_addr.value = batch_index - 1

            await _tick(dut)
            assert bool(dut.valid_out_pe_chain_v16.value) == stores_previous_batch, (
                f"V16 storage valid mismatch at batch {batch_index}, "
                f"element {element_index}"
            )
            assert dut.error_out_pe_chain_v16.value == 0, (
                "V16 reported an unexpected overflow"
            )
            assert int(dut.overflow_out_pe_chain_v16.value) == 0, (
                "V16 reported unexpected per-PE overflow bits"
            )

            for pe_index, (raw_value, raw_weight) in enumerate(operands):
                running_results[pe_index] += (
                    signed_truncate(raw_value, data_width)
                    * signed_truncate(raw_weight, data_width)
                )
            packed_results = int(dut.v16_result_vector.value)
            for pe_index, expected in enumerate(running_results):
                actual = signed_truncate(
                    packed_results >> (pe_index * result_width), result_width
                )
                assert actual == expected, (
                    f"V16 PE{pe_index} batch {batch_index}, element "
                    f"{element_index} mismatch: got {actual}, expected {expected}"
                )

            if stores_previous_batch:
                expected_stored = pack_vector(
                    batches[batch_index - 1][2], result_width
                )
                assert int(dut.v16_ram_result_vector.value) == expected_stored, (
                    f"V16 RAM batch {batch_index - 1} was not stored when valid_out rose"
                )

        assert running_results == final_results

    # The final V15 completion is written on the following edge. Deasserting
    # valid_in here also proves that storage does not start another calculation.
    await FallingEdge(dut.clk)
    dut.v16_valid_in.value = 0
    dut.v16_result_addr.value = batch_count - 1
    await _tick(dut)
    assert dut.valid_out_pe_chain_v16.value == 1, (
        "V16 did not mark the final result-RAM write"
    )
    assert dut.error_out_pe_chain_v16.value == 0, (
        "V16 reported an unexpected final-batch overflow"
    )
    assert int(dut.overflow_out_pe_chain_v16.value) == 0, (
        "V16 reported unexpected final-batch overflow bits"
    )
    expected_final = pack_vector(batches[-1][2], result_width)
    assert int(dut.v16_ram_result_vector.value) == expected_final, (
        "V16 final result vector was not stored"
    )

    await FallingEdge(dut.clk)
    await _tick(dut)
    assert dut.valid_out_pe_chain_v16.value == 0, "V16 valid_out did not clear"

    # The RAM has an asynchronous read port, so every prior address can be
    # revisited without advancing the compute engine.
    await FallingEdge(dut.clk)
    for batch_index, (_, _, final_results) in enumerate(batches):
        dut.v16_result_addr.value = batch_index
        await Timer(1, unit="ps")
        expected_stored = pack_vector(final_results, result_width)
        actual_stored = int(dut.v16_ram_result_vector.value)
        assert actual_stored == expected_stored, (
            f"V16 retained RAM batch {batch_index} mismatch: got "
            f"0x{actual_stored:x}, expected 0x{expected_stored:x}"
        )

    print(
        f"[OK] V16 stored {batch_count} result vector(s) produced by its V15 core"
    )


async def _run_v16_overflow_memory(dut, config: TestConfig) -> None:
    """Check V16's per-PE overflow map, sanitized RAM write, and recovery."""
    data_width = len(dut.a)
    result_width = len(dut.v16_result_vector) // config.num_pe
    max_accumulator = (1 << (result_width - 1)) - 1
    min_accumulator = -(1 << (result_width - 1))
    overflow_lane_count = min(config.num_pe, 2)
    expected_overflow_map = (1 << overflow_lane_count) - 1

    initial_accumulators = tuple(
        max_accumulator if pe_index == 0
        else min_accumulator if pe_index == 1
        else 0
        for pe_index in range(config.num_pe)
    )
    data = tuple(
        1 if pe_index == 0 else -1 if pe_index == 1 else pe_index + 1
        for pe_index in range(config.num_pe)
    )
    weights = (1,) * config.num_pe
    expected_stored_results = tuple(
        0 if pe_index < overflow_lane_count else data[pe_index] * config.num_el
        for pe_index in range(config.num_pe)
    )

    await _reset_dut(
        dut,
        inputs=(
            "v16_valid_in", "v16_data_vector", "v16_weight_vector",
            "v16_acc_vector", "v16_result_addr",
        ),
    )
    assert dut.valid_out_pe_chain_v16.value == 0, (
        "V16 valid_out was not cleared by reset"
    )
    assert dut.error_out_pe_chain_v16.value == 0, (
        "V16 error_out was not cleared by reset"
    )
    assert int(dut.overflow_out_pe_chain_v16.value) == 0, (
        "V16 overflow map was not cleared by reset"
    )

    await FallingEdge(dut.clk)
    dut.rst.value = 0
    dut.v16_acc_vector.value = pack_vector(initial_accumulators, result_width)
    dut.v16_data_vector.value = pack_vector(data, data_width)
    dut.v16_weight_vector.value = pack_vector(weights, data_width)
    dut.v16_valid_in.value = 1

    for element_index in range(config.num_el):
        await _tick(dut)
        assert dut.valid_out_pe_chain_v16.value == 0, (
            f"V16 stored the overflow batch too early at element {element_index}"
        )
        assert dut.error_out_pe_chain_v16.value == 0, (
            f"V16 reported the overflow before its RAM write at element {element_index}"
        )
        await FallingEdge(dut.clk)

    dut.v16_valid_in.value = 0
    dut.v16_result_addr.value = 0
    await _tick(dut)
    assert dut.valid_out_pe_chain_v16.value == 1, (
        "V16 did not mark the overflowing result-RAM write"
    )
    assert dut.error_out_pe_chain_v16.value == 1, (
        "V16 did not report accumulator overflow"
    )
    actual_overflow_map = int(dut.overflow_out_pe_chain_v16.value)
    assert actual_overflow_map == expected_overflow_map, (
        f"V16 overflow map was 0b{actual_overflow_map:0{config.num_pe}b}, "
        f"expected 0b{expected_overflow_map:0{config.num_pe}b}"
    )
    expected_stored = pack_vector(expected_stored_results, result_width)
    assert int(dut.v16_ram_result_vector.value) == expected_stored, (
        "V16 did not zero the overflowing PE while retaining safe PE results"
    )

    await FallingEdge(dut.clk)
    await _tick(dut)
    assert dut.valid_out_pe_chain_v16.value == 0, "V16 valid_out did not clear"
    assert dut.error_out_pe_chain_v16.value == 0, "V16 error_out did not clear"
    assert int(dut.overflow_out_pe_chain_v16.value) == 0, (
        "V16 overflow map did not clear"
    )

    # A safe batch must recover immediately and use the next RAM address.
    await FallingEdge(dut.clk)
    safe_accumulators = (5,) * config.num_pe
    safe_data = (2,) * config.num_pe
    safe_weights = (3,) * config.num_pe
    expected_safe_results = tuple(
        accumulator + (2 * 3 * config.num_el)
        for accumulator in safe_accumulators
    )
    dut.v16_acc_vector.value = pack_vector(safe_accumulators, result_width)
    dut.v16_data_vector.value = pack_vector(safe_data, data_width)
    dut.v16_weight_vector.value = pack_vector(safe_weights, data_width)
    dut.v16_valid_in.value = 1
    for element_index in range(config.num_el):
        await _tick(dut)
        assert dut.error_out_pe_chain_v16.value == 0, (
            f"V16 retained overflow into recovery element {element_index}"
        )
        await FallingEdge(dut.clk)

    dut.v16_valid_in.value = 0
    dut.v16_result_addr.value = 1
    await _tick(dut)
    assert dut.valid_out_pe_chain_v16.value == 1, (
        "V16 did not store the recovery batch"
    )
    assert dut.error_out_pe_chain_v16.value == 0, (
        "V16 reported overflow for the recovery batch"
    )
    assert int(dut.overflow_out_pe_chain_v16.value) == 0, (
        "V16 retained overflow bits for the recovery batch"
    )
    expected_safe = pack_vector(expected_safe_results, result_width)
    assert int(dut.v16_ram_result_vector.value) == expected_safe, (
        "V16 recovery batch was not stored at the next RAM address"
    )

    await FallingEdge(dut.clk)
    dut.v16_result_addr.value = 0
    await Timer(1, unit="ps")
    assert int(dut.v16_ram_result_vector.value) == expected_stored, (
        "V16 overflow result was not retained at RAM address zero"
    )
    print(
        f"[OK] V16 stored overflow map 0b{actual_overflow_map:0{config.num_pe}b} "
        "and recovered at the next RAM address"
    )


def _v15_operand_streams(num_pe: int, num_el: int):
    """Create one random NUM_EL-element operand-vector pair for every PE."""
    return tuple(
        tuple(
            (
                randint(-5, 5),
                randint(-5, 5),
            )
            for _ in range(num_el)
        )
        for _ in range(num_pe)
    )


async def _run_v7_overflow_vector(dut, config: TestConfig) -> None:
    data_width = len(dut.a)
    max_operand = (1 << (data_width - 1)) - 1
    overflow_vector = (max_operand,) * config.num_pe

    await FallingEdge(dut.clk)
    dut.rst.value = 0
    dut.valid_in.value = 1
    _drive_chain_vectors(dut, overflow_vector, overflow_vector, data_width)

    for cycle in range(config.num_pe):
        await _tick(dut)
        if cycle < config.num_pe - 1:
            assert dut.error_out_pe_chain_v7.value == 0, (
                f"V7 reported overflow too early at cycle {cycle}"
            )
        await FallingEdge(dut.clk)
        dut.valid_in.value = 0

    assert dut.error_out_pe_chain_v7.value == 1, "V7 did not flag vector overflow"
    assert dut.valid_out_pe_chain_v7.value == 0, "V7 overflow remained valid"
    assert dut.y_pe_chain_v7.value.to_signed() == 0, "V7 overflow data was not zero"
    overflow_map = int(dut.overflow_out_pe_chain_v7.value)
    expected_overflow_map = _expected_v7_overflow_map(
        overflow_vector, overflow_vector, data_width, len(dut.y_pe_chain_v7)
    )
    assert overflow_map == expected_overflow_map, (
        f"V7 per-PE overflow map was 0b{overflow_map:0{config.num_pe}b}, "
        f"expected 0b{expected_overflow_map:0{config.num_pe}b}"
    )
    for pe_index in range(config.num_pe):
        status = "overflowing" if (overflow_map >> pe_index) & 1 else "not overflowing"
        print(f"[OVERFLOW] V7 PE{pe_index}: {status}")
    print(
        f"[OK] pechain_v7 overflow map "
        f"0b{overflow_map:0{config.num_pe}b} for {overflow_vector}"
    )


def _expected_v7_overflow_map(
    data: tuple[int, ...],
    weights: tuple[int, ...],
    data_width: int,
    acc_width: int,
) -> int:
    accumulator = 0
    minimum = -(1 << (acc_width - 1))
    maximum = (1 << (acc_width - 1)) - 1

    for pe_index, (raw_data, raw_weight) in enumerate(zip(data, weights)):
        value = signed_truncate(raw_data, data_width)
        weight = signed_truncate(raw_weight, data_width)
        next_accumulator = accumulator + value * weight
        if not minimum <= next_accumulator <= maximum:
            return 1 << pe_index
        accumulator = next_accumulator
    return 0


def _assert_v7_pe_vector_mapping(
    dut, driven, cycle: int, num_pe: int, data_width: int
) -> list[tuple[int, int, int, int]]:
    data_trace = int(dut.v7_pe_data_trace.value)
    weight_trace = int(dut.v7_pe_weight_trace.value)
    valid_trace = int(dut.v7_pe_valid_trace.value)
    active_vector_ids = []

    for pe_index in range(num_pe):
        vector_id = cycle - pe_index
        vector_is_present = 0 <= vector_id < len(driven)
        expected_valid = vector_is_present and driven[vector_id][2]
        actual_valid = bool((valid_trace >> pe_index) & 1)
        assert actual_valid == expected_valid, (
            f"V7 PE{pe_index} valid mismatch at iteration {cycle}: "
            f"got {actual_valid}, expected {expected_valid} for vector {vector_id}"
        )
        if not expected_valid:
            continue

        expected_data = signed_truncate(driven[vector_id][0][pe_index], data_width)
        expected_weight = signed_truncate(driven[vector_id][1][pe_index], data_width)
        actual_data = signed_truncate(
            data_trace >> (pe_index * data_width), data_width
        )
        actual_weight = signed_truncate(
            weight_trace >> (pe_index * data_width), data_width
        )
        assert (actual_data, actual_weight) == (expected_data, expected_weight), (
            f"V7 PE{pe_index} used the wrong vector at iteration {cycle}: "
            f"got ({actual_data}, {actual_weight}), expected vector {vector_id} "
            f"element {pe_index} = ({expected_data}, {expected_weight})"
        )
        active_vector_ids.append(
            (pe_index, vector_id, actual_data, actual_weight)
        )

    vector_ids = [vector_id for _, vector_id, _, _ in active_vector_ids]
    assert len(vector_ids) == len(set(vector_ids)), (
        f"V7 iteration {cycle} assigned one vector to multiple PEs: {vector_ids}"
    )
    return active_vector_ids


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

    if version == "v11":
        await _verify_v11_memories(dut, data_width, data_vectors, weight_vectors)
    run_transactions = {
        "v8": _run_v8_transactions,
        "v9": _run_v9_transactions,
        "v10": _run_v10_transactions,
        "v11": _run_v11_transactions,
    }[version]
    await run_transactions(dut, config, data_width, data_vectors, weight_vectors)


async def _initialize_memory_system(dut) -> None:
    await _reset_dut(dut, MEMORY_INPUTS)


def _assert_memory_reset(dut, version: str) -> None:
    for name in MEMORY_RESET_OUTPUTS[version]:
        assert int(getattr(dut, name).value) == 0, (
            f"{version.upper()} {name} was not cleared by reset"
        )


async def _test_standalone_ram(dut) -> None:
    await FallingEdge(dut.clk)
    dut.ram_we.value = 1
    dut.ram_write_addr.value = 2
    dut.ram_write_data.value = 0xA5
    await _tick(dut)
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
            await _tick(dut)


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

        await _tick(dut)
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

        await _tick(dut)
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
    await _tick(dut)
    _assert_memory_reset(dut, "v9")


async def _run_v9_command(
    dut, address: int, expected: int, num_pe: int, hold_start: bool = False
) -> None:
    dut.data_addr.value = address
    dut.weight_addr.value = address
    dut.start.value = 1
    await _tick(dut)
    await FallingEdge(dut.clk)
    if not hold_start:
        dut.start.value = 0

    for _ in range(num_pe + 4):
        await _tick(dut)
        if dut.done_v9.value == 1:
            assert_signal_equals("V9 result", dut.result_v9, expected)
            await FallingEdge(dut.clk)
            if hold_start:
                await _tick(dut)
                assert dut.done_v9.value == 1, "V9 left DONE while start was still asserted"
                await FallingEdge(dut.clk)
                dut.start.value = 0
            await _tick(dut)
            assert dut.done_v9.value == 0, "V9 did not return from DONE to IDLE"
            print(f"[OK] V9 FSM completed with expected result ({expected})")
            await FallingEdge(dut.clk)
            return
        await FallingEdge(dut.clk)
    assert False, "V9 timed out waiting for done"


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
    await _tick(dut)
    assert dut.busy_v10.value == 1, "V10 did not assert busy for an accepted command"
    assert dut.done_v10.value == 0, "V10 asserted done before the result was ready"

    await FallingEdge(dut.clk)
    dut.start.value = 0
    if try_retrigger:
        await _tick(dut)
        assert dut.busy_v10.value == 1, "V10 dropped busy before completion"
        await FallingEdge(dut.clk)
        rejected_address = 1 - address
        dut.data_addr.value = rejected_address
        dut.weight_addr.value = rejected_address
        dut.start.value = 1

    for _ in range(num_pe + 4):
        await _tick(dut)
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
        await _tick(dut)
        assert dut.done_v10.value == 1, "V10 did not hold done for a held retrigger attempt"
        assert dut.busy_v10.value == 0, "V10 retriggered while waiting for start to be released"
        await FallingEdge(dut.clk)

    dut.start.value = 0
    await _tick(dut)
    assert dut.done_v10.value == 0, "V10 did not clear done after start was released"
    assert dut.busy_v10.value == 0, "V10 was busy without an accepted command"

    if try_retrigger:
        for _ in range(5):
            await _tick(dut)
            assert dut.busy_v10.value == 0, "V10 executed the rejected retrigger"
            assert dut.done_v10.value == 0, "V10 completed the rejected retrigger"
            assert dut.result_v10.value.to_signed() == expected, (
                "V10 changed result after rejecting a retrigger"
            )
            await FallingEdge(dut.clk)

    scenario = "with retrigger attempt" if try_retrigger else "without retrigger"
    print(f"[OK] V10 command completed {scenario} ({expected})")


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
    await _tick(dut)
    assert dut.busy_v12.value == 0, "V12 accepted B before entering LOAD_A"

    await FallingEdge(dut.clk)
    dut.memory_load_we.value = 0
    dut.start.value = 1
    await _tick(dut)
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
    await _tick(dut)
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
        await _tick(dut)

    for write_address, values in enumerate(weight_vectors):
        await FallingEdge(dut.clk)
        dut.memory_load_we.value = 1
        dut.memory_load_weights.value = 1
        dut.memory_load_addr.value = write_address
        dut.memory_load_data.value = pack_vector(values, data_width)
        await _tick(dut)

    # Once LOAD_B has started, a late A write must not alter operand memory.
    await FallingEdge(dut.clk)
    dut.memory_load_we.value = 1
    dut.memory_load_weights.value = 0
    dut.memory_load_addr.value = address
    dut.memory_load_data.value = pack_vector([9] * config.num_pe, data_width)
    await _tick(dut)

    await FallingEdge(dut.clk)
    dut.memory_load_we.value = 0
    await _tick(dut)
    assert dut.busy_v12.value == 0, "V12 became busy before start"

    await FallingEdge(dut.clk)
    dut.data_addr.value = address
    dut.weight_addr.value = address
    dut.start.value = 1
    await _tick(dut)
    assert dut.busy_v12.value == 1, "V12 did not enter START_CALC"
    assert dut.done_v12.value == 0, "V12 asserted done before starting the pipeline"

    await FallingEdge(dut.clk)
    dut.start.value = 0
    await _tick(dut)
    expected_error = int(config.overlap and address > 0)
    assert int(dut.error_v12.value) == expected_error, (
        "V12 overlap error did not retain its expected state"
    )

    if config.overlap and address == 0:
        await FallingEdge(dut.clk)
        dut.data_addr.value = 1 - address
        dut.weight_addr.value = 1 - address
        dut.start.value = 1
        await _tick(dut)
        assert dut.busy_v12.value == 1, "V12 was not busy during the overlap attempt"
        assert dut.error_v12.value == 1, "V12 did not flag the overlap attempt"
        await FallingEdge(dut.clk)
        dut.start.value = 0

    for _ in range(config.num_pe + 3):
        await FallingEdge(dut.clk)
        await _tick(dut)
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

    await FallingEdge(dut.clk)
    await _tick(dut)
    assert dut.done_v12.value == 0, "V12 did not return to IDLE after start was released"
    print(f"[OK] V12 load/execute sequence completed ({expected})")


def _pack_unit_vectors(vectors, width: int) -> int:
    vector_width = len(vectors[0]) * width
    return sum(
        pack_vector(vector, width) << (unit_index * vector_width)
        for unit_index, vector in enumerate(vectors)
    )


def _drive_special_request(dut, data, weights, biases, data_width: int) -> None:
    dut.special_data_vectors.value = _pack_unit_vectors(data, data_width)
    dut.special_weight_vectors.value = _pack_unit_vectors(weights, data_width)
    dut.special_biases.value = pack_vector(
        biases, len(dut.special_biases) // len(data)
    )
    dut.special_valid_in.value = 1


def _clear_special_request(dut) -> None:
    for name in (
        "special_valid_in", "special_data_vectors", "special_weight_vectors",
        "special_biases",
    ):
        getattr(dut, name).value = 0


async def run_vspecial(dut, config: TestConfig) -> None:
    await _run_biased_dot_product_system(dut, config, "vspecial", "VSpecial")


async def run_v13_system(dut, config: TestConfig) -> None:
    if config.overflow:
        await _run_v13_overflow_case(dut, config)
        return
    await _run_biased_dot_product_system(dut, config, "v13", "V13")


async def _run_v13_overflow_case(dut, config: TestConfig) -> None:
    await _initialize_memory_system(dut)
    assert dut.busy_v13.value == 0, "V13 busy was not cleared by reset"
    assert dut.done_v13.value == 0, "V13 done was not cleared by reset"
    assert dut.error_v13.value == 0, "V13 error was not cleared by reset"
    assert int(dut.overflow_v13.value) == 0, (
        "V13 overflow map was not cleared by reset"
    )

    data_width = len(dut.a)
    acc_width = len(dut.result_v13) - 1
    max_operand = (1 << (data_width - 1)) - 1
    overflow_vector = (max_operand,) * config.num_pe
    safe_vector = (1,) * config.num_pe
    vectors = (overflow_vector,) + (safe_vector,) * (config.num_dots - 1)
    expected_pe_map = _expected_v7_overflow_map(
        overflow_vector, overflow_vector, data_width, acc_width
    )
    expected_overflow_map = expected_pe_map
    assert expected_overflow_map.bit_count() == 1, (
        "V13 overflow stimulus must select exactly one PE"
    )

    overflow_pe_index = expected_pe_map.bit_length() - 1
    expected_results = (0,) + (config.num_pe - 1,) * (config.num_dots - 1)

    await FallingEdge(dut.clk)
    _drive_special_request(dut, vectors, vectors, (), data_width)
    dut.rst.value = 0
    await _tick(dut)
    assert dut.busy_v13.value == 1, "V13 did not accept the overflow request"

    await FallingEdge(dut.clk)
    _clear_special_request(dut)

    for _ in range(config.num_dots * (config.num_pe + 1) + 4):
        await _tick(dut)
        if dut.done_v13.value == 1:
            break
        assert dut.busy_v13.value == 1, "V13 dropped busy after an overflow"
        await FallingEdge(dut.clk)
    else:
        assert False, "V13 timed out after an overflow"

    assert dut.busy_v13.value == 0, "V13 remained busy after an overflow"
    assert dut.error_v13.value == 1, "V13 did not report the overflow"
    actual_overflow_map = int(dut.overflow_v13.value)
    assert actual_overflow_map == expected_overflow_map, (
        f"V13 overflow map was 0b{actual_overflow_map:0{config.num_dots * config.num_pe}b}, "
        f"expected 0b{expected_overflow_map:0{config.num_dots * config.num_pe}b}"
    )

    await FallingEdge(dut.clk)
    for unit_index, expected_result in enumerate(expected_results):
        dut.special_result_addr.value = unit_index
        await Timer(1, unit="ps")
        assert_signal_equals(
            f"V13 overflow result RAM address {unit_index}",
            dut.result_v13,
            expected_result,
        )
        status = (actual_overflow_map >> (unit_index * config.num_pe)) & (
            (1 << config.num_pe) - 1
        )
        if status:
            print(
                f"[PE{overflow_pe_index} OVERFLOW] V13 unit {unit_index}; "
                "inactive for the remaining units in this calculation period"
            )

    print(
        f"[OK] V13 completed with overflow map "
        f"0b{actual_overflow_map:0{config.num_dots * config.num_pe}b}"
    )


async def _run_biased_dot_product_system(
    dut, config: TestConfig, signal_suffix: str, label: str
) -> None:
    await _initialize_memory_system(dut)
    busy = getattr(dut, f"busy_{signal_suffix}")
    done = getattr(dut, f"done_{signal_suffix}")
    result = getattr(dut, f"result_{signal_suffix}")
    assert busy.value == 0, f"{label} busy was not cleared by reset"
    assert done.value == 0, f"{label} done was not cleared by reset"
    if signal_suffix == "v13":
        assert dut.error_v13.value == 0, "V13 error was not cleared by reset"
        assert int(dut.overflow_v13.value) == 0, (
            "V13 overflow map was not cleared by reset"
        )

    data_width = len(dut.a)
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
            _show_biased_dot_product_calculation(
                label, unit_index, data, weights, bias, data_width
            )
    if not config.passed:
        expected_results[0] += 1

    await FallingEdge(dut.clk)
    _drive_special_request(dut, data_vectors, weight_vectors, biases, data_width)
    dut.rst.value = 0
    await _tick(dut)
    assert busy.value == 1, f"{label} did not accept the request"
    assert done.value == 0, f"{label} completed too early"

    await FallingEdge(dut.clk)
    # Inputs are captured with the accepted request and may change while busy.
    _clear_special_request(dut)

    if config.overlap:
        overlap_data = tuple(
            _vector(30 + unit_index, config.num_pe)
            for unit_index in range(config.num_dots)
        )
        overlap_weights = tuple(
            _vector(-20 - unit_index, config.num_pe)
            for unit_index in range(config.num_dots)
        )
        overlap_biases = tuple(
            100 + unit_index for unit_index in range(config.num_dots)
        )
        _drive_special_request(
            dut, overlap_data, overlap_weights, overlap_biases, data_width
        )
        await _tick(dut)
        assert busy.value == 1, (
            f"{label} was not busy during the overlap attempt"
        )
        assert done.value == 0, (
            f"{label} completed during the overlap attempt"
        )
        await FallingEdge(dut.clk)
        _clear_special_request(dut)

    for _ in range(config.num_dots * (config.num_pe + 1) + 4):
        await _tick(dut)
        if done.value == 1:
            break
        assert busy.value == 1, f"{label} dropped busy before completion"
        await FallingEdge(dut.clk)
    else:
        assert False, f"{label} timed out waiting for completion"

    assert busy.value == 0, f"{label} remained busy after completion"
    if signal_suffix == "v13":
        assert dut.error_v13.value == 0, "V13 reported an unexpected overflow"
        assert int(dut.overflow_v13.value) == 0, (
            "V13 reported unexpected per-unit overflow bits"
        )
    await FallingEdge(dut.clk)
    for address, expected in enumerate(expected_results):
        dut.special_result_addr.value = address
        await Timer(1, unit="ps")
        assert_signal_equals(
            f"{label} result RAM address {address}", result, expected
        )

    # Present the next request while done is still asserted. It must be accepted
    # on the immediately following edge, without an idle cycle between requests.
    back_to_back_data = tuple(
        _vector(-12 - unit_index, config.num_pe)
        for unit_index in range(config.num_dots)
    )
    back_to_back_weights = tuple(
        _vector(6 + unit_index, config.num_pe)
        for unit_index in range(config.num_dots)
    )
    back_to_back_biases = tuple(
        -30 + unit_index for unit_index in range(config.num_dots)
    )
    back_to_back_expected = [
        dot_product(data, weights, data_width) + bias
        for data, weights, bias in zip(
            back_to_back_data, back_to_back_weights, back_to_back_biases
        )
    ]
    _drive_special_request(
        dut,
        back_to_back_data,
        back_to_back_weights,
        back_to_back_biases,
        data_width,
    )
    await _tick(dut)
    assert busy.value == 1, (
        f"{label} did not accept a request immediately after completion"
    )
    assert done.value == 0, (
        f"{label} done was not cleared by the back-to-back request"
    )

    await FallingEdge(dut.clk)
    _clear_special_request(dut)

    for _ in range(config.num_dots * (config.num_pe + 1) + 4):
        await _tick(dut)
        if done.value == 1:
            break
        assert busy.value == 1, (
            f"{label} dropped busy during the back-to-back request"
        )
        await FallingEdge(dut.clk)
    else:
        assert False, f"{label} timed out on the back-to-back request"

    assert busy.value == 0, (
        f"{label} remained busy after the back-to-back request"
    )
    if signal_suffix == "v13":
        assert dut.error_v13.value == 0, (
            "V13 reported an unexpected back-to-back overflow"
        )
        assert int(dut.overflow_v13.value) == 0, (
            "V13 retained unexpected back-to-back overflow bits"
        )
    await FallingEdge(dut.clk)
    for address, expected in enumerate(back_to_back_expected):
        dut.special_result_addr.value = address
        await Timer(1, unit="ps")
        assert_signal_equals(
            f"{label} back-to-back result RAM address {address}",
            result,
            expected,
        )

    await _tick(dut)
    assert done.value == 0, f"{label} done was not a one-cycle pulse"
    scenario = "with overlap attempt" if config.overlap else "without overlap"
    print(
        f"[OK] {label} stored biased dot products {scenario}; "
        f"back-to-back results {back_to_back_expected}"
    )


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


def _show_v14_calculation(
    cycle: int,
    data,
    weights,
    products,
    data_width: int,
    accumulator_width: int,
    result: int,
    overflow_map: int,
) -> None:
    """Show the parallel PE products and each following reduction step."""
    running_total = 0
    overflow_seen = False
    minimum = -(1 << (accumulator_width - 1))
    maximum = (1 << (accumulator_width - 1)) - 1
    print(
        f"[DEBUG] V14 cycle {cycle}: {len(products)} PEs calculate in parallel"
    )
    for pe_index, (raw_value, raw_weight, product) in enumerate(
        zip(data, weights, products)
    ):
        value = signed_truncate(raw_value, data_width)
        weight = signed_truncate(raw_weight, data_width)
        print(
            f"[DEBUG] V14 cycle {cycle} PE{pe_index} product: "
            f"data[{pe_index}] * weight[{pe_index}] = "
            f"{value} * {weight} = {product}"
        )
        if overflow_seen:
            print(
                f"[DEBUG] V14 cycle {cycle} reducer after PE{pe_index}: "
                "skipped because an earlier step overflowed"
            )
            continue

        reduced_total = running_total + product
        if (overflow_map >> pe_index) & 1:
            print(
                f"[DEBUG] V14 cycle {cycle} reducer after PE{pe_index}: "
                f"{running_total} + {product} = {reduced_total} -> overflow "
                f"(range {minimum}..{maximum})"
            )
            overflow_seen = True
        else:
            print(
                f"[DEBUG] V14 cycle {cycle} reducer after PE{pe_index}: "
                f"{running_total} + {product} = {reduced_total}"
            )
            running_total = reduced_total

    if overflow_map:
        print(
            f"[DEBUG] V14 cycle {cycle} result: error, output={result}, "
            f"overflow_map=0b{overflow_map:0{len(products)}b}"
        )
    else:
        print(f"[DEBUG] V14 cycle {cycle} result: output={result}, valid=1")


def _show_biased_dot_product_calculation(
    label: str,
    unit_index: int,
    data: tuple[int, ...],
    weights: tuple[int, ...],
    bias: int,
    data_width: int,
) -> None:
    running_total = bias
    print(f"[CALCULUS] {label} unit {unit_index}: bias = {bias}")
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
