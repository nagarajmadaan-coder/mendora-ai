"""
Exercises the REAL network code (urllib_transport) against a local fake provider server,
so timeouts and connection errors are tested for real — still without calling any real AI API.
"""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import anthropic_body, auth, create_request, make_settings, register


class _Handler(BaseHTTPRequestHandler):
    mode = "ok"
    received: list[dict] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", 0))
        _Handler.received.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": self.rfile.read(length)})
        if _Handler.mode == "slow":
            time.sleep(2)
        status, body = (200, anthropic_body()) if _Handler.mode in ("ok", "slow") else (429, '{"error":"rate"}')
        data = body.encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # keep test output quiet
        pass


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):  # client hanging up during the timeout test is expected
        pass


@pytest.fixture(autouse=True)
def _no_proxy_for_localhost(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


@pytest.fixture
def fake_provider():
    server = _QuietServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Handler.received = []
    yield server
    server.shutdown()


def _run(tmp_path, base_url, timeout=5.0):
    # No fake transport passed → the real urllib transport is used.
    settings = make_settings(tmp_path, ai_base_url=base_url, ai_timeout_seconds=timeout)
    with TestClient(create_app(settings)) as c:
        token = register(c)
        rid = create_request(c, auth(token)).json()["request_id"]
        return c.post(f"/api/repair-requests/{rid}/diagnosis", headers=auth(token))


def test_real_transport_success(tmp_path, fake_provider):
    _Handler.mode = "ok"
    r = _run(tmp_path, f"http://127.0.0.1:{fake_provider.server_port}")
    assert r.status_code == 200 and r.json()["diagnosis"]["source"] == "ai"
    assert _Handler.received[0]["path"] == "/v1/messages"
    assert _Handler.received[0]["headers"]["x-api-key"] == "test-key-not-real"


def test_real_transport_timeout(tmp_path, fake_provider):
    _Handler.mode = "slow"
    started = time.monotonic()
    r = _run(tmp_path, f"http://127.0.0.1:{fake_provider.server_port}", timeout=0.5)
    assert r.status_code == 504 and r.json()["error"]["code"] == "ai_timeout"
    assert time.monotonic() - started < 2.5  # gave up quickly instead of hanging


def test_real_transport_http_error(tmp_path, fake_provider):
    _Handler.mode = "rate"
    r = _run(tmp_path, f"http://127.0.0.1:{fake_provider.server_port}")
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_rate_limited"


def test_real_transport_unreachable(tmp_path):
    with socket.socket() as s:  # find a port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    r = _run(tmp_path, f"http://127.0.0.1:{port}")
    assert r.status_code == 502 and r.json()["error"]["code"] == "ai_provider_error"
