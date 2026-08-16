"""Command-line and environment configuration for the PE cocotb tests."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass


PIPELINED_VERSIONS = tuple(f"v{version}" for version in range(5, 11))


@dataclass(frozen=True)
class TestConfig:
    passed: bool = True
    positive: bool = True
    zero: bool = False
    version: str = "all"
    pechain: bool = False
    arrays: bool = False
    pipeline_version: str | None = None
    warning: bool = False

    @classmethod
    def from_environment(cls) -> "TestConfig":
        enabled_versions = [
            version
            for version in PIPELINED_VERSIONS
            if os.getenv(f"TEST_{version.upper()}", "0") == "1"
        ]
        return cls(
            passed=_env_flag("TEST_PASSED_STATUS", True),
            positive=_env_flag("TEST_POSITIVE_VALUES", True),
            zero=_env_flag("TEST_ZERO_VALUES", False),
            version=os.getenv("TEST_VERSION", "all"),
            pechain=_env_flag("TEST_PECHAIN", False),
            arrays=_env_flag("TEST_ARRAYS", False),
            pipeline_version=enabled_versions[0] if enabled_versions else None,
        )

    def as_environment(self) -> dict[str, str]:
        environment = {
            "COCOTB_LOG_LEVEL": "WARNING" if self.warning else "ERROR",
            "GPI_LOG_LEVEL": "ERROR",
            "TEST_PASSED_STATUS": _flag_value(self.passed),
            "TEST_POSITIVE_VALUES": _flag_value(self.positive),
            "TEST_ZERO_VALUES": _flag_value(self.zero),
            "TEST_VERSION": self.version,
            "TEST_PECHAIN": _flag_value(self.pechain),
            "TEST_ARRAYS": _flag_value(self.arrays),
        }
        environment.update(
            {
                f"TEST_{version.upper()}": _flag_value(
                    self.pipeline_version == version
                )
                for version in PIPELINED_VERSIONS
            }
        )
        return environment


def _env_flag(name: str, default: bool) -> bool:
    return os.getenv(name, _flag_value(default)) == "1"


def _flag_value(value: bool) -> str:
    return "1" if value else "0"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set the expected value to make the test pass or fail"
    )
    parser.add_argument(
        "--passed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Default status PASS. Use --no-passed to fail.",
    )
    parser.add_argument(
        "--positive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Default positive values. Use --no-positive to fail",
    )
    parser.add_argument("--zero", action="store_true", help="Use zero as the first operand")
    parser.add_argument(
        "--warning", action="store_true", help="Show only Cocotb warnings and errors"
    )
    parser.add_argument(
        "--version",
        choices=("v0", "v1", "pe", "all"),
        default="all",
        help="DUT to check (default: all; pe is the implementation in pe.sv)",
    )
    parser.add_argument(
        "--pechain",
        action="store_true",
        help="Test the manual and parameterized pe_chain implementations",
    )
    parser.add_argument(
        "--arrays",
        action="store_true",
        help="With --pechain, test the V4 array implementation",
    )
    for version, help_text in {
        "v5": "test the V5 dot-product chain",
        "v6": "test the V6 clocked pipeline",
        "v7": "test the V7 valid pipeline",
        "v8": "test RAM and the V8 memory-backed chain",
        "v9": "test the V9 FSM-controlled system",
        "v10": "test the V10 command interface",
    }.items():
        parser.add_argument(
            f"--{version}",
            action="store_true",
            help=f"With --pechain --arrays, {help_text}",
        )
    return parser


def parse_config() -> TestConfig:
    parser = build_argument_parser()
    args = parser.parse_args()
    selected = [version for version in PIPELINED_VERSIONS if getattr(args, version)]

    if args.arrays and not args.pechain:
        parser.error("--arrays requires --pechain")
    if selected and not (args.pechain and args.arrays):
        parser.error(f"--{selected[0]} requires --pechain --arrays")
    if len(selected) > 1:
        parser.error("--v5 through --v10 are mutually exclusive")

    return TestConfig(
        passed=args.passed,
        positive=args.positive,
        zero=args.zero,
        version=args.version,
        pechain=args.pechain,
        arrays=args.arrays,
        pipeline_version=selected[0] if selected else None,
        warning=args.warning,
    )
