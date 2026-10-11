"""
bucket4_cadence_gate.py — the TWO-SIDED cadence judge for Bucket 4.

WHAT (plain English):
  Bucket 4 is the only bucket where Gemini imitates Hemingway, so it is the only place
  caricature can sneak in. This module decides whether ONE generated answer reads like a
  real Hemingway PARAGRAPH — judged against bands measured from 2,310 real ~85-word
  Hemingway chunks (bucket4_style_reference.json, built by build_style_reference.py with
  the SAME splitter we use here, so it is apples-to-apples).

  "Two-sided" = we reject BOTH failure directions, not just one:
    - TOO CHOPPY (the caricature): mean sentence length below the corpus floor, OR no
      flowing sentence at all (the strongest tell — even Hemingway's choppiest real
      paragraphs contain at least one 12+-word sentence), OR an over-long run of fragments,
      OR a fragment rate above anything the real corpus shows.
    - TOO FLOWERY (not him): mean sentence length above the corpus ceiling.

  Both the generator (inline accept/retry) and the final acceptance gate import
  cadence_check() so the same bar is applied at generation time and at promotion time.

WHAT IT CANNOT SEE: whether the answer is actually a GOOD, on-topic answer to the question,
  or whether it is purple/parody at the WORD level (cadence can be perfect while diction is
  cartoonish). Those are caught by the pilot human read + the adversarial review panel — a
  green cadence check is necessary, NOT sufficient.

RUN (Bash):
  python pipeline/bucket4_cadence_gate.py --self-test
  python pipeline/bucket4_cadence_gate.py --src bucket4_pilot.jsonl   # judge a jsonl of answers
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stylometry  # noqa: E402

REF_PATH = os.path.join(HERE, "bucket4_style_reference.json")
ANSWER_FIELDS = ("hemingway_answer", "answer", "output")

# Minimum size for a measurable, real paragraph-answer. Below this we can't judge
# cadence and it isn't a satisfying practical answer either.
MIN_SENTS = 3
MIN_WORDS = 40
# Informational only (the prompt targets ~50-110 words): flag overshoot, don't fail.
SOFT_LONG_WORDS = 150

_REF = None


def load_reference(path=REF_PATH):
    global _REF
    if _REF is None:
        with open(path, encoding="utf-8") as f:
            _REF = json.load(f)
    return _REF


def _answer_of(rec):
    for k in ANSWER_FIELDS:
        if rec.get(k):
            return rec[k]
    return ""


def cadence_check(answer, ref=None):
    """Judge one answer's cadence against the real-Hemingway per-chunk bands.
    Returns (passed: bool, hard: list[str], metrics: dict). The thresholds are read
    LIVE from the frozen reference so the bands and this code can never drift apart."""
    ref = ref or load_reference()
    b = ref["per_chunk_bands"]
    m = stylometry.style_metrics(answer)
    if not m:
        return False, ["empty"], {}

    hard = []
    # ── size: must be a real, measurable paragraph ────────────────────────────
    if m["n_sents"] < MIN_SENTS or m["n_words"] < MIN_WORDS:
        hard.append("too_short")

    # ── TOO-FLOWERY guard (one): mean above the corpus ceiling ────────────────
    if m["mean_len"] > b["mean_len"]["p90"]:
        hard.append("too_flowery_mean")

    # ── TOO-CHOPPY guards (three — caricature is the dominant failure) ─────────
    if m["mean_len"] < b["mean_len"]["p10"]:
        hard.append("too_choppy_mean")
    # the single strongest anti-caricature rule: a real Hemingway paragraph almost
    # always has at least one 12+-word sentence. No flowing sentence => caricature.
    if m["max_len"] < b["max_len"]["p10"]:
        hard.append("no_flowing_sentence")
    # a run of fragments longer than 95% of real Hemingway paragraphs ever show.
    if m["max_consec_frag"] > b["max_consec_frag"]["p95"]:
        hard.append("frag_run")
    # a fragment rate above anything the real corpus reaches.
    if m["frag_rate"] > b["frag_rate"]["p95"]:
        hard.append("too_many_frags")

    m["soft_long"] = m["n_words"] > SOFT_LONG_WORDS   # informational, not gated
    return (not hard), hard, m


def main():
    if "--self-test" in sys.argv:
        ref = load_reference()
        choppy = "It was good. The coffee was hot. He was tired. The road was long. She left. The end."
        flowery = ("When the morning came and the light was on the water and the boats were "
                   "moving out past the breakwater into the long grey swell of the sea, he "
                   "thought that perhaps it would be a fine day after all and that the fish "
                   "would be running and the nets would come back heavy and silver and full.")
        good = ("Start slow. Run in the morning when the streets are empty and the air is cold "
                "in your chest, and do not run far the first day or the second. Walk when you have "
                "to walk. Your legs will hurt and that is all right. Go out the next day and the "
                "day after, and after a while the running is easy and good and you do not think "
                "about it any more.")
        for name, txt in (("choppy", choppy), ("flowery", flowery), ("good", good)):
            ok, hard, m = cadence_check(txt, ref)
            print(f"  {name:8} pass={ok}  hard={hard}")
            print(f"           mean={m.get('mean_len')} max={m.get('max_len')} "
                  f"frag_rate={m.get('frag_rate')} max_run={m.get('max_consec_frag')} "
                  f"and={m.get('and_frac')} nsent={m.get('n_sents')}")
        assert cadence_check(choppy, ref)[0] is False
        assert cadence_check(flowery, ref)[0] is False
        assert cadence_check(good, ref)[0] is True
        print("SELF-TEST PASSED (choppy & flowery rejected, good accepted).")
        return

    src = None
    if "--src" in sys.argv:
        src = os.path.join(HERE, sys.argv[sys.argv.index("--src") + 1])
    if not src or not os.path.exists(src):
        print("usage: python pipeline/bucket4_cadence_gate.py --src <file.jsonl> | --self-test")
        sys.exit(1)

    ref = load_reference()
    rows = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
    passed, fails = 0, []
    reason_counts = {}
    for r in rows:
        ok, hard, m = cadence_check(_answer_of(r), ref)
        if ok:
            passed += 1
        else:
            fails.append({"id": r.get("id"), "hard": hard,
                          "mean_len": m.get("mean_len"), "max_len": m.get("max_len"),
                          "frag_rate": m.get("frag_rate"), "max_run": m.get("max_consec_frag")})
            for h in hard:
                reason_counts[h] = reason_counts.get(h, 0) + 1
    print(json.dumps({
        "src": src, "n": len(rows), "passed": passed, "failed": len(fails),
        "pass_rate": round(passed / max(1, len(rows)), 3),
        "reason_counts": reason_counts, "fails": fails,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
