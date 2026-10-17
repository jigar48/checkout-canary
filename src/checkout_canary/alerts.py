"""Failure alerts.

`Notifier` is the interface every alert channel implements. Telegram is the only channel today;
Slack or email can be added later by implementing `Notifier` and registering it in
`notifiers_from_env`.

Rules: alerts are best effort, never change the exit code, and never contain secrets or fill values.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from checkout_canary import __version__
from checkout_canary.results import RunResult, plain_description

TELEGRAM_TOKEN_VAR = "CHECKOUT_CANARY_TELEGRAM_TOKEN"
TELEGRAM_CHAT_VAR = "CHECKOUT_CANARY_TELEGRAM_CHAT_ID"
TELEGRAM_API_BASE_VAR = "CHECKOUT_CANARY_TELEGRAM_API_BASE"  # for tests; defaults to Telegram
RUN_URL_VAR = "CHECKOUT_CANARY_RUN_URL"
DEFAULT_TELEGRAM_API = "https://api.telegram.org"
MAX_REASON_CHARS = 500


class AlertError(Exception):
    """An alert could not be delivered. The message never contains secrets."""


@dataclass(frozen=True)
class FailureAlert:
    journey: str
    step_index: int
    step_total: int
    what: str
    reason: str
    time_utc: str
    run_url: str | None = None

    @classmethod
    def from_result(cls, result: RunResult, run_url: str | None = None) -> "FailureAlert":
        failed = next(step for step in result.steps if step.status == "failed")
        reason = failed.error or "no further detail"
        if len(reason) > MAX_REASON_CHARS:
            reason = reason[: MAX_REASON_CHARS - 3] + "..."
        return cls(
            journey=result.journey,
            step_index=failed.index,
            step_total=len(result.steps),
            what=plain_description(failed.action, failed.target),
            reason=reason,
            time_utc=result.started_at,
            run_url=run_url,
        )

    def text(self) -> str:
        lines = [
            f"Checkout check FAILED: {self.journey}",
            f"It stopped at step {self.step_index} of {self.step_total}, while {self.what}.",
            f"Reason: {self.reason}",
            f"Time (UTC): {self.time_utc}",
        ]
        if self.run_url:
            lines.append(f"Run details: {self.run_url}")
        return "\n".join(lines)


class Notifier(Protocol):
    name: str

    def send(self, alert: FailureAlert) -> None:
        """Deliver the alert or raise AlertError."""


def redact(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


class TelegramNotifier:
    """Sends a text message with the Telegram Bot API `sendMessage` method."""

    name = "telegram"

    def __init__(
        self,
        token: str,
        chat_id: str,
        api_base: str = DEFAULT_TELEGRAM_API,
        timeout: float = 10.0,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout

    def send(self, alert: FailureAlert) -> None:
        payload = {
            "chat_id": self._chat_id,
            "text": alert.text(),
            "link_preview_options": {"is_disabled": True},
        }
        request = urllib.request.Request(
            f"{self._api_base}/bot{self._token}/sendMessage",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"checkout-canary/{__version__}",
            },
            method="POST",
        )
        secrets = (self._token, self._chat_id)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            description = ""
            try:
                description = json.load(exc).get("description", "")
            except Exception:  # noqa: BLE001 - error body is optional detail
                pass
            message = f"Telegram returned HTTP {exc.code}"
            if description:
                message += f" ({description})"
            raise AlertError(redact(message, secrets)) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            reason = getattr(exc, "reason", exc)
            raise AlertError(redact(f"Telegram request failed: {reason}", secrets)) from None
        if not (isinstance(body, dict) and body.get("ok") is True):
            raise AlertError("Telegram did not accept the message")


def notifiers_from_env(env: Mapping[str, str]) -> tuple[list[Notifier], list[str]]:
    """Build notifiers from environment variables. Returns (notifiers, human-readable notes)."""
    notifiers: list[Notifier] = []
    notes: list[str] = []
    token = env.get(TELEGRAM_TOKEN_VAR, "").strip()
    chat_id = env.get(TELEGRAM_CHAT_VAR, "").strip()
    if token and chat_id:
        api_base = env.get(TELEGRAM_API_BASE_VAR, "").strip() or DEFAULT_TELEGRAM_API
        notifiers.append(TelegramNotifier(token, chat_id, api_base))
    elif token or chat_id:
        missing = TELEGRAM_CHAT_VAR if token else TELEGRAM_TOKEN_VAR
        notes.append(f"Telegram alert is off: {missing} is not set.")
    if not notifiers and not notes:
        notes.append(
            "Alerts are off (set "
            f"{TELEGRAM_TOKEN_VAR} and {TELEGRAM_CHAT_VAR} to enable Telegram alerts)."
        )
    return notifiers, notes


def run_url_from_env(env: Mapping[str, str]) -> str | None:
    """Link to the CI run, if there is one (explicit override, else GitHub Actions variables)."""
    explicit = env.get(RUN_URL_VAR, "").strip()
    if explicit:
        return explicit
    server = env.get("GITHUB_SERVER_URL", "").strip()
    repository = env.get("GITHUB_REPOSITORY", "").strip()
    run_id = env.get("GITHUB_RUN_ID", "").strip()
    if server and repository and run_id:
        return f"{server}/{repository}/actions/runs/{run_id}"
    return None


def send_alerts(notifiers: Sequence[Notifier], alert: FailureAlert) -> list[str]:
    """Send to every notifier. Never raises; returns one status line per notifier."""
    lines = []
    for notifier in notifiers:
        try:
            notifier.send(alert)
        except Exception as exc:  # noqa: BLE001 - an alert problem must not affect the run
            lines.append(f"Alert via {notifier.name} FAILED to send: {exc}")
        else:
            lines.append(f"Alert sent via {notifier.name}.")
    return lines
