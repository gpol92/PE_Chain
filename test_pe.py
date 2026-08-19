"""Cocotb entry point and command-line runner for the PE implementations."""

import logging
import subprocess
import sys
from pathlib import Path

import cocotb
from cocotb_tools.runner import get_results, get_runner

from pe_test_config import TestConfig as _TestConfig
from pe_test_config import parse_config
from pe_test_scenarios import run_product_test


# Keep the test output focused on the message emitted for a failed check.
logging.getLogger("cocotb.regression").setLevel(logging.ERROR)


def _array_version(version: str) -> tuple[str, ...]:
    return ("--pechain", "--arrays", f"--{version}")


REGRESSION_CASES = (
    *((f"V{version} default", (f"--v{version}",)) for version in range(5)),
    *(
        (f"V{version} default", _array_version(f"v{version}"))
        for version in range(5, 17)
    ),
    ("VSpecial default", _array_version("vspecial")),
    ("V12 overlap", (*_array_version("v12"), "--overlap")),
    (
        "V7 NUM_PE=2 calculus",
        (*_array_version("v7"), "--numPE", "2", "--calculus"),
    ),
    (
        "V7 NUM_PE=3 overflow",
        (*_array_version("v7"), "--numPE", "3", "--overflow"),
    ),
    (
        "V12 NUM_PE=2 overlap",
        (*_array_version("v12"), "--numPE", "2", "--overlap"),
    ),
    (
        "V13 NUM_PE=3 NUM_DOT_UNITS=4 overflow",
        (
            *_array_version("v13"),
            "--numPE", "3",
            "--num-dots", "4",
            "--overflow",
        ),
    ),
    (
        "V14 NUM_PE=3 overflow calculus",
        (*_array_version("v14"), "--numPE", "3", "--overflow", "--calculus"),
    ),
    (
        "V15 NUM_PE=2 NUM_EL=3 stream",
        (*_array_version("v15"), "--numPE", "2", "--num-el", "3", "--stream"),
    ),
    (
        "V16 NUM_PE=2 NUM_EL=3 stream",
        (*_array_version("v16"), "--numPE", "2", "--num-el", "3", "--stream"),
    ),
    (
        "VSpecial NUM_PE=2 NUM_DOT_UNITS=4 overlap",
        (
            *_array_version("vspecial"),
            "--numPE", "2",
            "--num-dots", "4",
            "--overlap",
        ),
    ),
)


@cocotb.test()
async def test_product(dut):
    await run_product_test(dut, _TestConfig.from_environment())


def run_simulation(config: _TestConfig) -> None:
    project_dir = Path(__file__).resolve().parent
    runner = get_runner("icarus")
    parameters = {
        "NUM_PE": config.num_pe,
        "NUM_EL": config.num_el,
        "NUM_DOT_UNITS": config.num_dots,
    }
    if config.overflow:
        width_parameter = {
            "v7": "V7_ACC_WIDTH",
            "v13": "SPECIAL_ACC_WIDTH",
            "v14": "V14_ACC_WIDTH",
            "v16": "V15_ACC_WIDTH",
        }[config.version]
        parameters[width_parameter] = 2 * 8

    runner.build(
        sources=[
            project_dir / "pe.sv",
            project_dir / "pe_chain.sv",
            project_dir / "simple_ram.sv",
            project_dir / "pe_system.sv",
            project_dir / "pe_special.sv",
            project_dir / "testbench.sv",
        ],
        hdl_toplevel="pe_testbench",
        parameters=parameters,
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


def run_regression(*, warning: bool = False) -> None:
    """Run every supported regression case and report all failures together."""
    runner = Path(__file__).resolve()
    failures = []
    total = len(REGRESSION_CASES)

    for index, (name, arguments) in enumerate(REGRESSION_CASES, start=1):
        command = [sys.executable, str(runner), *arguments]
        if warning:
            command.append("--warning")
        rendered_arguments = " ".join(arguments)
        print(
            f"\n[REGRESSION] [{index}/{total}] {name}\n"
            f"[REGRESSION] python test_pe.py {rendered_arguments}",
            flush=True,
        )
        result = subprocess.run(command, cwd=runner.parent, check=False)
        if result.returncode:
            failures.append((name, result.returncode))
            print(f"[REGRESSION] FAIL: {name}", flush=True)
        else:
            print(f"[REGRESSION] PASS: {name}", flush=True)

    passed = total - len(failures)
    print(f"\n[REGRESSION] Summary: {passed}/{total} passed", flush=True)
    if failures:
        for name, returncode in failures:
            print(
                f"[REGRESSION] FAIL: {name} (exit code {returncode})",
                flush=True,
            )
        raise SystemExit(1)


if __name__ == "__main__":
    selected_config = parse_config()
    if selected_config.version == "regression":
        run_regression(warning=selected_config.warning)
    else:
        run_simulation(selected_config)
