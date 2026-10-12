"""Offline tests of the shared Gemini client.

The retry loop, error tags, key loading and pacing run against a real local
HTTP server (stdlib http.server on an ephemeral localhost port) — genuine
urllib round-trips, no network, no API spend (R6). The only substitution is
the clock: a plain injectable function records delays instead of sleeping, so
backoff policy is observable in milliseconds. No mock/patch anywhere.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import gemini_client
from gemini_client import GeminiClient, INTER_CALL_SLEEP, load_key


# ── Local scripted endpoint (real HTTP, queue of outcomes) ───────────────────
class ScriptedHandler(BaseHTTPRequestHandler):
    """Pops one outcome per request: a dict = a 200 with that JSON payload; an
    int = that HTTP status with a JSON error body; a (status, body) tuple =
    that exact status and raw body. Records path and request body."""

    def do_POST(self):
        server = self.server
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with server.lock:
            outcome = server.script.pop(0) if server.script else None
            server.requests.append((self.path, raw))
        if isinstance(outcome, dict):
            body = json.dumps(outcome).encode("utf-8")
            self.send_response(200)
        elif isinstance(outcome, tuple):
            status, text = outcome
            body = text.encode("utf-8")
            self.send_response(status)
        else:
            status = outcome if isinstance(outcome, int) else 500
            body = json.dumps({"error": {"code": status, "message": "scripted failure"}}).encode("utf-8")
            self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def endpoint():
    server = HTTPServer(("localhost", 0), ScriptedHandler)
    server.script = []
    server.requests = []
    server.lock = threading.Lock()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


class SleepLog:
    """Stand-in clock: records the requested delays instead of waiting."""

    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


def make_client(server, **kwargs):
    log = SleepLog()
    client = GeminiClient(
        "test-key",
        base_url=f"http://localhost:{server.server_port}",
        sleep=log,
        **kwargs,
    )
    return client, log


def ok_response(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def backoff_bounds(attempt):
    """The unified policy: capped exponential delay plus jitter in [0, 1.5]."""
    base = min(2 ** attempt * 2, 30)
    return base, base + 1.5


# ── Request contract and happy path ──────────────────────────────────────────
def test_generate_posts_proven_request_shape_and_returns_text(endpoint):
    endpoint.script.append(ok_response("  Answer text.  "))
    client, log = make_client(endpoint)
    result = client.generate("Hello there.", temperature=0.55, max_output_tokens=777)
    assert result == "Answer text."
    assert log.calls == []
    path, raw = endpoint.requests[0]
    assert path == f"/models/{gemini_client.DEFAULT_MODEL}:generateContent?key=test-key"
    payload = json.loads(raw.decode("utf-8"))
    assert payload["contents"][0]["parts"][0]["text"] == "Hello there."
    assert payload["generationConfig"]["temperature"] == 0.55
    assert payload["generationConfig"]["maxOutputTokens"] == 777
    assert payload["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0


# ── Retry policy (unified: capped exponential + jitter on 429/500/503) ───────
def test_retryable_statuses_are_retried_with_capped_jittered_backoff(endpoint):
    endpoint.script.extend([500, 429, ok_response("third try")])
    client, log = make_client(endpoint)
    assert client.generate("Hello there.") == "third try"
    assert len(endpoint.requests) == 3
    assert len(log.calls) == 2
    for attempt, delay in enumerate(log.calls):
        low, high = backoff_bounds(attempt)
        assert low <= delay <= high


def test_exhaustion_returns_http_error_tag_after_exactly_retries_attempts(endpoint):
    endpoint.script.extend([503, 503, 503, ok_response("never reached")])
    client, log = make_client(endpoint, retries=3)
    result = client.generate("Hello there.")
    assert result.startswith("[ERROR HTTP 503:")
    assert "scripted failure" in result
    assert len(endpoint.requests) == 3
    assert len(log.calls) == 2  # no sleep after the final attempt


def test_non_retryable_status_fails_on_first_attempt(endpoint):
    endpoint.script.append(400)
    client, log = make_client(endpoint)
    result = client.generate("Hello there.")
    assert result.startswith("[ERROR HTTP 400:")
    assert len(endpoint.requests) == 1
    assert log.calls == []


def test_generic_exception_retries_then_succeeds(endpoint):
    endpoint.script.extend([(200, "not-json"), ok_response("recovered")])
    client, log = make_client(endpoint, retries=2)
    assert client.generate("Hello there.") == "recovered"
    assert len(endpoint.requests) == 2
    assert len(log.calls) == 1


# ── Immediate-fail responses (never resolve on retry) ────────────────────────
def test_empty_candidates_fail_immediately_with_feedback(endpoint):
    endpoint.script.append({"promptFeedback": {"blockReason": "SAFETY"}})
    client, log = make_client(endpoint)
    result = client.generate("Hello there.")
    assert result.startswith("[ERROR NO_CANDIDATES:")
    assert "SAFETY" in result
    assert len(endpoint.requests) == 1
    assert log.calls == []


def test_missing_parts_fail_immediately_with_finish_reason(endpoint):
    endpoint.script.append({"candidates": [{"finishReason": "SAFETY"}]})
    client, log = make_client(endpoint)
    assert client.generate("Hello there.") == "[ERROR NO_PARTS finish=SAFETY]"
    assert len(endpoint.requests) == 1
    assert log.calls == []


# ── Key handling (function, not import-time; env wins over key file) ─────────
def test_load_key_prefers_env_over_key_file(tmp_path):
    key_file = tmp_path / "gemini_key.txt"
    key_file.write_text("file-key\n", encoding="utf-8")
    assert load_key(env={"GEMINI_API_KEY": "env-key"}, key_file=key_file) == "env-key"


def test_load_key_reads_file_when_env_has_no_key(tmp_path):
    key_file = tmp_path / "gemini_key.txt"
    key_file.write_text("  file-key  \n", encoding="utf-8")
    assert load_key(env={}, key_file=key_file) == "file-key"


def test_load_key_raises_clear_error_when_neither_source_has_a_key(tmp_path):
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        load_key(env={}, key_file=tmp_path / "absent.txt")


# ── Inter-call pacing ────────────────────────────────────────────────────────
def test_pace_sleeps_the_module_interval_through_the_injected_clock(endpoint):
    client, log = make_client(endpoint)
    client.pace()
    assert log.calls == [INTER_CALL_SLEEP]
