"""Presets: every file in presets/ must load, and each is exercised against its local fixture."""

import json
from pathlib import Path

import pytest

from checkout_canary.cli import main
from checkout_canary.journey import load_journey
from conftest import FIXTURES_DIR, REPO_ROOT, serve_directory

PRESETS = sorted((REPO_ROOT / "presets").glob("*.yml"))
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_there_are_presets():
    assert PRESETS


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.name)
def test_preset_is_valid_and_labelled_experimental(preset):
    journey = load_journey(preset)
    assert "experimental" in journey.name.lower()
    assert "EXPERIMENTAL" in preset.read_text(encoding="utf-8")
    assert journey.base_url and "example" in journey.base_url  # placeholder, not a real store


def fast_copy(preset: Path, tmp_path: Path) -> Path:
    """Copy a preset with a short timeout so failing runs finish quickly."""
    text = preset.read_text(encoding="utf-8")
    assert "timeout_ms: 15000" in text
    copy = tmp_path / preset.name
    copy.write_text(text.replace("timeout_ms: 15000", "timeout_ms: 1500"), encoding="utf-8")
    return copy


def run_preset(preset, fixture_dir, tmp_path):
    out = tmp_path / "out"
    journey = fast_copy(preset, tmp_path)
    for base_url in serve_directory(fixture_dir):
        code = main(["run", str(journey), "--base-url", base_url, "--output-dir", str(out)], env={})
    return code, json.loads((out / "result.json").read_text(encoding="utf-8")), out


# preset file -> (fixture directory, selector expected to fail in the broken fixture)
FIXTURE_CASES = {
    "magento2.yml": ("magento2", ".message-success"),
    "woocommerce.yml": ("woocommerce", "a.checkout-button"),
}


def test_every_preset_has_a_fixture_case():
    assert {p.name for p in PRESETS} == set(FIXTURE_CASES)


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.name)
def test_preset_never_places_an_order(preset):
    """Presets must stop before payment: no step may touch place-order or payment fields."""
    text = preset.read_text(encoding="utf-8").lower()
    steps = text.split("steps:", 1)[1]
    for forbidden in ("place_order", "place-order", "card", "cvv", "payment_method"):
        assert forbidden not in steps


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.name)
def test_preset_passes_on_working_fixture(preset, tmp_path):
    fixture, _ = FIXTURE_CASES[preset.name]
    code, result, out = run_preset(preset, FIXTURES_DIR / fixture / "ok", tmp_path)

    assert code == 0
    assert result["passed"] is True
    assert {s["status"] for s in result["steps"]} == {"passed"}
    assert (out / "screenshots" / "checkout.png").read_bytes().startswith(PNG_MAGIC)


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.name)
def test_preset_fails_with_evidence_on_broken_fixture(preset, tmp_path):
    fixture, failing_target = FIXTURE_CASES[preset.name]
    code, result, out = run_preset(preset, FIXTURES_DIR / fixture / "broken", tmp_path)

    assert code == 1
    failed = next(s for s in result["steps"] if s["status"] == "failed")
    assert failed["target"] == failing_target
    assert (out / "failure.png").read_bytes().startswith(PNG_MAGIC)
    assert (out / "trace.zip").exists()
