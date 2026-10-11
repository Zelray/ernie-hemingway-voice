"""
Bucket-1 SELECTOR — Gemini precision-sorts the wide-net candidate pool.

The miner SLICED (bucket1_candidates.jsonl); Gemini SORTS. This is a legit
"understanding" use: judging whether a REAL Hemingway span is answer-shaped
reflective prose. Distinguishing "I did not care what it was all about"
(reflection) from "I gave him a dollar and a half" (narration) is semantic —
exactly what a lexical scorer can't do.

INTEGRITY: Gemini returns a VERDICT ONLY (grade + question-kind hint + reason).
It NEVER returns passage text — the target stays the offset-sliced span. The
back-translated QUESTION is invented in a SEPARATE later step, not here.

USAGE:
  python pipeline/gen_bucket1_select.py --pilot 15   # eyeball verdicts, writes _pilot
  python pipeline/gen_bucket1_select.py               # full run, resumable
"""
import os
import re
import sys
import time
import json
import argparse
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine  # noqa: E402

KEY = open(os.path.join(HERE, "..", "gemini_key.txt"), encoding="utf-8").read().strip()
MODEL = "gemini-2.5-flash"
ROOT = "https://generativelanguage.googleapis.com/v1beta"
TEMP = 0.2                 # classification wants consistency, not creativity
INTER_CALL_SLEEP = 0.7

CANDS = os.path.join(HERE, "bucket1_candidates.jsonl")
OUT = os.path.join(HERE, "bucket1_selected.jsonl")
PILOT_OUT = os.path.join(HERE, "bucket1_selected_pilot.jsonl")

PROMPT = """You are curating fine-tuning data: REAL Ernest Hemingway passages that work as ANSWER-SHAPED REFLECTIVE prose — a passage that could stand alone as a thoughtful answer to a question a person might ask about life, war, love, courage, fear, loss, or how to live.

Judge the ONE passage below. ACCEPT only if BOTH hold:
 (a) REFLECTIVE — it makes a GENERAL observation about life / people / the world / the human condition, OR is a first-person MEDITATION on meaning, feeling, or how to live. NOT a report of specific physical events or actions, and NOT scene description.
 (b) SELF-CONTAINED & ANSWER-SHAPED — it stands on its own (no dangling pronoun or reference to missing context) and reads like it could ANSWER a question, not narrate a plot.

REJECT if it is: narration of action/events ("he took...", "we went...", "she made..."), physical or scene description, dialogue/conversation, a fragment needing prior context, or plot exposition — EVEN IF it contains words like "one", "people", "nobody", "no one".

Grades: "A" = strong, resonant reflective answer; "B" = clearly reflective but mild or short; "C" = borderline; "reject" = not reflective/answer-shaped.

Return STRICT JSON ONLY, no prose, no code fence:
{"reflective": true|false, "answer_shaped": true|false, "grade": "A"|"B"|"C"|"reject", "question_kind": "<the kind of question this could answer, <=12 words, or empty>", "reason": "<one short clause>"}

PASSAGE:
\"\"\"__SPAN__\"\"\""""


def generate(prompt, retries=4):
    url = f"{ROOT}/models/{MODEL}:generateContent?key={KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": TEMP, "maxOutputTokens": 300,
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
    """Extract the first {...} JSON object; tolerate code fences / stray prose."""
    if raw.startswith("[ERROR"):
        return {"grade": "api_error", "reason": raw}
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"grade": "parse_error", "reason": raw[:120]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"grade": "parse_error", "reason": raw[:120]}


def load_cands():
    rows = []
    for line in open(CANDS, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def judge(rows, out_path, resume=True):
    done = spine.load_done_ids(out_path) if resume else set()
    if not resume and os.path.exists(out_path):
        os.remove(out_path)
    n = 0
    for r in rows:
        if r["id"] in done:
            continue
        prompt = PROMPT.replace("__SPAN__", r["span_text"])
        verdict = parse_verdict(generate(prompt))
        rec = {
            "id": r["id"], "work": r["work"],
            "char_start": r["char_start"], "char_end": r["char_end"],
            "span_text": r["span_text"], "word_count": r["word_count"],
            "content_hash": r["content_hash"], "span_mode": r["span_mode"],
            "reflect_score": r["reflect_score"],
            "grade": verdict.get("grade", "parse_error"),
            "reflective": verdict.get("reflective"),
            "answer_shaped": verdict.get("answer_shaped"),
            "question_kind": verdict.get("question_kind", ""),
            "sel_reason": verdict.get("reason", ""),
        }
        spine.append_record(out_path, rec)
        n += 1
        time.sleep(INTER_CALL_SLEEP)
    return n


def stratified(rows, k):
    """Sample k rows evenly across the score-ranked pool (rows already score-sorted)."""
    if k >= len(rows):
        return rows
    step = len(rows) / k
    return [rows[int(i * step)] for i in range(k)]


def summarize(out_path):
    recs = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
    by_grade = {}
    for r in recs:
        by_grade[r["grade"]] = by_grade.get(r["grade"], 0) + 1
    print(f"\njudged: {len(recs)}   by grade: {by_grade}")
    keepers = [r for r in recs if r["grade"] in ("A", "B")]
    print(f"keepers (A+B): {len(keepers)}")
    bw = {}
    for r in keepers:
        bw[r["work"]] = bw.get(r["work"], 0) + 1
    print(f"keepers by work: {bw}")
    return recs


def show(r):
    t = r["span_text"]
    t = (t[:130] + "…") if len(t) > 130 else t
    return (f"  [{r['grade']:>6}] score{r['reflect_score']:>6} {r['span_mode']:<8} "
            f"qk='{r.get('question_kind','')[:38]}' | {t}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0, help="stratified sample size; writes _pilot, prints verdicts")
    args = ap.parse_args()
    rows = load_cands()

    if args.pilot:
        sample = stratified(rows, args.pilot)
        print(f"PILOT: judging {len(sample)} stratified spans (of {len(rows)})…")
        judge(sample, PILOT_OUT, resume=False)
        recs = [json.loads(l) for l in open(PILOT_OUT, encoding="utf-8") if l.strip()]
        recs.sort(key=lambda r: r["reflect_score"], reverse=True)
        print("\n--- PILOT VERDICTS (high score -> low) ---")
        for r in recs:
            print(show(r))
        summarize(PILOT_OUT)
    else:
        print(f"FULL RUN: judging {len(rows)} candidates (resumable)…")
        added = judge(rows, OUT, resume=True)
        print(f"added {added} new verdicts")
        summarize(OUT)
