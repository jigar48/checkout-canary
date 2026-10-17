"""Run history kept between scheduled runs (a small JSON file plus failure screenshots)."""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from checkout_canary.results import RunResult, plain_description

HISTORY_FILE = "history.json"
SCREENSHOT_DIR = "screenshots"
KEEP_RUNS = 90  # stored; the status page shows the latest SHOW_RUNS
SHOW_RUNS = 30
_SAFE_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z(-[0-9]+)?$")


class HistoryError(Exception):
    """The history file exists but cannot be used."""


class HistoryEntry(BaseModel):
    id: str
    started_at: str
    passed: bool
    duration_ms: int
    detail: str | None = None
    run_url: str | None = None
    screenshot: str | None = None  # file name inside the screenshots directory


class History(BaseModel):
    runs: list[HistoryEntry] = Field(default_factory=list)


def load_history(data_dir: Path) -> History:
    path = data_dir / HISTORY_FILE
    if not path.exists():
        return History()
    try:
        return History.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise HistoryError(f"Cannot read history file '{path}': {exc}") from exc


def entry_id(started_at: str) -> str:
    """Stable, file-name-safe id such as 20261017T153610Z."""
    moment = datetime.fromisoformat(started_at)
    return moment.strftime("%Y%m%dT%H%M%SZ")


def failure_detail(result: RunResult) -> str | None:
    failed = next((step for step in result.steps if step.status == "failed"), None)
    if failed is None:
        return None
    what = plain_description(failed.action, failed.target)
    reason = f": {failed.error}" if failed.error else ""
    return f"Stopped at step {failed.index} of {len(result.steps)}, while {what}{reason}"


def record_run(
    history: History,
    result: RunResult,
    data_dir: Path,
    result_dir: Path,
    run_url: str | None = None,
) -> History:
    """Add a run to the history, store its failure screenshot, and trim old entries."""
    run_id = entry_id(result.started_at)
    existing = {entry.id for entry in history.runs}
    if run_id in existing:
        suffix = 2
        while f"{run_id}-{suffix}" in existing:
            suffix += 1
        run_id = f"{run_id}-{suffix}"

    screenshot = None
    source = (
        result_dir / result.evidence.failure_screenshot
        if result.evidence.failure_screenshot
        else None
    )
    if source is not None and source.is_file():
        (data_dir / SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)
        screenshot = f"{run_id}.png"
        shutil.copyfile(source, data_dir / SCREENSHOT_DIR / screenshot)

    entry = HistoryEntry(
        id=run_id,
        started_at=result.started_at,
        passed=result.passed,
        duration_ms=result.duration_ms,
        detail=failure_detail(result),
        run_url=run_url,
        screenshot=screenshot,
    )
    runs = (history.runs + [entry])[-KEEP_RUNS:]
    kept = History(runs=runs)
    prune_screenshots(kept, data_dir)
    return kept


def prune_screenshots(history: History, data_dir: Path) -> None:
    """Remove stored screenshots that no history entry refers to (only files this tool names)."""
    directory = data_dir / SCREENSHOT_DIR
    if not directory.is_dir():
        return
    wanted = {entry.screenshot for entry in history.runs if entry.screenshot}
    for path in directory.glob("*.png"):
        if _SAFE_ID.match(path.stem) and path.name not in wanted:
            path.unlink()


def save_history(history: History, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / HISTORY_FILE).write_text(history.model_dump_json(indent=2) + "\n", encoding="utf-8")
