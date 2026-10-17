"""Result model and the plain-language summary written to result.json."""

from typing import Literal

from pydantic import BaseModel, Field


class StepResult(BaseModel):
    index: int
    action: str
    target: str
    status: Literal["passed", "failed", "skipped"]
    duration_ms: int = 0
    error: str | None = None


class Evidence(BaseModel):
    """File names relative to the output directory."""

    failure_screenshot: str | None = None
    trace: str | None = None
    screenshots: list[str] = Field(default_factory=list)


class RunResult(BaseModel):
    journey: str
    passed: bool
    summary: str
    started_at: str
    duration_ms: int
    base_url: str | None
    steps: list[StepResult]
    evidence: Evidence


_PLAIN = {
    "goto": "opening {target}",
    "click": "clicking {target}",
    "fill": "typing into {target}",
    "expect_text": "checking that {target}",
    "expect_visible": "waiting for {target} to appear",
    "screenshot": "taking the screenshot '{target}'",
}


def plain_description(action: str, target: str) -> str:
    """Owner-readable description of a step, e.g. 'clicking #checkout-button'."""
    return _PLAIN.get(action, "{action} {target}").format(action=action, target=target)


def build_summary(journey: str, steps: list[StepResult]) -> str:
    failed = next((step for step in steps if step.status == "failed"), None)
    if failed is None:
        return f"PASS: '{journey}' completed all {len(steps)} steps."
    detail = f": {failed.error}" if failed.error else ""
    return (
        f"FAIL: '{journey}' stopped at step {failed.index} of {len(steps)} "
        f"({failed.action} {failed.target}){detail}"
    )


def build_result(
    *,
    journey: str,
    base_url: str | None,
    steps: list[StepResult],
    evidence: Evidence,
    started_at: str,
    duration_ms: int,
) -> RunResult:
    return RunResult(
        journey=journey,
        passed=all(step.status == "passed" for step in steps),
        summary=build_summary(journey, steps),
        started_at=started_at,
        duration_ms=duration_ms,
        base_url=base_url,
        steps=steps,
        evidence=evidence,
    )
