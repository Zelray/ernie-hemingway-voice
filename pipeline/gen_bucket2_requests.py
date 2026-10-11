"""
gen_bucket2_requests.py — REGENERATE ONLY THE BUCKET-2 REQUESTS (keep the 228 targets).

WHY (plain English):
  Session-5 built 228 Bucket-2 pairs whose TARGETS (real Hemingway) are perfect,
  but whose invented REQUESTS over-concentrated on two openers ("Recount" 37.7% +
  "Show" 37.3% = 75%) and read robotic. Root cause: each request was generated
  BLIND to the others, so the model can't balance a corpus it can't see — it just
  latches onto a favorite verb. Asking the model to "vary" failed twice.

  THE FIX: take the opener choice AWAY from the model. We iterate the 228 EXISTING
  rows (targets/offsets/content_hash untouched) and, for each, the GENERATOR assigns
  the request FORM by the work's LOCAL index, round-robin over six near-universal
  descriptive openers — each a DISTINCT first word, so the distribution lands flat
  (~17% each, top-2 ~33%, under the gate's 45% ceiling). Only `invented_request` is
  replaced; everything precious (the real-Hemingway target, the offset reservation,
  the dedup hash) is carried through verbatim.

FORM-MISFIT -> CYCLE, NEVER DROP (load-bearing):
  Every one of these 228 spans already produced a valid request last session, so
  each is PROVEN answerable. The only NEW failure mode is "the assigned form does
  not fit this span." If that happens (model returns [UNSUITABLE], or fails a
  per-pair check, or disobeys the opener after a temp-retry), we ADVANCE to the next
  form in the rotation and regenerate — we do NOT skip. Skipping would silently
  shrink below 228, and the thin works (mww 36 / three-stories 15 / in-our-time 7)
  cannot be backfilled. The fallback forms are themselves rotation members, so the
  distribution stays balanced. A row is only skipped if it fails ALL six forms,
  which — given it answered once already — should never fire.

REUSES (never reinvents): gen_bucket2.generate (Gemini call + backoff),
  gen_bucket2.request_check (HARD leak/meta/length checks), gen_bucket2.get_key,
  spine.append_record / load_done_ids. NEW prompt = bucket2_request_prompt_v3.txt
  (v3 = re-aim at the bare subject, FORBID enumeration, ban the speaker/narrator
  register, guard against false-merged names; two purple openers swapped — see FORMS).

NEVER-RE-PAY: accepted rows stream to bucket2_v3/<work>.jsonl; on resume the loop
  skips ids already present, so re-runs are cumulative. (If you revise the v3 prompt
  after piloting, delete that work's bucket2_v3/<work>.jsonl first, or the old-prompt
  rows survive as already-done.)

RUN (PowerShell ok):
  python pipeline/gen_bucket2_requests.py --dry                       # plan only, no API/no $
  python pipeline/gen_bucket2_requests.py --work farewell-to-arms --smoke 14   # pilot
  python pipeline/gen_bucket2_requests.py                             # full scale, all works
"""
import os, sys, json, time, string, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine                                       # noqa: E402
genb2 = importlib.import_module("gen_bucket2")     # generate, request_check, get_key, consts

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SRC = os.path.join(HERE, "bucket2_all.jsonl")      # canonical post-merge 228 (NOT pre-merge)
OUT_DIR = os.path.join(HERE, "bucket2_v3")
PROMPT_PATH = os.path.join(HERE, "bucket2_request_prompt_v3.txt")

TEMP = genb2.TEMP                  # 0.7
TEMP_RETRY = genb2.TEMP_RETRY      # 0.9
INTER_CALL_SLEEP = genb2.INTER_CALL_SLEEP
MODEL = genb2.MODEL

# Six near-universal descriptive openers, each a DISTINCT first word so the opener
# distribution stays flat. Assigned round-robin by each work's LOCAL index.
# v3: swapped the two "purple/writerly" openers (Capture, Give me a sense of) that
# drew the most enumeration-leaks for two plainer, more concrete ones (How would you
# describe / Picture). Each remains a DISTINCT first word so the distribution stays flat.
FORMS = [
    {"template": "Describe ___",                "first": "describe"},
    {"template": "Tell me about ___",           "first": "tell"},
    {"template": "What was ___ like?",          "first": "what"},
    {"template": "Show me ___",                 "first": "show"},
    {"template": "How would you describe ___?", "first": "how"},
    {"template": "Picture ___",                 "first": "picture"},
]
NFORMS = len(FORMS)

_PROMPT = None


def get_prompt():
    global _PROMPT
    if _PROMPT is None:
        _PROMPT = open(PROMPT_PATH, encoding="utf-8").read()
    return _PROMPT


def opener_of(text):
    toks = text.split()
    return toks[0].lower().strip(string.punctuation) if toks else ""


def load_by_work():
    rows = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
    by_work = {}
    for r in rows:
        by_work.setdefault(r["work"], []).append(r)
    return rows, by_work


def gen_for_form(target, form):
    """Try ONE form (assigned opener) at TEMP then TEMP_RETRY. Returns
    (request, metrics) on success, or (None, reason) so the caller advances form.
    'unsuitable' / a failed check / opener-disobedience all mean 'form misfit'."""
    prompt = get_prompt().replace("__FORM__", form["template"]).replace("__PASSAGE__", target)
    last = "failed"
    for temp in (TEMP, TEMP_RETRY):
        out = genb2.generate(prompt, temp).strip()
        if out.startswith("[ERROR"):
            last = "error:" + out[:60]
            time.sleep(INTER_CALL_SLEEP)
            continue
        if out.upper().startswith("[UNSUITABLE]"):
            return None, "unsuitable"           # explicit misfit -> next form
        passed, hard, soft, metrics = genb2.request_check(out, target)
        if passed and opener_of(out) == form["first"]:
            metrics["temperature"] = temp
            return out, metrics
        last = ("hard:" + ",".join(hard)) if hard else ("opener:" + opener_of(out))
        time.sleep(INTER_CALL_SLEEP)
    return None, last


def main():
    argv = sys.argv
    dry = "--dry" in argv
    only_work = argv[argv.index("--work") + 1] if "--work" in argv else None
    smoke = int(argv[argv.index("--smoke") + 1]) if "--smoke" in argv else None

    rows, by_work = load_by_work()
    os.makedirs(OUT_DIR, exist_ok=True)

    works = [only_work] if only_work else sorted(by_work)
    for w in works:
        if w not in by_work:
            print(f"[FATAL] no rows for --work {w!r}; have {sorted(by_work)}")
            sys.exit(2)

    if dry:
        print("DRY RUN — assignment plan (no API, no $):")
        for w in works:
            wr = by_work[w]
            plan = {}
            for li in range(len(wr)):
                fw = FORMS[li % NFORMS]["first"]
                plan[fw] = plan.get(fw, 0) + 1
            print(f"  {w}: {len(wr)} rows -> " +
                  ", ".join(f"{k} {v}" for k, v in plan.items()))
        print(f"TOTAL rows = {len(rows)}; forms = {[f['first'] for f in FORMS]}")
        return

    new_this_run = 0
    exhausted = 0
    fallback_used = 0
    samples = []

    for w in works:
        wr = by_work[w]
        OUT = os.path.join(OUT_DIR, w + ".jsonl")
        done = spine.load_done_ids(OUT)
        for li, r in enumerate(wr):                       # li = LOCAL index (stable on resume)
            if smoke is not None and new_this_run >= smoke:
                break
            if r["id"] in done:
                continue
            target = r.get("real_target", r.get("span_text", ""))
            start = li % NFORMS
            picked = None
            for step in range(NFORMS):                    # rotate forward from the assigned form
                form = FORMS[(start + step) % NFORMS]
                req, info = gen_for_form(target, form)
                time.sleep(INTER_CALL_SLEEP)
                if req:
                    picked = (req, form, info, step)
                    break
            if picked is None:
                exhausted += 1                            # should never happen
                spine.append_record(os.path.join(OUT_DIR, "_skip_" + w + ".jsonl"), {
                    "id": r["id"], "work": w, "reason": "all_forms_failed",
                    "regenerated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
                done.add(r["id"])
                continue

            req, form, metrics, step = picked
            if step > 0:
                fallback_used += 1
            rec = dict(r)                                 # carry id/offsets/hash/target verbatim
            rec["invented_request"] = req
            rec["assigned_form"] = form["first"]
            rec["form_fallback_steps"] = step
            rec["model"] = MODEL
            rec["temperature"] = metrics.get("temperature")
            rec["regenerated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            rec["request_check"] = {"metrics": metrics}
            spine.append_record(OUT, rec)
            done.add(r["id"])
            new_this_run += 1
            if len(samples) < 16:
                samples.append((form["first"], step, req[:90]))

    print(f"NEW_THIS_RUN={new_this_run}")
    print(f"FALLBACK_USED={fallback_used}   (rows that needed a form past the assigned one)")
    print(f"EXHAUSTED_ALL_FORMS={exhausted}   (MUST be 0)")
    print(f"OUT_DIR={OUT_DIR}")
    for fw, step, ex in samples:
        print(f"SAMPLE [{fw} +{step}] :: {ex}")


if __name__ == "__main__":
    main()
