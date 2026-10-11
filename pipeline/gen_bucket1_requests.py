"""
gen_bucket1_requests.py — BUCKET-1 (reflective Q&A) QUESTION inventor (D2).

WHAT (plain English):
  Bucket 1 is the back-translation bucket. The ANSWERS are 21 curated REAL
  Hemingway reflective passages (bucket1_targets.jsonl). This script invents the
  QUESTION for each — the short, sincere question a real person would type that
  the passage perfectly answers. Each training pair is  question -> real :
    - REAL Hemingway span = the training TARGET (genuine voice, never imitated).
    - Gemini INVENTS the matching question = the training INPUT.

  This is gen_bucket2_requests.py INVERTED: there Gemini wrote a "describe X"
  request; here it writes a reflective QUESTION. We REUSE gen_bucket2's proven
  Gemini call + leak/meta detectors, and add a B1 question_check (must end in
  '?', no quiz/meta register, no crude wording leak).

THE HARD PART (the leak<->natural<->answerable triangle, tighter than B2):
  - too specific  -> the question leaks the passage's payoff (its punch word);
  - too general   -> the passage stops being THE answer (fits a thousand spans).
  The mechanical question_check catches only CRUDE leaks (>=2-word runs) and the
  quiz/meta register. It is BLIND to a single payoff word and to answerability —
  those are caught by the FULL human read + the adversarial panel downstream.

HINTS ARE TOPIC-GRAVITY ONLY: each target carries a question_kind hint from the
  selector. Those hints were graded for "what could this answer", NOT for leak-
  safety, so several point straight at the payoff word (seed: "brave") or mis-aim
  (aficion: "What is passion?" — that span is about telling real devotion from
  fake). The hint is fed as a loose topic tag, explicitly OUTRANKED by the oblique
  /non-leak rule, and --no-hint drops it entirely (use the A/B to decide).

NEVER-RE-PAY: accepted rows stream to bucket1_requests/<work>.jsonl; on resume the
  loop skips ids already present. Re-runs are cumulative. (If you revise the prompt
  after piloting, delete the per-work file first or old-prompt rows survive.)

RUN (Bash; PowerShell hangs this box):
  python pipeline/gen_bucket1_requests.py --dry              # plan only, no API/no $
  python pipeline/gen_bucket1_requests.py --pilot            # 7 hint-trap rows -> _pilot file
  python pipeline/gen_bucket1_requests.py --pilot --no-hint  # same 7, hint dropped (A/B)
  python pipeline/gen_bucket1_requests.py                    # full run, all 21, resumable
"""
import os, sys, json, time, re, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine                                            # noqa: E402
import fidelity_gate                                    # noqa: E402  normalize_quotes
genb2 = importlib.import_module("gen_bucket2")          # generate, detectors, consts

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SRC = os.path.join(HERE, "bucket1_targets.jsonl")
OUT_DIR = os.path.join(HERE, "bucket1_requests")
PILOT_OUT = os.path.join(HERE, "bucket1_requests_pilot.jsonl")
PROMPT_PATH = os.path.join(HERE, "bucket1_question_prompt.txt")

TEMP = genb2.TEMP                  # 0.7 — natural variety
TEMP_RETRY = genb2.TEMP_RETRY      # 0.9 — decorrelate the one retry
INTER_CALL_SLEEP = genb2.INTER_CALL_SLEEP
MODEL = genb2.MODEL

# Pilot = the HINT-TRAP rows (advisor): payoff-word hint (seed/brave), known leak
# history (silk-worms), mis-aimed hint (aficion/"What is passion?"), abstract
# "nature of X" drifters, a grade-A oblique, plus the 3-word "How to live?".
PILOT_IDS = [
    "b1_farewell-to-arms_00354095",   # seed; hint "brave" = payoff word
    "b1_men-without-women_00220659",  # silk-worms; known leak history
    "b1_the-sun-also-rises_00186063", # aficion; hint "What is passion?" MIS-AIMS
    "b1_farewell-to-arms_00188030",   # "nature of denial" — abstract drifter
    "b1_farewell-to-arms_00322003",   # "judgment from afar" (grade A) — abstract
    "b1_the-sun-also-rises_00212553", # "How to live?" (grade A) — tiny question
    "b1_farewell-to-arms_00353567",   # loneliness (grade A); hint word "lonely"
]

# Quiz/literary register the B2 meta check doesn't already ban (it covers
# narrator/story/etc). A reflective QUESTION must never name the speaking subject
# as a literary object. CONSERVATIVE on purpose: we OMIT "figure" (false-positive
# on "figure out") and "character" (false-positive on "what builds character?") —
# both have a dominant everyday sense in a sincere life-question. The remaining
# words are almost never natural in one; the human read + panel catch the rest.
_B1_QUIZ_RE = re.compile(r"\b(speaker|protagonist|persona)\b", re.IGNORECASE)

_PROMPT = None


def get_prompt():
    global _PROMPT
    if _PROMPT is None:
        _PROMPT = open(PROMPT_PATH, encoding="utf-8").read()
    return _PROMPT


def build_prompt(target, question_kind, use_hint):
    hint_block = ""
    if use_hint and question_kind:
        hint_block = (
            'A rough topic tag for this passage is: "' + question_kind + '". '
            "Use it ONLY to locate the area of life the passage is about. Do NOT echo "
            "it as your question, do NOT reuse any of its words that also appear in the "
            "passage, and ignore it entirely if a truer question fits the passage itself.\n"
        )
    return get_prompt().replace("__HINT__", hint_block).replace("__PASSAGE__", target)


def _b1_meta_hit(q_norm):
    hit = genb2._meta_hit(q_norm)
    if hit:
        return hit
    m = _B1_QUIZ_RE.search(q_norm)
    return ("quiz:" + m.group(1).lower()) if m else None


def question_check(question, target):
    """Grade an invented question against its real-Hemingway target.
    Returns (passed, hard, metrics). HARD reasons:
      no_qmark / multi_sentence / newline / length([3,30]) — degenerate shape.
      meta  -> names a source / act of writing / quiz register.
      leak  -> >=5-word containment OR >=3 non-stopword contiguous run (CRUDE leak
               only; a single payoff-word leak is NOT catchable here)."""
    raw = question.strip()
    q_norm = fidelity_gate.normalize_quotes(raw)
    t_norm = fidelity_gate.normalize_quotes(target)
    hard, metrics = [], {}

    words = q_norm.split()
    wc = len(words)
    metrics["word_count"] = wc

    if not raw.endswith("?"):
        hard.append("no_qmark")
    if "\n" in raw:
        hard.append("newline")
    if genb2._is_multi_sentence(raw):
        hard.append("multi_sentence")
    if wc < 3 or wc > 30:
        hard.append("length")

    mh = _b1_meta_hit(q_norm)
    if mh:
        metrics["meta_hit"] = mh
        hard.append("meta")

    cont = spine.containment(q_norm, t_norm, n=5)
    run = genb2._contiguous_run_leak(q_norm, t_norm)
    metrics["containment_5"] = round(cont, 3)
    if run:
        metrics["leak_run"] = run
    if cont > 0 or run:
        hard.append("leak")

    return (not hard), hard, metrics


def gen_one(target, question_kind, use_hint):
    """Try TEMP then TEMP_RETRY. Returns (question, metrics, temp) or (None, reason, None)."""
    prompt = build_prompt(target, question_kind, use_hint)
    last = "failed"
    for temp in (TEMP, TEMP_RETRY):
        out = genb2.generate(prompt, temp).strip()
        if out.startswith("[ERROR"):
            last = "error:" + out[:60]
            time.sleep(INTER_CALL_SLEEP)
            continue
        out = out.strip().strip('"').strip("'").strip()   # drop wrapping quotes the model adds
        passed, hard, metrics = question_check(out, target)
        if passed:
            metrics["temperature"] = temp
            return out, metrics, temp
        last = "hard:" + ",".join(hard) + " :: " + out[:80]
        time.sleep(INTER_CALL_SLEEP)
    return None, last, None


def load_targets():
    return [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]


def main():
    argv = sys.argv
    dry = "--dry" in argv
    pilot = "--pilot" in argv
    use_hint = "--no-hint" not in argv

    targets = load_targets()
    by_id = {t["id"]: t for t in targets}
    rows = [by_id[i] for i in PILOT_IDS if i in by_id] if pilot else targets

    if dry:
        print("DRY RUN — no API, no $")
        print(f"SRC={SRC}")
        print(f"TARGETS={len(targets)}  ROWS_THIS_RUN={len(rows)}  PILOT={pilot}  USE_HINT={use_hint}")
        for t in rows:
            recomputed = spine.content_hash(t["span_text"])
            ok = "OK " if recomputed == t["content_hash"] else "HASH-DRIFT!"
            print(f"  [{ok}] {t['id']}  qk='{t.get('question_kind','')[:42]}'")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    if pilot and os.path.exists(PILOT_OUT):
        os.remove(PILOT_OUT)

    new_this_run = 0
    failed = 0
    samples = []
    for t in rows:
        # content_hash integrity (advisor): a target must never silently drift.
        if spine.content_hash(t["span_text"]) != t["content_hash"]:
            print(f"[FATAL] content_hash drift for {t['id']} — refusing to write")
            sys.exit(3)

        OUT = PILOT_OUT if pilot else os.path.join(OUT_DIR, t["work"] + ".jsonl")
        if t["id"] in spine.load_done_ids(OUT):
            continue

        q, info, temp = gen_one(t["span_text"], t.get("question_kind", ""), use_hint)
        time.sleep(INTER_CALL_SLEEP)
        if q is None:
            failed += 1
            print(f"  [FAIL] {t['id']} :: {info}")
            continue

        rec = dict(t)                                  # carry id/offsets/hash/target/grade/qk verbatim
        rec["invented_question"] = q
        rec["used_hint"] = use_hint
        rec["model"] = MODEL
        rec["temperature"] = temp
        rec["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        rec["question_check"] = {"metrics": info}
        spine.append_record(OUT, rec)
        new_this_run += 1
        samples.append((t["id"], t["work"], t.get("question_kind", ""), q, t["span_text"]))

    print(f"\nNEW_THIS_RUN={new_this_run}")
    print(f"FAILED={failed}")
    print(f"OUT={'PILOT:' + PILOT_OUT if pilot else OUT_DIR}")
    print("\n--- PAIRS (read each Q against the FULL A: non-leaky? answerable? natural?) ---")
    for i, w, qk, q, tgt in samples:
        print(f"\n{i}  [{w}]")
        print(f"  hint: {qk}")
        print(f"  Q:    {q}")
        print(f"  A:    {tgt}")


if __name__ == "__main__":
    main()
