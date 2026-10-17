"""Playwright runner: executes one journey and returns a RunResult."""

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Page, expect, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from checkout_canary import __version__
from checkout_canary.journey import (
    ClickStep,
    ExpectTextStep,
    ExpectVisibleStep,
    FillStep,
    GotoStep,
    Journey,
    ScreenshotStep,
    describe_step,
)
from checkout_canary.results import Evidence, RunResult, StepResult, build_result

USER_AGENT = f"checkout-canary/{__version__} (+https://github.com/jigar48/checkout-canary)"
RESULT_FILE = "result.json"
FAILURE_SCREENSHOT = "failure.png"
TRACE_FILE = "trace.zip"
SCREENSHOT_DIR = "screenshots"


def _short_error(exc: Exception) -> str:
    """First useful part of a Playwright error: no call log, one line, bounded length."""
    text = str(exc).split("Call log:")[0]
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= 300 else text[:297] + "..."


def _explain(step: object, exc: Exception, timeout_ms: int) -> str:
    """Plain-language failure message for the common timeout/assertion cases."""
    seconds = f"{timeout_ms / 1000:g}s"
    if isinstance(exc, AssertionError | PlaywrightTimeoutError):
        if isinstance(step, ExpectVisibleStep):
            return f"'{step.expect_visible}' was not visible after {seconds}"
        if isinstance(step, ExpectTextStep):
            args = step.expect_text
            return f"'{args.selector}' did not show the text '{args.text}' within {seconds}"
        if isinstance(step, ClickStep):
            return f"could not click '{step.click}' within {seconds} (not found or not clickable)"
        if isinstance(step, FillStep):
            selector = step.fill.selector
            return f"could not fill '{selector}' within {seconds} (not found or not editable)"
    return _short_error(exc)


def _execute(page: Page, step: object, journey: Journey, output_dir: Path) -> str | None:
    """Run one step. Raises on failure. Returns the screenshot file name for screenshot steps."""
    timeout = journey.timeout_ms
    if isinstance(step, GotoStep):
        url = urljoin(journey.base_url or "", step.goto)
        response = page.goto(url, timeout=timeout)
        if response is not None and response.status >= 400:
            raise AssertionError(f"page returned HTTP {response.status} for {url}")
    elif isinstance(step, ClickStep):
        page.locator(step.click).click(timeout=timeout)
    elif isinstance(step, FillStep):
        page.locator(step.fill.selector).fill(step.fill.value, timeout=timeout)
    elif isinstance(step, ExpectTextStep):
        locator = page.locator(step.expect_text.selector)
        expect(locator).to_contain_text(step.expect_text.text, timeout=timeout)
    elif isinstance(step, ExpectVisibleStep):
        expect(page.locator(step.expect_visible)).to_be_visible(timeout=timeout)
    elif isinstance(step, ScreenshotStep):
        directory = output_dir / SCREENSHOT_DIR
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{step.screenshot}.png"
        page.screenshot(path=directory / name)
        return f"{SCREENSHOT_DIR}/{name}"
    return None


def run_journey(journey: Journey, output_dir: Path) -> RunResult:
    """Run the journey headless in Chromium and write result.json (plus evidence on failure)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    run_start = time.perf_counter()
    steps: list[StepResult] = []
    evidence = Evidence()
    failed = False

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}
            )
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
            page = context.new_page()

            for index, step in enumerate(journey.steps, start=1):
                action, target = describe_step(step)
                if failed:
                    steps.append(
                        StepResult(index=index, action=action, target=target, status="skipped")
                    )
                    continue
                step_start = time.perf_counter()
                try:
                    screenshot = _execute(page, step, journey, output_dir)
                except Exception as exc:  # noqa: BLE001 - any step error is a journey failure
                    failed = True
                    status, error = "failed", _explain(step, exc, journey.timeout_ms)
                else:
                    status, error = "passed", None
                    if screenshot:
                        evidence.screenshots.append(screenshot)
                duration_ms = round((time.perf_counter() - step_start) * 1000)
                steps.append(
                    StepResult(
                        index=index,
                        action=action,
                        target=target,
                        status=status,
                        duration_ms=duration_ms,
                        error=error,
                    )
                )

            if failed:
                try:
                    page.screenshot(path=output_dir / FAILURE_SCREENSHOT)
                    evidence.failure_screenshot = FAILURE_SCREENSHOT
                except Exception:  # noqa: BLE001 - evidence is best effort
                    pass
                context.tracing.stop(path=output_dir / TRACE_FILE)
                evidence.trace = TRACE_FILE
            else:
                context.tracing.stop()
            context.close()
        finally:
            browser.close()

    result = build_result(
        journey=journey.name,
        base_url=journey.base_url,
        steps=steps,
        evidence=evidence,
        started_at=started_at,
        duration_ms=round((time.perf_counter() - run_start) * 1000),
    )
    (output_dir / RESULT_FILE).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return result
