import functools
import http.server
import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

SHOP_DIR = Path(__file__).parent / "fixtures" / "shop"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent
EXAMPLE_JOURNEY = REPO_ROOT / "examples" / "demo-shop.yml"

SEEN_USER_AGENTS: list[str] = []


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        SEEN_USER_AGENTS.append(self.headers.get("User-Agent", ""))
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def serve_directory(directory: Path) -> Iterator[str]:
    """Serve a directory on a free local port; yields the base URL."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture(autouse=True)
def _reset_seen_user_agents() -> None:
    SEEN_USER_AGENTS.clear()


@pytest.fixture
def working_shop_url() -> Iterator[str]:
    """Base URL of the local fixture shop whose checkout works."""
    yield from serve_directory(SHOP_DIR / "ok")


@pytest.fixture
def broken_shop_url() -> Iterator[str]:
    """Base URL of the local fixture shop whose cart has no checkout button."""
    yield from serve_directory(SHOP_DIR / "broken")


class FakeTelegram:
    """Local stand-in for api.telegram.org. Records requests; tests never use the real API."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.status = 200
        self.base_url = ""


@pytest.fixture
def fake_telegram() -> Iterator[FakeTelegram]:
    fake = FakeTelegram()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            fake.requests.append({"path": self.path, "body": body})
            payload = (
                {"ok": True, "result": {"message_id": 1}}
                if fake.status == 200
                else {"ok": False, "error_code": fake.status, "description": "Unauthorized"}
            )
            data = json.dumps(payload).encode()
            self.send_response(fake.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield fake
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
