"""Integration tests: real CLI and Chromium against the local fixture shop (no internet)."""

import json
import zipfile

from checkout_canary.cli import main
from conftest import EXAMPLE_JOURNEY, SEEN_USER_AGENTS

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def run(journey, base_url, out):
    return main(["run", str(journey), "--base-url", base_url, "--output-dir", str(out)])


def read_result(out):
    return json.loads((out / "result.json").read_text(encoding="utf-8"))


def test_working_shop_passes(working_shop_url, tmp_path, capsys):
    code = run(EXAMPLE_JOURNEY, working_shop_url, tmp_path)

    assert code == 0
    result = read_result(tmp_path)
    assert result["passed"] is True
    assert len(result["steps"]) == 12
    assert {s["status"] for s in result["steps"]} == {"passed"}
    assert all(s["duration_ms"] >= 0 for s in result["steps"])
    assert result["evidence"]["failure_screenshot"] is None
    assert not (tmp_path / "failure.png").exists()
    assert not (tmp_path / "trace.zip").exists()
    assert (tmp_path / "screenshots" / "cart.png").read_bytes().startswith(PNG_MAGIC)
    assert "PASS: 'Demo shop checkout' completed all 12 steps." in capsys.readouterr().out
    assert SEEN_USER_AGENTS
    assert all(ua.startswith("checkout-canary/") for ua in SEEN_USER_AGENTS)


def test_broken_shop_fails_with_evidence(broken_shop_url, tmp_path, capsys):
    code = run(EXAMPLE_JOURNEY, broken_shop_url, tmp_path)

    assert code == 1
    result = read_result(tmp_path)
    assert result["passed"] is False
    statuses = [s["status"] for s in result["steps"]]
    assert statuses == ["passed"] * 7 + ["failed"] + ["skipped"] * 4
    failed = result["steps"][7]
    assert failed["action"] == "expect_visible"
    assert "#checkout-button" in failed["error"]
    assert (tmp_path / "failure.png").read_bytes().startswith(PNG_MAGIC)
    with zipfile.ZipFile(tmp_path / "trace.zip") as trace:
        assert trace.testzip() is None
    assert result["evidence"]["trace"] == "trace.zip"
    assert "stopped at step 8 of 12" in capsys.readouterr().out


def test_invalid_journey_exits_2_without_launching_browser(tmp_path, capsys):
    bad = tmp_path / "bad.yml"
    bad.write_text("name: S\nsteps:\n  - clik: a\n", encoding="utf-8")

    code = main(["run", str(bad), "--output-dir", str(tmp_path / "out")])

    assert code == 2
    assert "unknown action 'clik'" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_http_error_page_fails_goto(working_shop_url, tmp_path):
    journey = tmp_path / "j.yml"
    journey.write_text("name: S\nsteps:\n  - goto: /does-not-exist.html\n", encoding="utf-8")

    code = run(journey, working_shop_url, tmp_path / "out")

    assert code == 1
    assert "HTTP 404" in read_result(tmp_path / "out")["steps"][0]["error"]
