"""Command line entry point."""

import argparse
from collections.abc import Sequence

from checkout_canary import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="checkout-canary",
        description="Walk a store's checkout journey with Playwright and report pass/fail.",
        epilog="Only run this against sites you own or have written permission to test.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_subparsers(dest="command", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
