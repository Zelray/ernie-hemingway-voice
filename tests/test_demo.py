"""In-process demo API tests; no model endpoint is contacted."""
import asyncio

import httpx

from demo.server import BASELINE_SYSTEM, NEUTRAL_SYSTEM, app, build_user_message


def request(method, path, **kwargs):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(send())


def test_prompt_disclosure_matches_the_two_columns():
    response = request("GET", "/api/info")
    assert response.status_code == 200
    data = response.json()
    assert data["ernie"]["system"] == NEUTRAL_SYSTEM == "You are a helpful assistant."
    assert data["baseline"]["system"] == BASELINE_SYSTEM
    assert "Ernest Hemingway" in data["baseline"]["system"]
    assert set(data["ernie"]) == {"model", "system"}
    assert set(data["baseline"]) == {"model", "system"}


def test_rewrite_uses_trained_task_instruction():
    assert build_user_message("rewrite", "Original content.") == "Rewrite this in your own voice:\n\nOriginal content."
    assert build_user_message("ask", "A question?") == "A question?"


def test_empty_and_overlong_inputs_are_rejected_before_inference():
    empty = request("POST", "/api/stream", json={"target": "ernie", "text": " "})
    long = request("POST", "/api/stream", json={"target": "ernie", "text": "a" * 4001})
    assert empty.status_code == 400
    assert empty.json() == {"error": "empty input"}
    assert long.status_code == 400
    assert "4000" in long.json()["error"]
