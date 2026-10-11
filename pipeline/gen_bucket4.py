"""
gen_bucket4.py — BUCKET-4 (practical Q&A) Hemingway-voice ANSWER generator.

WHAT (plain English):
  Bucket 4 is the ONE bucket where Gemini IMITATES Hemingway. The questions are real
  Dolly questions a terse experiential voice can answer well (selected by
  gen_bucket4_select.py, capped/balanced by bucket4_to_generate.py). For each, Gemini
  writes a ~75-100-word answer in Hemingway's voice using the panel-built prompt
  (bucket4_answer_prompt.txt). Caricature is quarantined HERE, so every answer must
  pass the two-sided cadence gate INLINE before we keep it.

  INLINE ACCEPT = bucket4_cadence_gate.cadence_check(answer) passes (not too choppy /
  not too flowery / a real paragraph). Generate at temp 0.6; on cadence-fail retry
  ONCE at 0.9 to decorrelate; if it still fails, DON'T keep a caricature — log the row
  to bucket4_needs_fix.jsonl for hand-handling. The gate is NECESSARY-not-SUFFICIENT:
  it cannot see off-topic answers or word-level parody. The pilot read + the
  adversarial panel are the real catches (see panel pilot_watchpoints).

NEVER-RE-PAY: accepted rows stream to bucket4/<category>.jsonl; on resume the loop
  skips ids already present. Re-runs are cumulative and converge. (Revise the prompt
  after piloting? Delete the per-category files first or old-prompt rows survive.)

RUN (Bash; PowerShell hangs this box):
  python pipeline/gen_bucket4.py --dry            # plan only, no API / no $
  python pipeline/gen_bucket4.py --pilot 30       # ~30 category-mixed -> _pilot, yield+diagnostics
  python pipeline/gen_bucket4.py                  # full run, resumable
"""
import os, sys, json, time, re, importlib
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine                                              # noqa: E402
import bucket4_cadence_gate as cg                         # noqa: E402  cadence_check
genb2 = importlib.import_module("gen_bucket2")            # reuse the proven Gemini call

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SRC = os.path.join(HERE, "bucket4_to_generate.jsonl")
OUT_DIR = os.path.join(HERE, "bucket4")
PILOT_OUT = os.path.join(HERE, "bucket4_pilot.jsonl")
NEEDS_FIX = os.path.join(HERE, "bucket4_needs_fix.jsonl")
PROMPT_PATH = os.path.join(HERE, "bucket4_answer_prompt.txt")

TEMP = 0.6                       # imitation wants a little warmth; not as loose as invention
TEMP_RETRY = 0.9                 # decorrelate the one cadence retry
INTER_CALL_SLEEP = genb2.INTER_CALL_SLEEP
MODEL = genb2.MODEL

# Cheap, INFORMATIONAL pilot diagnostics (not gates) — the panel watchpoints. We flag,
# the human read decides. Example-anchor tokens: if a generation echoes a worked-example
# subject (flat tire / found letter / cast iron) that is "copied subject, not shape".
_EXAMPLE_BLEED = re.compile(
    r"\b(tire|tube|patch|puncture|thorn|"               # [A] flat tire
    r"coat|closet|letter|pocket|ink|"                   # [B] found letter
    r"cast iron|nonstick|skillet|the iron)\b", re.I)
# Purple Hemingway props that should NOT be shoehorned into a practical answer.
_PURPLE_PROPS = re.compile(r"\b(bullfight\w*|matador|cafe|café|trench\w*|the war|the front)\b", re.I)

_PROMPT = None


def get_prompt():
    global _PROMPT
    if _PROMPT is None:
        _PROMPT = open(PROMPT_PATH, encoding="utf-8").read()
    return _PROMPT


def build_prompt(question):
    return get_prompt().replace("__QUESTION__", question)


def clean_answer(raw):
    """Defensive: strip wrapping quotes / a stray code fence the model may add.
    The prompt forbids preambles; real preamble leakage is caught downstream."""
    out = raw.strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-z]*\n?|\n?```$", "", out).strip()
    out = out.strip().strip('"').strip("'").strip()
    return out


def gen_one(question):
    """temp 0.6 then ONE retry at 0.9. Returns (answer, metrics, temp) or (None, reason, None)."""
    prompt = build_prompt(question)
    last = "failed"
    for temp in (TEMP, TEMP_RETRY):
        out = genb2.generate(prompt, temp)
        if out.startswith("[ERROR"):
            last = "error:" + out[:60]
            time.sleep(INTER_CALL_SLEEP)
            continue
        ans = clean_answer(out)
        ok, hard, metrics = cg.cadence_check(ans)
        if ok:
            metrics["temperature"] = temp
            return ans, metrics, temp
        last = "cadence:" + ",".join(hard) + " :: " + ans[:70]
        time.sleep(INTER_CALL_SLEEP)
    return None, last, None


def load_src():
    return [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]


def mixed_sample(rows, n):
    """Round-robin across categories so the pilot spans creative/general/open alike."""
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    out, i, cats = [], 0, list(by_cat)
    while len(out) < n and any(by_cat.values()):
        c = cats[i % len(cats)]
        if by_cat[c]:
            out.append(by_cat[c].pop(0))
        i += 1
    return out


def make_record(r, ans, metrics, temp):
    return {
        "id": r["id"],
        "bucket": 4,
        "category": r["category"],
        "answer_mode": r.get("answer_mode", ""),
        "grade": r.get("grade", ""),
        "instruction": r["instruction"],
        "hemingway_answer": ans,
        "content_hash": spine.content_hash(ans),
        "model": MODEL,
        "temperature": temp,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cadence": {k: metrics.get(k) for k in
                    ("mean_len", "max_len", "frag_rate", "max_consec_frag", "and_frac",
                     "n_sents", "n_words", "soft_long")},
    }


def pilot_diagnostics(recs):
    """Print the panel pilot_watchpoints as cheap automated flags (informational)."""
    print("\n--- PILOT DIAGNOSTICS (watchpoints; flags are informational, the read decides) ---")
    n = len(recs)
    print(f"generated+passed cadence: {n}")
    print(f"  by category : {dict(Counter(r['category'] for r in recs))}")
    means = [r['cadence']['mean_len'] for r in recs]
    maxes = [r['cadence']['max_len'] for r in recs]
    words = [r['cadence']['n_words'] for r in recs]
    if n:
        print(f"  mean_len    : min {min(means)} / avg {round(sum(means)/n,1)} / max {max(means)}")
        print(f"  longest sent: min {min(maxes)} / max {max(maxes)}   words: avg {round(sum(words)/n)}")
    openers = Counter(r['hemingway_answer'].split()[0].lower().strip('.,') for r in recs if r['hemingway_answer'])
    print(f"  top openers : {openers.most_common(6)}")
    closers = Counter(r['hemingway_answer'].rstrip().split('.')[-2].strip().split()[0].lower()
                      for r in recs if r['hemingway_answer'].count('.') >= 2)
    print(f"  closer 1st-words: {closers.most_common(6)}")
    bleed = [r['id'] for r in recs if _EXAMPLE_BLEED.search(r['hemingway_answer'])]
    purple = [r['id'] for r in recs if _PURPLE_PROPS.search(r['hemingway_answer'])]
    soft_long = [r['id'] for r in recs if r['cadence'].get('soft_long')]
    print(f"  ⚑ example-bleed (flat tire/letter/cast iron tokens): {len(bleed)} {bleed[:6]}")
    print(f"  ⚑ purple-prop (war/cafe/bullfight tokens)         : {len(purple)} {purple[:6]}")
    print(f"  ⚑ over-110-word (soft_long)                       : {len(soft_long)}")


def main():
    argv = sys.argv
    dry = "--dry" in argv
    pilot_n = int(argv[argv.index("--pilot") + 1]) if "--pilot" in argv else 0

    rows = load_src()
    run_rows = mixed_sample(rows, pilot_n) if pilot_n else rows

    if dry:
        print("DRY RUN — no API, no $")
        print(f"SRC={SRC}  rows={len(rows)}")
        print(f"  by category: {dict(Counter(r['category'] for r in rows))}")
        print(f"ROWS_THIS_RUN={len(run_rows)}  PILOT={bool(pilot_n)}")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    if pilot_n and os.path.exists(PILOT_OUT):
        os.remove(PILOT_OUT)

    accepted, failed = [], 0
    for r in run_rows:
        out_path = PILOT_OUT if pilot_n else os.path.join(OUT_DIR, r["category"] + ".jsonl")
        if not pilot_n and r["id"] in spine.load_done_ids(out_path):
            continue
        ans, info, temp = gen_one(r["instruction"])
        time.sleep(INTER_CALL_SLEEP)
        if ans is None:
            failed += 1
            spine.append_record(NEEDS_FIX, {**r, "fail_reason": info})
            print(f"  [needs_fix] {r['id']} :: {info}")
            continue
        rec = make_record(r, ans, info, temp)
        spine.append_record(out_path, rec)
        accepted.append(rec)

    attempted = len(accepted) + failed
    print(f"\nACCEPTED={len(accepted)}  NEEDS_FIX={failed}  ATTEMPTED_THIS_RUN={attempted}")
    if attempted:
        print(f"INLINE CADENCE YIELD = {round(100*len(accepted)/attempted)}%")
    print(f"OUT={'PILOT:'+PILOT_OUT if pilot_n else OUT_DIR}   NEEDS_FIX_LOG={NEEDS_FIX}")

    if pilot_n and accepted:
        pilot_diagnostics(accepted)
        print("\n--- PILOT PAIRS (read each: does it ANSWER? caricature/purple at WORD level? example-bleed?) ---")
        for r in accepted:
            print(f"\n{r['id']}  [{r['category']}/{r.get('answer_mode','')}]  "
                  f"mean={r['cadence']['mean_len']} long={r['cadence']['max_len']} "
                  f"frag={r['cadence']['frag_rate']} words={r['cadence']['n_words']}")
            print(f"  Q: {r['instruction']}")
            print(f"  A: {r['hemingway_answer']}")


if __name__ == "__main__":
    main()
