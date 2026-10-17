"""History, status page and the `status update` command."""

import json
from datetime import UTC, datetime
from pathlib import Path

from checkout_canary.cli import main
from checkout_canary.history import (
    KEEP_RUNS,
    SHOW_RUNS,
    History,
    HistoryEntry,
    load_history,
    record_run,
    save_history,
)
from checkout_canary.journey import load_journey
from checkout_canary.results import Evidence, StepResult, build_result
from checkout_canary.statuspage import render_status_page
from conftest import REPO_ROOT, SHOP_DIR, serve_directory

PNG = b"\x89PNG\r\n\x1a\n" + b"fake"


def make_result(minute: int, passed: bool, with_screenshot: bool = False):
    steps = [StepResult(index=1, action="goto", target="/", status="passed", duration_ms=10)]
    if not passed:
        steps.append(
            StepResult(
                index=2,
                action="click",
                target="#checkout-button",
                status="failed",
                duration_ms=3000,
                error="could not click '#checkout-button' within 3s <script>alert(1)</script>",
            )
        )
    evidence = Evidence(failure_screenshot="failure.png" if with_screenshot else None)
    return build_result(
        journey="Demo",
        base_url="http://x.test",
        steps=steps,
        evidence=evidence,
        started_at=f"2026-10-17T10:{minute:02d}:00+00:00",
        duration_ms=1234,
    )


def test_record_run_adds_entry_and_failure_detail(tmp_path):
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / "failure.png").write_bytes(PNG)
    data = tmp_path / "data"

    history = record_run(
        History(), make_result(5, False, True), data, result_dir, run_url="https://ci.test/1"
    )

    (entry,) = history.runs
    assert entry.id == "20261017T100500Z"
    assert entry.passed is False
    assert entry.detail.startswith("Stopped at step 2 of 2, while clicking #checkout-button")
    assert entry.run_url == "https://ci.test/1"
    assert (data / "screenshots" / entry.screenshot).read_bytes() == PNG


def test_history_is_trimmed_and_old_screenshots_removed(tmp_path):
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / "failure.png").write_bytes(PNG)
    data = tmp_path / "data"
    history = History()
    for minute in range(KEEP_RUNS + 3):
        result = make_result(0, False, True)
        result.started_at = (
            datetime(2026, 1, 1, tzinfo=UTC)
            .replace(hour=minute // 60, minute=minute % 60)
            .isoformat()
        )
        history = record_run(history, result, data, result_dir)

    assert len(history.runs) == KEEP_RUNS
    stored = sorted(p.name for p in (data / "screenshots").glob("*.png"))
    assert stored == sorted(e.screenshot for e in history.runs)


def test_same_timestamp_gets_unique_id(tmp_path):
    first = record_run(History(), make_result(1, True), tmp_path, tmp_path)
    second = record_run(first, make_result(1, True), tmp_path, tmp_path)
    assert [e.id for e in second.runs] == ["20261017T100100Z", "20261017T100100Z-2"]


def test_save_and_load_roundtrip(tmp_path):
    history = record_run(History(), make_result(1, True), tmp_path, tmp_path)
    save_history(history, tmp_path)
    assert load_history(tmp_path) == history
    assert load_history(tmp_path / "missing").runs == []


def entry(minute, passed, **kwargs):
    return HistoryEntry(
        id=f"id{minute}",
        started_at=f"2026-10-17T10:{minute:02d}:00+00:00",
        passed=passed,
        duration_ms=2000,
        **kwargs,
    )


def test_page_with_no_runs():
    page = render_status_page(History(), "My shop")
    assert "No checks yet" in page
    assert "<title>My shop</title>" in page


def test_page_green_when_last_run_passed():
    page = render_status_page(History(runs=[entry(1, False, detail="boom"), entry(2, True)]), "S")
    assert "All good: checkout is working" in page
    assert "NOT working" not in page
    assert "Passed 1 of the last 2 checks." in page


def test_page_red_with_screenshot_run_link_and_escaping():
    bad = entry(
        3,
        False,
        detail="<script>alert(1)</script>",
        screenshot="20261017T100300Z.png",
        run_url="https://github.com/o/r/actions/runs/9",
    )
    page = render_status_page(History(runs=[entry(1, True), bad]), "S", note="demo <b>")
    assert "Problem: checkout is NOT working" in page
    assert 'src="screenshots/20261017T100300Z.png"' in page
    assert "https://github.com/o/r/actions/runs/9" in page
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "demo &lt;b&gt;" in page


def test_page_ignores_non_http_run_links():
    page = render_status_page(
        History(runs=[entry(1, False, detail="x", run_url="javascript:x")]), "S"
    )
    assert "javascript:x" not in page


def test_page_shows_only_last_30_runs():
    runs = [entry(minute, True) for minute in range(40)]
    page = render_status_page(History(runs=runs), "S")
    assert f"Last {SHOW_RUNS} checks" in page
    assert page.count('<li class="ok"') == SHOW_RUNS


def test_status_update_command_writes_history_and_site(tmp_path, capsys):
    results = tmp_path / "results"
    results.mkdir()
    result = make_result(7, False, True)
    (results / "result.json").write_text(result.model_dump_json(), encoding="utf-8")
    (results / "failure.png").write_bytes(PNG)
    data, site = tmp_path / "data", tmp_path / "site"
    argv = [
        "status", "update", "--data-dir", str(data), "--site-dir", str(site),
        "--result", str(results / "result.json"), "--title", "Demo status",
    ]  # fmt: skip

    assert main(argv, env={"CHECKOUT_CANARY_RUN_URL": "https://ci.test/run/5"}) == 0

    assert "1 runs in history" in capsys.readouterr().out
    page = (site / "index.html").read_text(encoding="utf-8")
    assert "Problem: checkout is NOT working" in page
    assert "https://ci.test/run/5" in page
    assert list((site / "screenshots").glob("*.png"))
    saved = json.loads((data / "history.json").read_text(encoding="utf-8"))
    assert saved["runs"][0]["passed"] is False

    # Re-render only (no --result), as the workflow does on a deploy-only run.
    assert main(["status", "update", "--data-dir", str(data), "--site-dir", str(site)], env={}) == 0
    assert len(load_history(data).runs) == 1


def test_status_update_reports_unreadable_history(tmp_path, capsys):
    data = tmp_path / "data"
    data.mkdir()
    (data / "history.json").write_text("{not json", encoding="utf-8")
    code = main(["status", "update", "--data-dir", str(data), "--site-dir", str(tmp_path / "s")])
    assert code == 2
    assert "Cannot read history file" in capsys.readouterr().err


def test_live_demo_journey_is_valid_and_passes_under_a_sub_path(tmp_path):
    """The live demo journey uses relative paths: GitHub Pages serves the shop under /demo-shop/."""
    journey_file = REPO_ROOT / "journeys" / "demo-shop.yml"
    assert load_journey(journey_file).base_url.endswith("/demo-shop/")

    out = tmp_path / "out"
    for base in serve_directory(SHOP_DIR):
        argv = ["run", str(journey_file), "--base-url", f"{base}/ok/", "--output-dir", str(out)]
        code = main(argv, env={})

    assert code == 0
    assert json.loads(Path(out / "result.json").read_text(encoding="utf-8"))["passed"] is True
