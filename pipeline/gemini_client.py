"""
gemini_client.py — shared Gemini generateContent call for future run scripts.

WHY THIS EXISTS (plain English):
  Five historical generators each carry their own copy of the Gemini HTTP loop
  (key, request shape, retry/backoff, [ERROR ...] tags, inter-call pacing).
  Rule R7's client-simulation work will add more generation runs. Without one
  owner, each new script copies the loop again. This module is that owner.

  Historical scripts stay untouched: they keep the copies that produced the
  training set. New scripts call this module and keep only their workload
  (prompts, caps, resume, output writing).

  NO IMPORT-TIME SIDE EFFECTS. The five historical scripts read gemini_key.txt
  at import, which is why offline gates parse them instead of importing them.
  load_key() is a function. GeminiClient is constructed with an explicit key.

RETRY / BACKOFF (unified on the bucket3 variant, Mike 2026-10-12):
  6 tries. Delay min(2**attempt*2, 30) + random.uniform(0, 1.5).
  Retryable HTTP codes: 429, 500, 503. Generic exceptions also retry.
  Sleep only when another attempt remains.

CONSCIOUS UNIFICATION vs the pilot copies:
  A 200 whose JSON has no candidates, or a candidate with no parts, is an
  immediate [ERROR ...] return. Those responses will not heal on retry, so
  they must not burn the retry budget. The older pilot copies retried them
  via KeyError from direct indexing. Transport failures and JSON parse
  errors still retry (they can heal).

STDLIB ONLY: json, os, random, time, urllib.request, urllib.error.

The HTTP seam is base_url (tests point it at a local http.server).
The clock seam is sleep (tests pass a recorder; production uses time.sleep).
"""
import json
import os
import random
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash"
INTER_CALL_SLEEP = 1.2
RETRYABLE_CODES = frozenset({429, 500, 503})

_DEFAULT_KEY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "gemini_key.txt"
)


def load_key(env=None, key_file=None):
    """Return the Gemini API key.

    GEMINI_API_KEY in env wins. If it is missing or blank, the gitignored
    key file is read (default: gemini_key.txt at the repo root). Raises
    RuntimeError naming GEMINI_API_KEY when neither source has a key.
    """
    if env is None:
        env = os.environ
    value = (env.get("GEMINI_API_KEY") or "").strip()
    if value:
        return value
    path = _DEFAULT_KEY_FILE if key_file is None else key_file
    try:
        with open(path, encoding="utf-8") as handle:
            value = handle.read().strip()
    except OSError:
        value = ""
    if value:
        return value
    raise RuntimeError(
        "Set GEMINI_API_KEY or place a key in gemini_key.txt at the repo root"
    )


class GeminiClient:
    """One Gemini generateContent caller with retry, error tags, and pacing."""

    def __init__(
        self,
        api_key,
        *,
        model=DEFAULT_MODEL,
        base_url=DEFAULT_BASE_URL,
        timeout=60.0,
        retries=6,
        sleep=time.sleep,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.retries = retries
        self.sleep = sleep

    def pace(self):
        """Courtesy gap between successive calls, via the injected clock."""
        self.sleep(INTER_CALL_SLEEP)

    def generate(self, prompt, *, temperature=0.3, max_output_tokens=1000):
        """POST generateContent. Returns stripped text or an [ERROR ...] tag.

        Request shape matches the proven bucket3 copy: contents/parts,
        generationConfig with temperature, maxOutputTokens, and
        thinkingConfig.thinkingBudget=0. Key is passed as ?key=.
        """
        url = (
            f"{self.base_url}/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }).encode("utf-8")
        retries = self.retries
        for attempt in range(retries):
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                cands = data.get("candidates")
                if not cands:
                    fb = json.dumps(data.get("promptFeedback", {}))[:160]
                    return f"[ERROR NO_CANDIDATES: {fb}]"
                parts = cands[0].get("content", {}).get("parts")
                if not parts:
                    reason = cands[0].get("finishReason", "?")
                    return f"[ERROR NO_PARTS finish={reason}]"
                return parts[0]["text"].strip()
            except urllib.error.HTTPError as error:
                if error.code in RETRYABLE_CODES and attempt < retries - 1:
                    self.sleep(_backoff(attempt))
                    continue
                body = error.read().decode("utf-8")[:160]
                return f"[ERROR HTTP {error.code}: {body}]"
            except Exception as error:
                if attempt < retries - 1:
                    self.sleep(_backoff(attempt))
                    continue
                return f"[ERROR {type(error).__name__}: {error}]"


def _backoff(attempt):
    """Capped exponential delay plus jitter in [0, 1.5], bucket3 policy."""
    return min(2 ** attempt * 2, 30) + random.uniform(0, 1.5)
