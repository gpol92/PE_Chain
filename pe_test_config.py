"""Command-line and environment configuration for the PE cocotb tests."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass


PE_VERSIONS = (*tuple(f"v{version}" for version in range(16)), "vspecial")
ARRAY_PIPELINE_VERSIONS = (*tuple(f"v{version}" for version in range(5, 16)), "vspecial")
FLAG_FIELDS = (
    "passed", "positive", "zero", "pechain", "arrays", "calculus", "overlap",
    "overflow", "stream",
)
ENV_NAMES = {
    "passed": "TEST_PASSED_STATUS", "positive": "TEST_POSITIVE_VALUES",
    "zero": "TEST_ZERO_VALUES",
}


@dataclass(frozen=True)
class TestConfig:
    passed: bool = True
    positive: bool = True
    zero: bool = False
    version: str = "all"
    pechain: bool = False
    arrays: bool = False
    calculus: bool = False
    overlap: bool = False
    overflow: bool = False
    stream: bool = False
    warning: bool = False
    num_pe: int = 4
    num_el: int = 4
    num_dots: int = 3

    @classmethod
    def from_environment(cls) -> "TestConfig":
        defaults = cls()
        return cls(
            **{
                name: _env_flag(_env_name(name), getattr(defaults, name))
                for name in FLAG_FIELDS
            },
            version=os.getenv("TEST_VERSION", "all"),
            num_pe=int(os.getenv("TEST_NUM_PE", "4")),
            num_el=int(os.getenv("TEST_NUM_EL", "4")),
            num_dots=int(os.getenv("TEST_NUM_DOTS", "3")),
        )

    def as_environment(self) -> dict[str, str]:
        environment = {
            "COCOTB_LOG_LEVEL": "WARNING" if self.warning else "ERROR",
            "GPI_LOG_LEVEL": "ERROR",
            "TEST_VERSION": self.version,
            "TEST_NUM_PE": str(self.num_pe),
            "TEST_NUM_EL": str(self.num_el),
            "TEST_NUM_DOTS": str(self.num_dots),
        }
        environment.update(
            (_env_name(name), _flag_value(getattr(self, name)))
            for name in FLAG_FIELDS
        )
        return environment


def _env_name(field_name: str) -> str:
    return ENV_NAMES.get(field_name, f"TEST_{field_name.upper()}")


def _env_flag(name: str, default: bool) -> bool:
    return os.getenv(name, _flag_value(default)) == "1"


def _flag_value(value: bool) -> str:
    return "1" if value else "0"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a selected PE or PE-chain Cocotb milestone test"
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
    versions = parser.add_mutually_exclusive_group()
    for version in PE_VERSIONS:
        versions.add_argument(
            f"--{version}",
            action="store_const",
            const=version,
            dest="version",
            help=f"Test the {version.upper()} implementation",
        )
    versions.add_argument(
        "--pe",
        action="store_const",
        const="pe",
        dest="version",
        help="Test the current PE implementation in pe.sv",
    )
    versions.add_argument(
        "--version",
        choices=("v0", "v1", "pe", "all"),
        dest="version",
        help=argparse.SUPPRESS,
    )
    versions.set_defaults(version="all")
    parser.add_argument(
        "--pechain",
        action="store_true",
        help="Select the PE-chain implementation family",
    )
    parser.add_argument(
        "--arrays",
        action="store_true",
        help="Select the vector/array PE-chain implementation family",
    )
    parser.add_argument(
        "--calculus",
        "--debug",
        action="store_true",
        help="Show each PE calculation step (--debug is an alias)",
    )
    parser.add_argument(
        "--overlap",
        action="store_true",
        help="Attempt a second V12, V13, or VSpecial calculation while busy",
    )
    parser.add_argument(
        "--overflow",
        action="store_true",
        help="Run the V7, V13, or V14 overflow testcase",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Run several back-to-back V15 vector batches",
    )
    parser.add_argument(
        "--numPE",
        "--num-pe",
        dest="num_pe",
        type=int,
        default=4,
        metavar="COUNT",
        help="Set the number of processing elements for V5-V15 and VSpecial (default: 4)",
    )
    parser.add_argument(
        "--num-el",
        dest="num_el",
        type=int,
        default=4,
        metavar="COUNT",
        help="Set the number of elements in each V15 PE vector (default: 4)",
    )
    parser.add_argument(
        "--num-dots",
        dest="num_dots",
        type=int,
        default=3,
        metavar="COUNT",
        help="Set the number of chained dot-product units for V13 or VSpecial (default: 3)",
    )
    return parser


def parse_config() -> TestConfig:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.arrays and not args.pechain:
        parser.error("--arrays requires --pechain")
    if args.version in ARRAY_PIPELINE_VERSIONS and not (
        args.pechain and args.arrays
    ):
        parser.error(f"--{args.version} requires --pechain --arrays")
    if args.overlap and args.version not in ("v12", "v13", "vspecial"):
        parser.error("--overlap requires --v12, --v13, or --vspecial")
    if args.overflow and args.version not in ("v7", "v13", "v14"):
        parser.error("--overflow requires --v7, --v13, or --v14")
    if args.stream and args.version != "v15":
        parser.error("--stream requires --v15")
    if args.overflow and args.num_pe < 3:
        parser.error("--overflow requires at least 3 processing elements")
    if args.num_pe < 1:
        parser.error("--numPE must be at least 1")
    if args.num_pe != 4 and args.version not in (
        *tuple(f"v{version}" for version in range(5, 16)), "vspecial"
    ):
        parser.error("--numPE is configurable only for V5-V15 and VSpecial")
    if args.num_el < 1:
        parser.error("--num-el must be at least 1")
    if args.num_el != 4 and args.version != "v15":
        parser.error("--num-el is configurable only for V15")
    if args.num_dots < 1:
        parser.error("--num-dots must be at least 1")
    if args.num_dots != 3 and args.version not in ("v13", "vspecial"):
        parser.error("--num-dots is configurable only for V13 or VSpecial")

    return TestConfig(**vars(args))
