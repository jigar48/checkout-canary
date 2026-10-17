"""Command line entry point.

Exit codes: 0 = journey passed, 1 = journey failed, 2 = bad usage, invalid journey file, or the
browser could not be started.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from checkout_canary import __version__
from checkout_canary.journey import JourneyError, load_journey
from checkout_canary.results import RunResult
from checkout_canary.runner import RESULT_FILE, run_journey

LABELS = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="checkout-canary",
        description="Walk a store's checkout journey with Playwright and report pass/fail.",
        epilog="Only run this against sites you own or have written permission to test.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run one journey file")
    run.add_argument("journey", type=Path, help="path to a journey YAML file")
    run.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="where to write result.json, screenshots and the failure trace (default: results)",
    )
    run.add_argument("--base-url", help="override base_url from the journey file")
    return parser


def print_report(result: RunResult, output_dir: Path) -> None:
    print(f"checkout-canary: {result.journey}")
    for step in result.steps:
        line = f"  [{LABELS[step.status]}] {step.index}. {step.action} {step.target}"
        if step.status != "skipped":
            line += f" ({step.duration_ms} ms)"
        print(line)
        if step.error:
            print(f"         {step.error}")
    print(result.summary)
    print(f"Result file: {output_dir / RESULT_FILE}")
    if result.evidence.failure_screenshot:
        print(f"Failure screenshot: {output_dir / result.evidence.failure_screenshot}")
    if result.evidence.trace:
        print(f"Trace: {output_dir / result.evidence.trace}")
        print(
            f"  (open with: python -m playwright show-trace {output_dir / result.evidence.trace})"
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        journey = load_journey(args.journey, base_url=args.base_url)
    except JourneyError as exc:
        print(f"checkout-canary: {exc}", file=sys.stderr)
        return 2
    try:
        result = run_journey(journey, args.output_dir)
    except PlaywrightError as exc:
        print(
            f"checkout-canary: could not run the browser: {str(exc).splitlines()[0]}\n"
            "If Chromium is missing, install it with: python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2
    print_report(result, args.output_dir)
    return 0 if result.passed else 1
