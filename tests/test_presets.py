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


MAGENTO = REPO_ROOT / "presets" / "magento2.yml"


def test_magento2_preset_passes_on_working_fixture(tmp_path):
    code, result, out = run_preset(MAGENTO, FIXTURES_DIR / "magento2" / "ok", tmp_path)

    assert code == 0
    assert result["passed"] is True
    assert {s["status"] for s in result["steps"]} == {"passed"}
    assert (out / "screenshots" / "checkout.png").read_bytes().startswith(PNG_MAGIC)


def test_magento2_preset_fails_when_add_to_cart_is_broken(tmp_path):
    code, result, out = run_preset(MAGENTO, FIXTURES_DIR / "magento2" / "broken", tmp_path)

    assert code == 1
    failed = next(s for s in result["steps"] if s["status"] == "failed")
    assert failed["target"] == ".message-success"
    assert (out / "failure.png").read_bytes().startswith(PNG_MAGIC)
    assert (out / "trace.zip").exists()
