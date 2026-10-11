"""
gen_bucket3_sun.py — BUCKET-3 (flatten-restore) generator for ONE work:
The Sun Also Rises (carrier; CAP 115 clean output pairs — never exceed).

WHAT IT DOES (plain English):
  Bucket 3 is the hero feature: paste an article, get it back in Hemingway's voice.
  Each training pair is  flat -> real :
    - REAL Hemingway span  = the training TARGET (genuine voice, never imitated).
    - Gemini FLATTENS it    = the training INPUT  (voiceless, bureaucratic prose).

  This is the PAID half (pre-approved cheap Gemini generation). It REUSES, never
  reinvents, the proven machinery:
    - 04_mine_passages.mine_work + span_is_clean  -> this work's clean spans.
    - 05_dress_rehearsal_flatten.FLATTEN_PROMPT   -> the proven person/fact/entity-
      preserving flatten prompt (temp ~0.3).
    - fidelity_gate.fidelity_gate (DE-NOISED)     -> hard-flag real loss/garble.
    - spine.append_record / load_done_ids         -> crash-safe streaming + resume.

PIPELINE (per the task brief):
  1. Mine this work's clean bucket-3 spans UNCAPPED (full pool), honoring the
     bucket-1 reservation by READING bucket1_reserved.jsonl into the registry
     (read-only: we do NOT call build_reserved_registry(), which rewrites that
     file and would race the other parallel generators).
  2. Deterministically SHUFFLE the pool (seed) so the 115 we keep are spread
     across the whole novel (front romance + Caporetto retreat + Switzerland
     ending), not just Book One. Shuffle is stable across runs -> idempotent
     resume + automatic backfill of skipped spans.
  3. DEFENSIVE re-check: re-assert span_is_clean before flattening each span
     (belt-and-suspenders; mine_work already guarantees it, so this is expected
     to be a no-op -> n_skipped_defensive≈0).
  4. Flatten via Gemini (temp 0.3). On a HARD gate flag, REGENERATE once at a
     slightly higher temp (0.5) to escape an under-flatten leak; if it still
     hard-flags, SKIP and record why. Record the temp that actually produced the
     accepted output.
  5. STREAM each clean pair the instant it passes -> pipeline/bucket3/<work>.jsonl.

CAP semantics: 115 is a ceiling on CLEAN OUTPUT pairs, not on attempts. Flagged/
  errored spans are absorbed by continuing down the shuffled pool (big cushion).

RUN (Bash; PowerShell hangs this box):
  python pipeline/gen_bucket3_farewell.py            # full run (resumable)
  python pipeline/gen_bucket3_farewell.py --smoke 2  # only produce 2 this run
  python pipeline/gen_bucket3_farewell.py --dry      # mine+shuffle, no API/no $
"""
import os, sys, json, time, random, urllib.request, urllib.error, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine                                            # noqa: E402
miner = importlib.import_module("04_mine_passages")     # mine_work, span_is_clean
m05 = importlib.import_module("05_dress_rehearsal_flatten")  # proven FLATTEN_PROMPT
from fidelity_gate import fidelity_gate, _load_dictionary   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
WORK = "the-sun-also-rises"
CAP = 115                 # ceiling on CLEAN OUTPUT pairs — do NOT exceed
SEED = 1926               # deterministic shuffle seed (stable across resumes)
MODEL = "gemini-2.5-flash"
TEMP = 0.3                # proven flatten temp (reliability, not creativity)
TEMP_RETRY = 0.5          # decorrelate the one regeneration to escape leaks
INTER_CALL_SLEEP = 1.2    # base pacing between calls (parallel-friendly)

ROOT = "https://generativelanguage.googleapis.com/v1beta"
KEY = open(os.path.join(HERE, "..", "gemini_key.txt"), encoding="utf-8").read().strip()
FLATTEN_PROMPT = m05.FLATTEN_PROMPT
RESERVED = os.path.join(HERE, "bucket1_reserved.jsonl")
OUT = os.path.join(HERE, "bucket3", WORK + ".jsonl")


# ── Gemini call (proven machinery + variable temp + empty-candidate guard) ─────
def generate(prompt, temperature, retries=6):
    """POST generateContent, key via ?key=, thinkingBudget=0, exponential backoff
    with jitter on 429/500/503 (parallel-friendly). Returns text, or an "[ERROR ...]"
    string. A safety-blocked / empty-candidates response is returned as an error
    IMMEDIATELY (it will not resolve on retry) so we don't burn the retry budget."""
    url = f"{ROOT}/models/{MODEL}:generateContent?key={KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 1000,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cands = data.get("candidates")
            if not cands:    # safety block / empty -> won't fix on retry, skip now
                fb = json.dumps(data.get("promptFeedback", {}))[:160]
                return f"[ERROR NO_CANDIDATES: {fb}]"
            parts = cands[0].get("content", {}).get("parts")
            if not parts:    # finishReason without text (e.g. SAFETY/MAX_TOKENS)
                return f"[ERROR NO_PARTS finish={cands[0].get('finishReason','?')}]"
            return parts[0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 30) + random.uniform(0, 1.5))
                continue
            return f"[ERROR HTTP {e.code}: {e.read().decode('utf-8')[:160]}]"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 30) + random.uniform(0, 1.5))
                continue
            return f"[ERROR {type(e).__name__}: {e}]"


# ── Registry from the EXISTING reserved file (read-only -> race-safe) ──────────
def reserved_registry():
    reg = spine.SpanRegistry()
    if os.path.exists(RESERVED):
        with open(RESERVED, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue   # tolerate a torn line from a parallel rewrite
                if r.get("work") and r.get("char_start") is not None:
                    reg.claim(r["work"], r["char_start"], r["char_end"], r.get("bucket", "1"))
    return reg


def main():
    dry = "--dry" in sys.argv
    smoke = None
    if "--smoke" in sys.argv:
        smoke = int(sys.argv[sys.argv.index("--smoke") + 1])

    # 1) mine uncapped, honoring bucket-1 reservation (read-only registry)
    recs, collisions = miner.mine_work(WORK, reserved_registry(), bucket="3", cap=None)
    n_mined = len(recs)

    # 2) deterministic spread across the whole novel (stable across resumes)
    random.Random(SEED).shuffle(recs)

    garble_status = "ON" if _load_dictionary() is not False else "DISABLED (no wordlist)"

    if dry:
        print(f"WORK={WORK} N_MINED={n_mined} COLLISIONS={collisions} "
              f"CAP={CAP} GARBLE_CHECK={garble_status} (dry: no API, no $)")
        return

    # idempotent resume: already-streamed clean pairs count toward the cap
    done = spine.load_done_ids(OUT)
    n_clean = len(done)
    n_skipped_defensive = n_gate_flagged = n_errors = attempts = 0
    gate_flags = []

    for c in recs:
        if n_clean >= CAP:
            break
        if smoke is not None and (n_clean - len(done)) >= smoke and n_clean > len(done):
            break
        cid = c["id"]
        if cid in done:
            continue
        target = c["span_text"]

        # 3) DEFENSIVE belt-and-suspenders recheck (expected no-op)
        if not miner.span_is_clean(target):
            n_skipped_defensive += 1
            continue

        # 4) flatten (temp 0.3); on a HARD flag, regenerate ONCE at 0.5
        attempts += 1
        used_temp = TEMP
        flat = generate(FLATTEN_PROMPT.replace("__PASSAGE__", target), TEMP)
        if flat.startswith("[ERROR"):
            n_errors += 1
            time.sleep(INTER_CALL_SLEEP)
            continue
        passed, hard, soft, metrics = fidelity_gate(flat, target)
        if not passed:
            flat2 = generate(FLATTEN_PROMPT.replace("__PASSAGE__", target), TEMP_RETRY)
            if flat2.startswith("[ERROR"):
                n_errors += 1
                time.sleep(INTER_CALL_SLEEP)
                continue
            p2, h2, s2, m2 = fidelity_gate(flat2, target)
            if p2:
                flat, passed, hard, soft, metrics, used_temp = flat2, p2, h2, s2, m2, TEMP_RETRY
            else:
                n_gate_flagged += 1
                if len(gate_flags) < 5:
                    gate_flags.append({"reason": " | ".join(h2),
                                       "excerpt": (flat2[:150]).replace("\n", " ")})
                time.sleep(INTER_CALL_SLEEP)
                continue

        # 5) STREAM the clean pair immediately (crash-safe)
        rec = {
            "id": cid, "bucket": "3", "work": WORK,
            "char_start": c["char_start"], "char_end": c["char_end"],
            "span_text": target, "real_target": target,
            "flattened_input": flat,
            "content_hash": spine.content_hash(target),
            "word_count": c["word_count"],
            "model": MODEL, "temperature": used_temp,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "fidelity": {"passed": passed, "hard": hard, "soft": soft,
                         "metrics": metrics, "garble_check": garble_status},
        }
        spine.append_record(OUT, rec)
        done.add(cid)
        n_clean += 1
        time.sleep(INTER_CALL_SLEEP)

    # ── Lean machine-readable summary (the orchestrating agent reads this) ─────
    print(f"WORK={WORK}")
    print(f"N_MINED={n_mined}")
    print(f"N_SKIPPED_DEFENSIVE={n_skipped_defensive}")
    print(f"N_FLATTENED_CLEAN={n_clean}")
    print(f"N_GATE_FLAGGED={n_gate_flagged}")
    print(f"N_ERRORS={n_errors}")
    print(f"ATTEMPTS={attempts}")
    print(f"COLLISIONS={collisions}")
    print(f"GARBLE_CHECK={garble_status}")
    print(f"OUT={OUT}")
    for g in gate_flags:
        print(f"GATEFLAG :: {g['reason'][:120]} :: {g['excerpt'][:90]}")


if __name__ == "__main__":
    main()
