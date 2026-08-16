"""Cocotb entry point and command-line runner for the PE implementations."""

import logging
from pathlib import Path

import cocotb
from cocotb_tools.runner import get_results, get_runner

from pe_test_config import TestConfig as _TestConfig
from pe_test_config import parse_config
from pe_test_scenarios import run_product_test


# Keep the test output focused on the message emitted for a failed check.
logging.getLogger("cocotb.regression").setLevel(logging.ERROR)


@cocotb.test()
async def test_product(dut):
    await run_product_test(dut, _TestConfig.from_environment())


def run_simulation(config: _TestConfig) -> None:
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
        hdl_toplevel="pe_testbench",
        test_module="test_pe",
        extra_env=config.as_environment(),
    )
    _, failed_tests = get_results(results_file)
    if failed_tests:
        raise SystemExit(1)


if __name__ == "__main__":
    run_simulation(parse_config())
