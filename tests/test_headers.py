"""User-Agent and secret-header settings. Fixtures only: no real site is contacted."""

import functools
import http.server
import json
import threading
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from checkout_canary.cli import main
from checkout_canary.runner import _redact
from checkout_canary.settings import (
    DEFAULT_USER_AGENT,
    SettingsError,
    settings_from_env,
)
from conftest import EXAMPLE_JOURNEY, SHOP_DIR

SECRET = "tok_S3cr3t-Value_0123456789"
NAME = "X-Monitor-Token"
ENV = {"CHECKOUT_CANARY_HEADER_NAME": NAME, "CHECKOUT_CANARY_HEADER_VALUE": SECRET}


# ---------- settings parsing ----------


def test_defaults_without_env():
    settings = settings_from_env({})
    assert settings.user_agent == DEFAULT_USER_AGENT
    assert settings.has_secret_header is False
    assert settings.secrets() == []


def test_custom_user_agent():
    settings = settings_from_env(
        {"CHECKOUT_CANARY_USER_AGENT": "checkout-canary (Krisvik monitoring)"}
    )
    assert settings.user_agent == "checkout-canary (Krisvik monitoring)"


def test_blank_user_agent_falls_back_to_default():
    assert settings_from_env({"CHECKOUT_CANARY_USER_AGENT": "  "}).user_agent == DEFAULT_USER_AGENT


@pytest.mark.parametrize("bad", ["line\nbreak", "x" * 301, "café"])
def test_invalid_user_agent(bad):
    with pytest.raises(SettingsError, match="CHECKOUT_CANARY_USER_AGENT"):
        settings_from_env({"CHECKOUT_CANARY_USER_AGENT": bad})


def test_header_settings_parsed():
    settings = settings_from_env(ENV)
    assert (settings.header_name, settings.header_value) == (NAME, SECRET)
    assert settings.secrets() == [SECRET]


@pytest.mark.parametrize(
    "env",
    [
        {"CHECKOUT_CANARY_HEADER_NAME": NAME},
        {"CHECKOUT_CANARY_HEADER_VALUE": SECRET},
        {"CHECKOUT_CANARY_HEADER_NAME": "Bad Name", "CHECKOUT_CANARY_HEADER_VALUE": SECRET},
        {"CHECKOUT_CANARY_HEADER_NAME": "Cookie", "CHECKOUT_CANARY_HEADER_VALUE": SECRET},
        {"CHECKOUT_CANARY_HEADER_NAME": "user-agent", "CHECKOUT_CANARY_HEADER_VALUE": SECRET},
        {"CHECKOUT_CANARY_HEADER_NAME": NAME, "CHECKOUT_CANARY_HEADER_VALUE": "a\r\nb: c"},
        {"CHECKOUT_CANARY_HEADER_NAME": NAME, "CHECKOUT_CANARY_HEADER_VALUE": "x" * 513},
    ],
)
def test_invalid_header_settings_never_echo_the_value(env):
    with pytest.raises(SettingsError) as info:
        settings_from_env(env)
    value = env.get("CHECKOUT_CANARY_HEADER_VALUE", "")
    assert value == "" or value not in str(info.value)


def test_redact_helper():
    assert _redact(f"failed with {SECRET} inside", [SECRET]) == "failed with [redacted] inside"


# ---------- local servers ----------


def lower(headers) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


@dataclass
class Gate:
    base_url: str
    requests: list[dict] = field(default_factory=list)


def _start(handler_cls) -> tuple[http.server.ThreadingHTTPServer, threading.Thread]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.fixture
def other_origin() -> Iterator[Gate]:
    """A second origin (different port) that records everything it receives."""
    gate = Gate(base_url="")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            gate.requests.append({"path": self.path, "headers": lower(self.headers)})
            body = b"<h1>other origin</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server, thread = _start(Handler)
    gate.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield gate
    server.shutdown()
    server.server_close()
    thread.join()


def make_gated_shop(variant: str, other_url: str) -> Iterator[Gate]:
    """The fixture shop behind a gate: 403 unless X-Monitor-Token carries the secret."""
    gate = Gate(base_url="")
    directory = str(SHOP_DIR / variant)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            gate.requests.append({"path": self.path, "headers": lower(self.headers)})
            if self.headers.get(NAME) != SECRET:
                body = b"<h1>Performing security verification</h1>"
                self.send_response(403)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/go-away.html":
                self.send_response(302)
                self.send_header("Location", f"{other_url}/landing")
                self.end_headers()
                return
            if self.path == "/set-cookie.html":
                body = b"<h1>cookie set</h1>"
                self.send_response(200)
                self.send_header("Set-Cookie", "cart=abc123; Path=/")
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/read-cookie.html":
                body = f"<h1>cookie={self.headers.get('Cookie')}</h1>".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    handler = functools.partial(Handler, directory=directory)
    server, thread = _start(handler)
    gate.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield gate
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def gated_ok(other_origin) -> Iterator[Gate]:
    yield from make_gated_shop("ok", other_origin.base_url)


@pytest.fixture
def gated_broken(other_origin) -> Iterator[Gate]:
    yield from make_gated_shop("broken", other_origin.base_url)


def run(journey: Path, base_url: str, out: Path, env: dict[str, str]) -> int:
    argv = ["run", str(journey), "--base-url", base_url, "--output-dir", str(out)]
    return main(argv, env=env)


def write_journey(tmp_path: Path, steps: str) -> Path:
    path = tmp_path / "j.yml"
    path.write_text(f"name: Gate test\ntimeout_ms: 1500\nsteps:\n{steps}", encoding="utf-8")
    return path


# ---------- behaviour ----------


def test_without_header_the_gate_blocks(gated_ok, tmp_path):
    assert run(EXAMPLE_JOURNEY, gated_ok.base_url, tmp_path, {}) == 1
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert "HTTP 403" in result["steps"][0]["error"]


def test_with_header_the_journey_passes_and_header_is_on_every_request(
    gated_ok, other_origin, tmp_path, capsys
):
    assert run(EXAMPLE_JOURNEY, gated_ok.base_url, tmp_path, ENV) == 0

    assert gated_ok.requests
    assert all(r["headers"].get(NAME.lower()) == SECRET for r in gated_ok.requests)
    assert all(r["headers"]["user-agent"].startswith("checkout-canary/") for r in gated_ok.requests)
    output = capsys.readouterr().out
    assert f"Extra request header '{NAME}' is enabled (value hidden)." in output
    assert SECRET not in output


def test_custom_user_agent_is_sent(gated_ok, tmp_path):
    env = {**ENV, "CHECKOUT_CANARY_USER_AGENT": "checkout-canary (Krisvik monitoring)"}
    assert run(EXAMPLE_JOURNEY, gated_ok.base_url, tmp_path, env) == 0
    assert {r["headers"]["user-agent"] for r in gated_ok.requests} == {
        "checkout-canary (Krisvik monitoring)"
    }


def test_custom_user_agent_without_header(working_shop_url, tmp_path):
    from conftest import SEEN_USER_AGENTS

    env = {"CHECKOUT_CANARY_USER_AGENT": "checkout-canary (Krisvik monitoring)"}
    assert run(EXAMPLE_JOURNEY, working_shop_url, tmp_path, env) == 0
    assert set(SEEN_USER_AGENTS) == {"checkout-canary (Krisvik monitoring)"}


def test_invalid_settings_exit_2_without_running(working_shop_url, tmp_path, capsys):
    env = {"CHECKOUT_CANARY_HEADER_NAME": NAME}
    assert run(EXAMPLE_JOURNEY, working_shop_url, tmp_path / "out", env) == 2
    assert "CHECKOUT_CANARY_HEADER_VALUE is not set" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_header_is_not_forwarded_to_another_origin_on_redirect(
    gated_ok, other_origin, tmp_path, capsys
):
    journey = write_journey(
        tmp_path, "  - goto: /go-away.html\n  - expect_text: {selector: h1, text: other origin}\n"
    )

    code = run(journey, gated_ok.base_url, tmp_path / "out", ENV)

    assert code == 0  # the browser followed the redirect
    assert other_origin.requests, "the redirect target was never contacted"
    for request in other_origin.requests:
        assert NAME.lower() not in request["headers"]
        assert SECRET not in json.dumps(request["headers"])
    assert "were redirected" in capsys.readouterr().out


def test_cookies_still_work_with_the_header(gated_ok, tmp_path):
    journey = write_journey(
        tmp_path,
        "  - goto: /set-cookie.html\n"
        "  - goto: /read-cookie.html\n"
        "  - expect_text: {selector: h1, text: cookie=cart=abc123}\n",
    )
    assert run(journey, gated_ok.base_url, tmp_path / "out", ENV) == 0


def contains_secret(data: bytes) -> bool:
    return SECRET.encode() in data


def test_secret_never_reaches_evidence_files_or_console(
    gated_broken, other_origin, tmp_path, capsys
):
    """Failing run with the header: scan result.json, screenshots, the trace zip and the console."""
    out = tmp_path / "out"
    assert run(EXAMPLE_JOURNEY, gated_broken.base_url, out, ENV) == 1

    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    scanned = 0
    for path in out.rglob("*"):
        if path.is_file() and path.suffix != ".zip":
            assert not contains_secret(path.read_bytes()), f"secret found in {path.name}"
            scanned += 1
    assert scanned >= 2  # result.json and failure.png at least
    trace = out / "trace.zip"
    if trace.exists():
        with zipfile.ZipFile(trace) as archive:
            for member in archive.namelist():
                assert not contains_secret(archive.read(member)), f"secret found in trace: {member}"
