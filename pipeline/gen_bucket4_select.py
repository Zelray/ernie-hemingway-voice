"""
gen_bucket4_select.py — Gemini SUITABILITY classifier for the Bucket-4 question pool.

WHAT (plain English):
  The deterministic pre-filter (gen_bucket4_pool.py) removed the OBVIOUS unanswerable
  questions. This pass makes the SEMANTIC call the regex can't: can a plain, terse,
  experiential voice answer this question WELL from lived experience / judgment / craft,
  WITHOUT reciting facts, looking something up, enumerating a list, or writing code?
  A Hemingway-voice answer to "what causes tides?" is either a refusal or a hallucination —
  both poison the training set. So we keep only questions where the VOICE can carry a real,
  honest answer.

  INTEGRITY: Gemini returns a VERDICT ONLY (suitable / grade / answer_mode / reason). It
  never rewrites the question. The Hemingway answer is written in a SEPARATE later step.

  ECONOMY: the pool is ~4,842 and we need ~560. We classify the (already-shuffled) pool in
  order and STOP once KEEP_TARGET suitable questions are banked — no need to judge all 4,842.

OUTPUT: pipeline/bucket4_selected.jsonl (verdicts) — suitable rows feed gen_bucket4.py.

RUN (Bash):
  python pipeline/gen_bucket4_select.py --pilot 15   # eyeball verdicts, writes _pilot
  python pipeline/gen_bucket4_select.py              # full run, resumable, early-stops at KEEP_TARGET
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine  # noqa: E402

KEY = open(os.path.join(HERE, "..", "gemini_key.txt"), encoding="utf-8").read().strip()
MODEL = "gemini-2.5-flash"
ROOT = "https://generativelanguage.googleapis.com/v1beta"
TEMP = 0.2                 # classification wants consistency, not creativity
INTER_CALL_SLEEP = 0.7

POOL = os.path.join(HERE, "bucket4_pool.jsonl")
OUT = os.path.join(HERE, "bucket4_selected.jsonl")
PILOT_OUT = os.path.join(HERE, "bucket4_selected_pilot.jsonl")
KEEP_TARGET = 1020         # s12 REBALANCE: was 750 (skewed 447cw/303gq/0oq). Bank ~270 MORE
                           # keepers, now from experiential open_qa, for a practical-majority B4.
MAX_JUDGE = 3000           # hard cap on classification calls (cost bound); open_qa yield is lower
                           # (trivia mixed in) so more headroom needed to bank the practical fill.

PROMPT = """You are curating questions for fine-tuning a model to answer in the writing voice of a plain, terse, experienced narrator (think a laconic war veteran who has lived a lot and says true things simply).

Judge the ONE question below. THE TEST: could a knowledgeable, experienced PERSON give a useful, honest answer from their OWN life, judgment, and know-how — even if imperfect — WITHOUT having to look up an external fact? If yes -> SUITABLE. If answering REQUIRES specific facts/data the person would have to look up -> UNSUITABLE.

SUITABLE (suitable=true) — answerable from a person's own experience and judgment:
  - experiential / emotional: "How do you know when you are in love?", "What makes a good morning?"
  - PRACTICAL HOW-TO / know-how: "How do I start running?", "How do people buy parts for old cars?", "How do you keep a fire going in the rain?"
  - OPINION / preference / advice: "Is it worth moving far from home?", "Is buying a multi-unit property a good first home?", "What's better, the mountains or the sea?"
  - creative / craft: "Write a short scene about a man who loses a fight.", "Write a story about a hidden room."
  When in doubt between a how-to/opinion question and "factual", lean SUITABLE.

UNSUITABLE (suitable=false) — answering REQUIRES reciting external facts, a mechanism, a lookup, a list, math, or code:
  factual/trivia ("capital of Peru", "who wrote Hamlet", "oldest MLB ballpark"), science/how-it-works ("why is the sky blue", "what causes tides", "how does a vaccine work"), definitions ("what is a polygon", "what is an octave"), anything needing specific data/dates/named-entities, list requests, technical/programming.

Grades: "good" = rich, voice-carrying, the model will learn real cadence from the answer; "ok" = answerable in voice but plainer; "weak" = borderline; "reject" = unsuitable.

Return STRICT JSON ONLY, no prose, no code fence:
{"suitable": true|false, "grade": "good"|"ok"|"weak"|"reject", "answer_mode": "experiential"|"opinion"|"practical"|"creative"|"emotional"|"factual"|"technical"|"list", "reason": "<one short clause>"}

QUESTION:
\"\"\"__Q__\"\"\""""


def generate(prompt, retries=4):
    url = f"{ROOT}/models/{MODEL}:generateContent?key={KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": TEMP, "maxOutputTokens": 200,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return f"[ERROR HTTP {e.code}]"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return f"[ERROR {type(e).__name__}]"


def parse_verdict(raw):
    if raw.startswith("[ERROR"):
        return {"grade": "api_error", "reason": raw}
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"grade": "parse_error", "reason": raw[:120]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"grade": "parse_error", "reason": raw[:120]}


# s12 REBALANCE: creative_writing (616) + most general_qa are already judged from the first
# run (banked 447cw/303gq). Re-point priority at the still-UN-judged experiential open_qa so the
# resume judges THOSE first and banks the practical/experiential fill. creative_writing keepers
# get CAPPED at ~200 downstream (bucket4_to_generate.py), so we don't want to judge more of it.
CAT_PRIORITY = {"open_qa": 0, "general_qa": 1, "creative_writing": 2}


def load_pool(order_by_priority=False):
    rows = [json.loads(l) for l in open(POOL, encoding="utf-8") if l.strip()]
    if order_by_priority:
        rows.sort(key=lambda r: CAT_PRIORITY.get(r["category"], 9))
    return rows


def _keeper(v):
    return bool(v.get("suitable")) and v.get("grade") in ("good", "ok")


def judge(rows, out_path, resume=True, early_stop=None, max_judge=None):
    done = spine.load_done_ids(out_path) if resume else set()
    if not resume and os.path.exists(out_path):
        os.remove(out_path)
    # count keepers already banked (for resume + early-stop)
    banked = 0
    if resume and os.path.exists(out_path):
        for l in open(out_path, encoding="utf-8"):
            l = l.strip()
            if l:
                try:
                    if _keeper(json.loads(l)):
                        banked += 1
                except json.JSONDecodeError:
                    pass
    n = 0
    for r in rows:
        if early_stop and banked >= early_stop:
            break
        if max_judge and n >= max_judge:
            break
        if r["id"] in done:
            continue
        verdict = parse_verdict(generate(PROMPT.replace("__Q__", r["instruction"])))
        rec = dict(r)
        rec["suitable"] = verdict.get("suitable")
        rec["grade"] = verdict.get("grade", "parse_error")
        rec["answer_mode"] = verdict.get("answer_mode", "")
        rec["sel_reason"] = verdict.get("reason", "")
        spine.append_record(out_path, rec)
        n += 1
        if _keeper(rec):
            banked += 1
        time.sleep(INTER_CALL_SLEEP)
    return n, banked


def summarize(out_path):
    recs = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
    by_grade, by_mode, by_cat = {}, {}, {}
    keep_by_cat = {}
    for r in recs:
        by_grade[r["grade"]] = by_grade.get(r["grade"], 0) + 1
        by_mode[r.get("answer_mode", "")] = by_mode.get(r.get("answer_mode", ""), 0) + 1
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        if _keeper(r):
            keep_by_cat[r["category"]] = keep_by_cat.get(r["category"], 0) + 1
    keepers = sum(1 for r in recs if _keeper(r))
    print(f"\njudged: {len(recs)}   keepers(suitable good|ok): {keepers}")
    print(f"by grade: {by_grade}")
    print(f"by answer_mode: {by_mode}")
    print(f"keepers by category: {keep_by_cat}")
    return recs


def show(r):
    q = r["instruction"]
    q = (q[:90] + "…") if len(q) > 90 else q
    keep = "KEEP" if _keeper(r) else "drop"
    return f"  [{keep}] {r['grade']:>6} {r.get('answer_mode',''):<12} | {q}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0)
    args = ap.parse_args()

    if args.pilot:
        # category-MIXED pilot: round-robin across categories so we validate the
        # prompt on creative/general/open alike, not just the open_qa-heavy head.
        rows = load_pool()
        by_cat = {}
        for r in rows:
            by_cat.setdefault(r["category"], []).append(r)
        sample, i = [], 0
        cats = list(by_cat)
        while len(sample) < args.pilot:
            c = cats[i % len(cats)]
            if by_cat[c]:
                sample.append(by_cat[c].pop(0))
            i += 1
            if i > args.pilot * len(cats):
                break
        print(f"PILOT: judging {len(sample)} category-mixed questions…")
        judge(sample, PILOT_OUT, resume=False)
        recs = [json.loads(l) for l in open(PILOT_OUT, encoding="utf-8") if l.strip()]
        print("\n--- PILOT VERDICTS ---")
        for r in recs:
            print(show(r))
        summarize(PILOT_OUT)
    else:
        rows = load_pool(order_by_priority=True)
        print(f"FULL RUN: classifying up to {MAX_JUDGE}, early-stop at {KEEP_TARGET} keepers (resumable)…")
        added, banked = judge(rows, OUT, resume=True, early_stop=KEEP_TARGET, max_judge=MAX_JUDGE)
        print(f"added {added} new verdicts; keepers banked = {banked}")
        summarize(OUT)
