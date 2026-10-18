"""Run settings read from environment variables: User-Agent and one optional secret header.

The header value is a secret (for example a token that lets the monitor through a bot-protection
allow rule). It is never printed, never written to result files, and error messages here never
contain it.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from checkout_canary import __version__

USER_AGENT_VAR = "CHECKOUT_CANARY_USER_AGENT"
HEADER_NAME_VAR = "CHECKOUT_CANARY_HEADER_NAME"
HEADER_VALUE_VAR = "CHECKOUT_CANARY_HEADER_VALUE"

DEFAULT_USER_AGENT = f"checkout-canary/{__version__} (+https://github.com/jigar48/checkout-canary)"

_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_PRINTABLE_ASCII = re.compile(r"^[\x20-\x7e]+$")
# Headers the browser controls itself or that have their own setting.
_RESERVED = {
    "host",
    "content-length",
    "content-type",
    "cookie",
    "connection",
    "transfer-encoding",
    "user-agent",
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
    "origin",
    "referer",
}


class SettingsError(Exception):
    """An environment variable is invalid. The message never contains a header value."""


@dataclass(frozen=True)
class RunSettings:
    user_agent: str = DEFAULT_USER_AGENT
    header_name: str | None = None
    header_value: str | None = None

    @property
    def has_secret_header(self) -> bool:
        return self.header_name is not None and self.header_value is not None

    def secrets(self) -> list[str]:
        """Strings that must never appear in output."""
        return [self.header_value] if self.header_value else []


def settings_from_env(env: Mapping[str, str]) -> RunSettings:
    user_agent = env.get(USER_AGENT_VAR, "").strip() or DEFAULT_USER_AGENT
    if len(user_agent) > 300 or not _PRINTABLE_ASCII.match(user_agent):
        raise SettingsError(
            f"{USER_AGENT_VAR} must be 1-300 printable ASCII characters (no line breaks)."
        )

    name = env.get(HEADER_NAME_VAR, "").strip()
    value = env.get(HEADER_VALUE_VAR, "").strip()
    if not name and not value:
        return RunSettings(user_agent=user_agent)
    if not name or not value:
        missing = HEADER_NAME_VAR if not name else HEADER_VALUE_VAR
        raise SettingsError(f"{missing} is not set; set both header variables or neither.")
    if not _HEADER_NAME.match(name):
        raise SettingsError(f"{HEADER_NAME_VAR} may only contain letters, digits and '-'.")
    if name.lower() in _RESERVED:
        raise SettingsError(
            f"{HEADER_NAME_VAR} '{name}' is reserved; use a custom name such as X-Monitor-Token "
            f"(set the User-Agent with {USER_AGENT_VAR})."
        )
    if len(value) > 512 or not _PRINTABLE_ASCII.match(value):
        raise SettingsError(
            f"{HEADER_VALUE_VAR} must be 1-512 printable ASCII characters (no line breaks)."
        )
    return RunSettings(user_agent=user_agent, header_name=name, header_value=value)
