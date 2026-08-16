"""Shared calculations and assertions for PE test scenarios."""

import logging


test_logger = logging.getLogger("test_pe")


def signed_truncate(value: int, width: int) -> int:
    raw_value = value & ((1 << width) - 1)
    sign_bit = 1 << (width - 1)
    return raw_value - (1 << width) if raw_value & sign_bit else raw_value


def pack_vector(values, width: int) -> int:
    packed = 0
    mask = (1 << width) - 1
    for index, value in enumerate(values):
        packed |= (value & mask) << (index * width)
    return packed


def dot_product(values, weights, width: int) -> int:
    return sum(
        signed_truncate(value, width) * signed_truncate(weight, width)
        for value, weight in zip(values, weights)
    )


def chain_dot_product(a: int, b: int, width: int, length: int = 4) -> int:
    return sum(
        signed_truncate(a + index, width)
        * signed_truncate(b + index, width)
        for index in range(length)
    )


def assert_signal_equals(name: str, signal, expected: int) -> None:
    actual = signal.value.to_signed()
    if actual != expected:
        message = (
            f"[FAIL] {name} value different from expected "
            f"(Got {actual}, Expected {expected})"
        )
        test_logger.error(message)
        assert actual == expected, message
    print(f"[OK] {name} value equal to expected ({actual})")
