from checkout_canary.results import Evidence, StepResult, build_result, build_summary


def step(index, status, error=None):
    return StepResult(
        index=index, action="click", target="#x", status=status, duration_ms=5, error=error
    )


def make_result(steps, evidence=None, base_url="http://x.test"):
    return build_result(
        journey="Shop",
        base_url=base_url,
        steps=steps,
        evidence=evidence or Evidence(),
        started_at="2026-01-01T00:00:00+00:00",
        duration_ms=10,
    )


def test_all_passed():
    result = make_result([step(1, "passed"), step(2, "passed")])
    assert result.passed is True
    assert result.summary == "PASS: 'Shop' completed all 2 steps."


def test_failure_summary_names_the_step_and_reason():
    steps = [step(1, "passed"), step(2, "failed", "button missing"), step(3, "skipped")]
    summary = build_summary("Shop", steps)
    assert summary.startswith("FAIL: 'Shop' stopped at step 2 of 3 (click #x)")
    assert "button missing" in summary


def test_failed_result_is_not_passed_and_serialises_to_json():
    evidence = Evidence(failure_screenshot="failure.png", trace="trace.zip")
    result = make_result([step(1, "failed", "boom"), step(2, "skipped")], evidence, base_url=None)
    assert result.passed is False
    payload = result.model_dump(mode="json")
    assert payload["evidence"]["trace"] == "trace.zip"
    assert [s["status"] for s in payload["steps"]] == ["failed", "skipped"]
