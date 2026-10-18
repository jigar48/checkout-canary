"""Journey file format: loading and validation.

A journey is one YAML file with a name, an optional base_url and a list of steps. Each step is a
mapping with exactly one action key (goto, click, fill, expect_text, expect_visible, screenshot).
"""

import re
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    field_validator,
    model_validator,
)

ACTIONS = ("goto", "click", "fill", "expect_text", "expect_visible", "screenshot", "wait")
MIN_WAIT_MS = 100
MAX_WAIT_MS = 10_000
SCREENSHOT_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


class JourneyError(Exception):
    """The journey file could not be read or is invalid. The message is meant for humans."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FillArgs(_Strict):
    selector: str = Field(min_length=1)
    value: str


class ExpectTextArgs(_Strict):
    selector: str = Field(min_length=1)
    text: str = Field(min_length=1)


class GotoStep(_Strict):
    goto: str = Field(min_length=1)

    @field_validator("goto")
    @classmethod
    def _http_only(cls, value: str) -> str:
        scheme = urlparse(value).scheme
        if scheme not in ("", "http", "https"):
            raise ValueError(f"only http and https URLs are allowed, got '{scheme}:'")
        return value


class ClickStep(_Strict):
    click: str = Field(min_length=1)


class FillStep(_Strict):
    fill: FillArgs


class ExpectTextStep(_Strict):
    expect_text: ExpectTextArgs


class ExpectVisibleStep(_Strict):
    expect_visible: str = Field(min_length=1)


class ScreenshotStep(_Strict):
    screenshot: str = Field(min_length=1)

    @field_validator("screenshot")
    @classmethod
    def _safe_name(cls, value: str) -> str:
        if not SCREENSHOT_NAME.match(value):
            raise ValueError("use only letters, digits, '-' and '_' (no paths or extension)")
        return value


class WaitStep(_Strict):
    """Pause for a fixed time, for pages that need a moment after loading before they work."""

    wait: int = Field(ge=MIN_WAIT_MS, le=MAX_WAIT_MS, description="milliseconds")


def _action_of(step: Any) -> str | None:
    if isinstance(step, dict):
        keys = [key for key in step if key in ACTIONS]
        if len(keys) == 1 and len(step) == 1:
            return keys[0]
        return keys[0] if keys else None
    return getattr(step, "action", None)


Step = Annotated[
    Annotated[GotoStep, Tag("goto")]
    | Annotated[ClickStep, Tag("click")]
    | Annotated[FillStep, Tag("fill")]
    | Annotated[ExpectTextStep, Tag("expect_text")]
    | Annotated[ExpectVisibleStep, Tag("expect_visible")]
    | Annotated[ScreenshotStep, Tag("screenshot")]
    | Annotated[WaitStep, Tag("wait")],
    Discriminator(_action_of),
]


class Journey(_Strict):
    name: str = Field(min_length=1)
    base_url: str | None = None
    timeout_ms: int = Field(default=10_000, ge=100, le=120_000)
    steps: list[Step] = Field(min_length=1)

    @field_validator("steps", mode="before")
    @classmethod
    def _one_known_action_per_step(cls, steps: Any) -> Any:
        if not isinstance(steps, list):
            return steps
        for number, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                raise ValueError(f"step {number} must be a mapping like '- click: \"#buy\"'")
            known = [key for key in step if key in ACTIONS]
            unknown = [key for key in step if key not in ACTIONS]
            if unknown:
                raise ValueError(
                    f"step {number} has unknown action '{unknown[0]}'. "
                    f"Allowed actions: {', '.join(ACTIONS)}"
                )
            if len(known) != 1:
                raise ValueError(f"step {number} must contain exactly one action, got {len(known)}")
        return steps

    @field_validator("base_url")
    @classmethod
    def _base_url_is_http(cls, value: str | None) -> str | None:
        if value is not None and urlparse(value).scheme not in ("http", "https"):
            raise ValueError("must start with http:// or https://")
        return value

    @model_validator(mode="after")
    def _relative_goto_needs_base_url(self) -> "Journey":
        if self.base_url is None:
            for number, step in enumerate(self.steps, start=1):
                if isinstance(step, GotoStep) and not urlparse(step.goto).scheme:
                    raise ValueError(
                        f"step {number}: goto '{step.goto}' is relative, so base_url is required "
                        "(set base_url in the journey or pass --base-url)"
                    )
        return self


def describe_step(step: Any) -> tuple[str, str]:
    """Return (action, target) for display and results. Never includes fill values."""
    if isinstance(step, GotoStep):
        return "goto", step.goto
    if isinstance(step, ClickStep):
        return "click", step.click
    if isinstance(step, FillStep):
        return "fill", step.fill.selector
    if isinstance(step, ExpectTextStep):
        return "expect_text", f"{step.expect_text.selector} contains '{step.expect_text.text}'"
    if isinstance(step, ExpectVisibleStep):
        return "expect_visible", step.expect_visible
    if isinstance(step, ScreenshotStep):
        return "screenshot", step.screenshot
    if isinstance(step, WaitStep):
        return "wait", f"{step.wait} ms"
    raise TypeError(f"unsupported step type: {type(step).__name__}")


def _format_location(loc: tuple[int | str, ...]) -> str:
    parts: list[str] = []
    for position, item in enumerate(loc):
        if isinstance(item, int):
            parts.append(f"step {item + 1}")
        elif item == "steps" and position + 1 < len(loc) and isinstance(loc[position + 1], int):
            continue
        elif not parts or parts[-1] != item:
            parts.append(str(item))
    return " > ".join(parts) or "journey"


def format_validation_error(error: ValidationError) -> str:
    lines = []
    for item in error.errors():
        message = item["msg"].removeprefix("Value error, ")
        location = _format_location(item["loc"])
        if item["type"] == "extra_forbidden":
            message = "unknown field (check the spelling)"
        lines.append(f"  - {location}: {message}")
    return "\n".join(lines)


def load_journey(path: str | Path, base_url: str | None = None) -> Journey:
    """Read and validate a journey file. `base_url` overrides the one in the file."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise JourneyError(f"Cannot read journey file '{path}': {exc.strerror or exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise JourneyError(f"'{path}' is not valid YAML:\n{exc}") from exc
    if not isinstance(data, dict):
        raise JourneyError(
            f"'{path}' must contain one journey as a YAML mapping with 'name' and 'steps'"
        )
    if base_url is not None:
        data["base_url"] = base_url
    try:
        return Journey.model_validate(data)
    except ValidationError as exc:
        raise JourneyError(f"Invalid journey '{path}':\n{format_validation_error(exc)}") from exc
