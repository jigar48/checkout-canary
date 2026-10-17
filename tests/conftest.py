import functools
import http.server
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

SHOP_DIR = Path(__file__).parent / "fixtures" / "shop"
EXAMPLE_JOURNEY = Path(__file__).parent.parent / "examples" / "demo-shop.yml"


SEEN_USER_AGENTS: list[str] = []


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        SEEN_USER_AGENTS.append(self.headers.get("User-Agent", ""))
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def _serve(variant: str) -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(SHOP_DIR / variant))
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
    yield from _serve("ok")


@pytest.fixture
def broken_shop_url() -> Iterator[str]:
    """Base URL of the local fixture shop whose cart has no checkout button."""
    yield from _serve("broken")
