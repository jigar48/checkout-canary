"""The `wait` step: limits, plain-language text, and a page that is ready only after a delay."""

import json
from pathlib import Path

import pytest

from checkout_canary.alerts import FailureAlert
from checkout_canary.cli import main
from checkout_canary.journey import JourneyError, WaitStep, describe_step, load_journey
from checkout_canary.results import Evidence, StepResult, build_result, plain_description
from conftest import serve_directory

# The button only works after 1.2 s, like a page whose JavaScript is still starting up.
SLOW_PAGE = """<!doctype html><html><body>
<button id="go">Go</button><p id="out">waiting</p>
<script>
let ready = false;
setTimeout(() => { ready = true; }, 1200);
document.getElementById("go").addEventListener("click", () => {
  document.getElementById("out").textContent = ready ? "done" : "not ready";
});
</script></body></html>
"""

HEAD = "name: S\nbase_url: http://x.test\nsteps:\n  - goto: /\n"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "j.yml"
    path.write_text(text, encoding="utf-8")
    return path


def journey_with(tmp_path: Path, wait_line: str) -> Path:
    return write(tmp_path, f"{HEAD}  - {wait_line}\n")


def test_wait_step_parses(tmp_path):
    step = load_journey(journey_with(tmp_path, "wait: 3000")).steps[1]
    assert isinstance(step, WaitStep)
    assert step.wait == 3000
    assert describe_step(step) == ("wait", "3000 ms")


@pytest.mark.parametrize("value", ["99", "10001", "0", "-5", "1.5", "abc", "true"])
def test_wait_rejects_out_of_range_or_non_integer(tmp_path, value):
    with pytest.raises(JourneyError) as info:
        load_journey(journey_with(tmp_path, f"wait: {value}"))
    assert "step 2 > wait" in str(info.value)


@pytest.mark.parametrize("value", ["100", "10000"])
def test_wait_accepts_the_limits(tmp_path, value):
    assert load_journey(journey_with(tmp_path, f"wait: {value}")).steps[1].wait == int(value)


def test_wait_with_another_action_in_one_step_is_rejected(tmp_path):
    path = write(tmp_path, f"{HEAD}  - wait: 200\n    click: a\n")
    with pytest.raises(JourneyError, match="exactly one action"):
        load_journey(path)


def test_plain_language_and_alert_text():
    assert plain_description("wait", "3000 ms") == "waiting 3000 ms"
    steps = [
        StepResult(index=1, action="wait", target="3000 ms", status="failed", error="interrupted")
    ]
    result = build_result(
        journey="J",
        base_url=None,
        steps=steps,
        evidence=Evidence(),
        started_at="2026-01-01T00:00:00+00:00",
        duration_ms=1,
    )
    assert "while waiting 3000 ms" in FailureAlert.from_result(result).text()


def run_slow_page(tmp_path: Path, steps: str) -> tuple[int, dict]:
    site = tmp_path / "site"
    site.mkdir()
    (site / "page.html").write_text(SLOW_PAGE, encoding="utf-8")
    journey = write(
        tmp_path, f"name: Slow page\ntimeout_ms: 800\nsteps:\n  - goto: /page.html\n{steps}"
    )
    out = tmp_path / "out"
    for base in serve_directory(site):
        code = main(["run", str(journey), "--base-url", base, "--output-dir", str(out)], env={})
    return code, json.loads((out / "result.json").read_text(encoding="utf-8"))


def test_without_wait_the_slow_page_fails(tmp_path):
    code, result = run_slow_page(
        tmp_path, "  - click: '#go'\n  - expect_text: {selector: '#out', text: done}\n"
    )
    assert code == 1
    assert result["steps"][2]["status"] == "failed"


def test_with_wait_the_slow_page_passes_and_wait_is_timed(tmp_path):
    code, result = run_slow_page(
        tmp_path,
        "  - wait: 1500\n  - click: '#go'\n  - expect_text: {selector: '#out', text: done}\n",
    )
    assert code == 0
    wait_step = result["steps"][1]
    assert (wait_step["action"], wait_step["target"]) == ("wait", "1500 ms")
    assert wait_step["status"] == "passed"
    assert wait_step["duration_ms"] >= 1400
