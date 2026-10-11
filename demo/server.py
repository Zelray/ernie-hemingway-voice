"""
Ernie — the Ernestifier.  M3 3-column compare demo (local-first, RunPod-ready).

Serves a 3-column UI and proxies generation to an OpenAI-compatible chat
endpoint.  Local default = Ollama (http://127.0.0.1:11434/v1).

THE FAIR FIGHT (the whole point of the demo):
  - Middle column  = ernie:epoch3   + a NEUTRAL system prompt  (voice in the weights)
  - Right  column  = qwen2.5:3b      + an HONEST, strong "write like Hemingway"
                     system prompt   (the same base model, prompted as well as we can)

RunPod-ready seam: every model host lives in TARGETS below, one entry per column,
each {base_url, model, api_key, system}.  Going public = point `ernie` at a RunPod
serverless vLLM endpoint (set ERNIE_BASE / ERNIE_MODEL / ERNIE_KEY).  The UI never
changes and the API key never reaches the browser.
"""
import asyncio
import json
import os
import time
from collections import deque
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse

# --- Honesty-critical prompts (recovered verbatim from generations.json) ---------
NEUTRAL_SYSTEM = "You are a helpful assistant."

# The STRONGEST honest zero-shot "write like Hemingway" prompt we could write
# (mined from the bucket-4 cadence panel, examples stripped to keep it a fair
# zero-shot fight — no hand-crafted few-shot Hemingway samples, which would change
# the claim to "fine-tuning beats FEW-SHOT prompting").  It explicitly demands the
# OPPOSITE of caricature: vary sentence length, hold at least one long and-chained
# sentence, "all-choppy is the cheap parody, WRONG".  VALIDATED (session 17): on the
# 18 real-text holdout questions, at temps 0.3/0.7/1.0, this prompt scores the SAME
# rhythm variance as the old prompt (~1.6) and nowhere near real Hemingway (6.46) or
# Ernie (~6).  qwen-3B simply ignores the instruction — it cannot produce the rhythm.
# So the prompt's value is HONESTY: a skeptic who reads it (the ⓘ popup) can no
# longer say "you told it to be choppy."  The baseline is told to do exactly what
# Hemingway does, and still can't — that is the fair fight, made unattackable.
BASELINE_SYSTEM = (
    "You are a writing assistant. Answer the user's request in the prose style of "
    "Ernest Hemingway. Two things matter equally — never sacrifice either.\n\n"
    "First, actually answer. Give a true, specific, useful response to the exact "
    "request. The concrete, correct details are the answer; a pretty answer that "
    "dodges the question is a failure. Never invent mood or scenery for a practical "
    "question.\n\n"
    "Second, carry the voice. The voice is plainness and rhythm:\n"
    "- Plain, common words. Concrete nouns and strong verbs. Prefer the simple "
    "word. Almost no -ly adverbs, few adjectives, no filler.\n"
    "- Show feeling through fact and action — the 'iceberg' restraint — and do not "
    "name the feeling outright.\n"
    "- The rhythm rises and falls. Most sentences run short to medium. Mix in very "
    "short punches of two to five words. But every answer must also hold at least "
    "one long sentence — about fifteen to thirty words — that runs several thoughts "
    "together with 'and' and lets them flow before it stops. Move it around: "
    "sometimes early, sometimes late.\n"
    "- An answer of nothing but short, choppy sentences is WRONG — that is the "
    "cheap parody. An answer of all long sentences is just as wrong. The real voice "
    "is the MIX of short and long.\n\n"
    "Do not mention Hemingway or that you are imitating any style. Do not begin with "
    "'Here is' or 'Sure.' Just answer in that voice."
)

# The trained rewrite-instruction shape (bucket 3).  Inference uses the canonical
# phrasing; the model saw a rotation of these during training.
REWRITE_INSTRUCTION = "Rewrite this in your own voice:"

# --- Per-target config = the RunPod-ready seam ----------------------------------
OLLAMA = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434/v1")

TARGETS = {
    "ernie": {
        "base_url": os.environ.get("ERNIE_BASE", OLLAMA),
        "model": os.environ.get("ERNIE_MODEL", "ernie:epoch3"),
        "api_key": os.environ.get("ERNIE_KEY", "ollama"),
        "system": NEUTRAL_SYSTEM,
    },
    "baseline": {
        "base_url": os.environ.get("BASELINE_BASE", OLLAMA),
        "model": os.environ.get("BASELINE_MODEL", "qwen2.5:3b"),
        "api_key": os.environ.get("BASELINE_KEY", "ollama"),
        "system": BASELINE_SYSTEM,
    },
}

# The poetry is a TEMPERATURE dial (session-16 finding): 0.3 = pragmatic/faithful,
# ~0.7 = the lyrical "tears" sweet spot (still coherent, on-voice), 0.95 = most
# poetic but starts to drift (person-shift, old-man-sea pastiche).  Exposed to the
# user as the "Voice" control.  Default depends on mode: rewrite stays faithful for
# fidelity (no confabulating a client's real content); ask leans lyrical.
CREATIVITY = {"faithful": 0.3, "lyrical": 0.7, "daring": 0.95}
DEFAULT_CREATIVITY = {"rewrite": "faithful", "ask": "lyrical"}
MAX_TOKENS = 768

# Fixed sampling seed so the TEMPERATURE slider is the ONLY thing that changes
# between runs of the same prompt.  Without it, every call rolls a fresh random
# seed whose variation swamps the temperature effect (the s16 "slider feels
# broken" bug).  Also makes the demo reproducible — no prospect hits a dud roll.
SEED = 42

# Belt-and-suspenders: pass the ChatML stop markers on every call so a model
# imported without them (the s15 runaway-template gotcha) still ends its turn.
STOP = ["<|im_end|>", "<|im_start|>"]

# Longest input we accept.  A demo prompt is a paragraph or a question; anything
# past this is abuse or a paste accident, and every extra char is GPU cost.
MAX_INPUT_CHARS = 4000

# Global concurrency cap.  min/max workers = 0/1 upstream means the GPU serves
# one request at a time; this ceiling refuses a stampede at the door (429) rather
# than letting requests pile up.  A "Run both" click spends 2 permits (ernie +
# baseline), so 6 permits ≈ 3 simultaneous visitors.
MAX_CONCURRENT = 6
_sem = asyncio.Semaphore(MAX_CONCURRENT)

# --- Anti-abuse rate limiting (P0 #3, app layer) --------------------------------
# The hard COST ceiling is upstream (Max Workers = 1 + prepaid billing cap +
# Semaphore above).  This is the VOLUME/abuse guard: a per-IP sliding window plus
# a global daily request cap, so one bot can't burn the day's GPU minutes or drown
# real visitors.  In-memory is correct here — the proxy is a single process; no
# Redis, no new dependency.  All limits are env-tunable.  Each "Run both" click =
# 2 POSTs (ernie + baseline), so 30 req/IP/min ≈ 15 clicks/min — roomy for a human,
# throttling for a bot.  (The _ip_hits map keeps one small deque per IP seen; a
# public demo redeploys long before that could matter.)
RATE_MAX = int(os.environ.get("RATE_MAX_PER_MIN", "30"))          # requests / IP / window
RATE_WINDOW = 60.0                                                # seconds
GLOBAL_DAILY_MAX = int(os.environ.get("GLOBAL_DAILY_MAX", "2000"))  # requests / day, all IPs

_ip_hits: dict[str, deque] = {}
_day_bucket = {"day": None, "count": 0}


def _client_ip(req: Request) -> str:
    # Behind Cloudflare (the launch topology — VPS firewalled to CF IPs), the real
    # visitor IP is in CF-Connecting-IP.  Fall back to the first X-Forwarded-For
    # hop, then the socket peer for local/dev.
    return (
        req.headers.get("cf-connecting-ip")
        or req.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (req.client.host if req.client else "unknown")
    )


def _rate_check(ip: str) -> str | None:
    """None if allowed, else the reason the request is refused: 'global' or 'ip'."""
    now = time.monotonic()
    today = time.strftime("%Y-%m-%d")  # calendar day for the global cap
    if _day_bucket["day"] != today:
        _day_bucket["day"], _day_bucket["count"] = today, 0
    if _day_bucket["count"] >= GLOBAL_DAILY_MAX:
        return "global"
    hits = _ip_hits.get(ip)
    if hits is None:
        hits = _ip_hits[ip] = deque()
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    if len(hits) >= RATE_MAX:
        return "ip"
    hits.append(now)
    _day_bucket["count"] += 1
    return None


STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Ernie - the Ernestifier")


def build_user_message(mode: str, text: str) -> str:
    if mode == "rewrite":
        return f"{REWRITE_INSTRUCTION}\n\n{text}"
    return text


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/info")
def info():
    """The real system prompts, so the UI's 'see the prompt' popup can never drift
    from what is actually sent.  Proving the fair fight is the whole point."""
    return {
        "ernie": {"model": TARGETS["ernie"]["model"], "system": TARGETS["ernie"]["system"]},
        "baseline": {"model": TARGETS["baseline"]["model"], "system": TARGETS["baseline"]["system"]},
        "rewrite_instruction": REWRITE_INSTRUCTION,
    }


@app.post("/api/stream")
async def stream(req: Request):
    body = await req.json()
    target_key = body.get("target")
    mode = body.get("mode", "rewrite")
    text = (body.get("text") or "").strip()

    if target_key not in TARGETS:
        return JSONResponse({"error": f"unknown target {target_key!r}"}, status_code=400)
    if not text:
        return JSONResponse({"error": "empty input"}, status_code=400)
    if len(text) > MAX_INPUT_CHARS:
        return JSONResponse(
            {"error": "That's a bit long for the demo — please keep it under 4000 characters."},
            status_code=400,
        )

    # Anti-abuse gate: refuse a per-IP flood (429) or a day past the global cap
    # (503) before spending any GPU time.  Log the real reason server-side only.
    refusal = _rate_check(_client_ip(req))
    if refusal == "ip":
        return JSONResponse(
            {"error": "You're going a little fast — give it a few seconds and try again."},
            status_code=429,
        )
    if refusal == "global":
        print("[rate] global daily cap reached — refusing until tomorrow", flush=True)
        return JSONResponse(
            {"error": "The demo has hit its limit for today. Please check back tomorrow."},
            status_code=503,
        )

    # Explicit slider value wins; clamp for safety.  Fall back to the named
    # creativity stops, then a mode default.
    temp_in = body.get("temperature")
    if temp_in is not None:
        try:
            temperature = max(0.0, min(1.5, float(temp_in)))
        except (TypeError, ValueError):
            temperature = 0.5
    else:
        creativity = body.get("creativity") or DEFAULT_CREATIVITY.get(mode, "lyrical")
        temperature = CREATIVITY.get(creativity, 0.7)

    t = TARGETS[target_key]
    payload = {
        "model": t["model"],
        "temperature": temperature,
        "seed": int(body.get("seed", SEED)),
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "stop": STOP,
        "messages": [
            {"role": "system", "content": t["system"]},
            {"role": "user", "content": build_user_message(mode, text)},
        ],
    }
    url = t["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {t['api_key']}"}

    # Global concurrency gate: take a slot or turn the visitor away politely.
    # wait_for(timeout) makes this race-free (acquire is atomic) and never hangs.
    try:
        await asyncio.wait_for(_sem.acquire(), timeout=0.05)
    except asyncio.TimeoutError:
        return JSONResponse(
            {"error": "Ernie is helping a lot of visitors right now. Please try again in a moment."},
            status_code=429,
        )

    async def gen():
        # RunPod serverless scales to zero; the FIRST request after idle can hang
        # (GPU loading the model) or return 5xx / connection errors for ~60-90s.
        # Emit {"status":"warming"} IMMEDIATELY so the UI shows a friendly counter
        # even if the cold worker holds the connection open, then retry BEFORE the
        # first token so a visitor never sees a raw error. Once tokens stream, never
        # retry. Upstream error bodies/exceptions are logged server-side but NEVER
        # forwarded to the browser (they can embed the RunPod endpoint id).
        backoffs = [2, 4, 8, 16, 30, 30]  # ~90s of patience for a cold worker
        warming_sent = True
        streamed = False
        try:
            yield _sse({"status": "warming"})
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
                for i in range(len(backoffs) + 1):
                    try:
                        async with client.stream("POST", url, json=payload, headers=headers) as resp:
                            if resp.status_code == 200:
                                async for line in resp.aiter_lines():
                                    if not line or not line.startswith("data: "):
                                        continue
                                    data = line[6:]
                                    if data.strip() == "[DONE]":
                                        break
                                    try:
                                        delta = json.loads(data)["choices"][0]["delta"].get("content", "")
                                    except Exception:
                                        continue
                                    if delta:
                                        streamed = True
                                        yield _sse({"t": delta})
                                break  # finished a 200 stream
                            await resp.aread()  # drain
                            if resp.status_code in (500, 502, 503, 504) and i < len(backoffs):
                                if not warming_sent:
                                    warming_sent = True
                                    yield _sse({"status": "warming"})
                                await asyncio.sleep(backoffs[i])
                                continue
                            print(f"[stream] upstream {resp.status_code} for {target_key}: {resp.text[:500]!r}", flush=True)
                            yield _sse({"error": "The model service is busy or unavailable. Please try again in a moment."})
                            break
                    except (httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                        if i < len(backoffs):
                            if not warming_sent:
                                warming_sent = True
                                yield _sse({"status": "warming"})
                            await asyncio.sleep(backoffs[i])
                            continue
                        print(f"[stream] connection error for {target_key}: {e!r}", flush=True)
                        yield _sse({"error": "The model service is taking too long to respond. Please try again."})
                        break
        except Exception as e:
            print(f"[stream] unexpected error for {target_key}: {e!r}", flush=True)
            if not streamed:
                yield _sse({"error": "Something went wrong reaching the model. Please try again."})
        finally:
            _sem.release()
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(obj) -> str:
    return f"data: {json.dumps(obj)}\n\n"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
