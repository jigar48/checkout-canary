from pathlib import Path

import pytest

from checkout_canary.journey import (
    ClickStep,
    ExpectTextStep,
    FillStep,
    GotoStep,
    JourneyError,
    describe_step,
    load_journey,
)

EXAMPLE = Path(__file__).parent.parent / "examples" / "demo-shop.yml"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "journey.yml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_journey_parses_every_action(tmp_path):
    path = write(
        tmp_path,
        """
name: Shop
base_url: http://localhost:8000
steps:
  - goto: /
  - click: "#buy"
  - fill: {selector: "#email", value: a@example.com}
  - expect_text: {selector: h1, text: Cart}
  - expect_visible: "#checkout"
  - screenshot: cart
""",
    )
    journey = load_journey(path)
    assert journey.timeout_ms == 10_000
    assert [type(s) for s in journey.steps[:4]] == [GotoStep, ClickStep, FillStep, ExpectTextStep]
    assert len(journey.steps) == 6


def test_example_journey_is_valid():
    assert load_journey(EXAMPLE).name == "Demo shop checkout"


def test_base_url_override(tmp_path):
    path = write(tmp_path, "name: S\nbase_url: http://a.test\nsteps:\n  - goto: /\n")
    assert load_journey(path, base_url="http://b.test").base_url == "http://b.test"


def test_unknown_action_is_reported_with_allowed_list(tmp_path):
    path = write(tmp_path, "name: S\nsteps:\n  - clik: '#x'\n")
    with pytest.raises(JourneyError) as info:
        load_journey(path)
    message = str(info.value)
    assert "step 1 has unknown action 'clik'" in message
    assert "expect_visible" in message


def test_step_with_two_actions_is_rejected(tmp_path):
    path = write(tmp_path, "name: S\nsteps:\n  - click: a\n    goto: b\n")
    with pytest.raises(JourneyError, match="exactly one action"):
        load_journey(path)


def test_missing_field_points_at_step_and_field(tmp_path):
    path = write(tmp_path, "name: S\nsteps:\n  - fill: {selector: '#e'}\n")
    with pytest.raises(JourneyError, match=r"step 1 > fill > value: Field required"):
        load_journey(path)


def test_misspelled_top_level_field(tmp_path):
    path = write(tmp_path, "name: S\nbase_urll: http://x.test\nsteps:\n  - goto: http://x.test\n")
    with pytest.raises(JourneyError, match="base_urll: unknown field"):
        load_journey(path)


def test_relative_goto_requires_base_url(tmp_path):
    path = write(tmp_path, "name: S\nsteps:\n  - goto: /cart\n")
    with pytest.raises(JourneyError, match="relative, so base_url is required"):
        load_journey(path)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)"])
def test_goto_rejects_non_http_schemes(tmp_path, url):
    path = write(tmp_path, f"name: S\nsteps:\n  - goto: '{url}'\n")
    with pytest.raises(JourneyError, match="only http and https"):
        load_journey(path)


def test_screenshot_name_cannot_escape_output_dir(tmp_path):
    path = write(tmp_path, "name: S\nsteps:\n  - screenshot: ../evil\n")
    with pytest.raises(JourneyError, match="letters, digits"):
        load_journey(path)


def test_empty_steps_rejected(tmp_path):
    path = write(tmp_path, "name: S\nsteps: []\n")
    with pytest.raises(JourneyError, match="at least 1 item"):
        load_journey(path)


def test_invalid_yaml_and_wrong_shape(tmp_path):
    with pytest.raises(JourneyError, match="not valid YAML"):
        load_journey(write(tmp_path, "name: [unclosed\n"))
    with pytest.raises(JourneyError, match="YAML mapping"):
        load_journey(write(tmp_path, "- just\n- a list\n"))


def test_missing_file(tmp_path):
    with pytest.raises(JourneyError, match="Cannot read journey file"):
        load_journey(tmp_path / "nope.yml")


def test_describe_step_never_includes_fill_value(tmp_path):
    path = write(
        tmp_path,
        "name: S\nbase_url: http://x.test\nsteps:\n  - fill: {selector: '#pw', value: hunter2}\n",
    )
    assert describe_step(load_journey(path).steps[0]) == ("fill", "#pw")
