"""
06_bucket3_generate.py — BUCKET-3 (flatten-restore) PAIR generator for ONE work.

WHY THIS EXISTS (plain English):
  04_mine_passages.py found the clean real-Hemingway spans (the training TARGETs).
  05_dress_rehearsal_flatten.py PROVED, on 22 hand-vetted spans, that Gemini can
  FLATTEN a span into voiceless bureaucratic prose (the training INPUT) and that an
  automated FIDELITY GATE catches the failures that matter. This script is the real
  production run for a SINGLE work: it mines that work's clean spans, flattens each
  one, gates each pair, and STREAMS every clean pair to disk crash-safely.

  It REUSES, never reinvents:
    - 04_mine_passages.mine_work / span_is_clean / build_reserved_registry  (the spans)
    - 05_dress_rehearsal_flatten.generate / FLATTEN_PROMPT                  (the flatten)
    - fidelity_gate.fidelity_gate                                          (the DE-NOISED gate)
    - spine.append_record / load_done_ids / content_hash                   (integrity)

  Defensive belt-and-suspenders: every span is re-checked through span_is_clean
  immediately before flattening, so even a straggler that slipped the miner is
  dropped. With a ~50-span cushion above the cap, skipping a few costs nothing.

RUN (Bash; PowerShell hangs this box):
  python pipeline/06_bucket3_generate.py --dry     # no API: show what WOULD generate
  python pipeline/06_bucket3_generate.py           # real paid run (pre-approved)
"""
import os
import sys
import json
import time
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Reuse the proven modules (filenames start with a digit -> import via importlib).
miner = importlib.import_module("04_mine_passages")
flat = importlib.import_module("05_dress_rehearsal_flatten")
from fidelity_gate import fidelity_gate          # noqa: E402  (the DE-NOISED gate)
from spine import append_record, load_done_ids   # noqa: E402

# ── This run's parameters ─────────────────────────────────────────────────────
WORK = "men-without-women"
CAP = 115                                          # carrier cap — do NOT exceed
OUT = os.path.join(HERE, "bucket3", f"{WORK}.jsonl")
DRESS = os.path.join(HERE, "dress_rehearsal_pairs.jsonl")
PACE_SECONDS = 1.5                                 # courtesy gap (parallel generators)
MAX_ATTEMPTS = 2                                   # original + 1 regeneration on a HARD flag


def dress_done_ids(work):
    """IDs of this work's ALREADY-PROVEN dress-rehearsal pairs. They share the
    miner's id scheme (b3_<work>_<offset>), so seeding them into the skip set means
    we never re-pay Gemini for them nor write a content-duplicate target."""
    ids = set()
    if not os.path.exists(DRESS):
        return ids
    with open(DRESS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("work") == work and r.get("flattened_input"):
                ids.add(r["id"])
    return ids


def main():
    dry = "--dry" in sys.argv

    # 1) Mine this work's clean bucket-3 spans (uncapped supply -> the cushion).
    reg, _reserved = miner.build_reserved_registry()
    spans, _coll = miner.mine_work(WORK, reg, bucket="3", cap=None)
    n_mined = len(spans)

    # Skip set = already-streamed rows (idempotent resume) + proven dress pairs.
    skip = load_done_ids(OUT) | dress_done_ids(WORK)
    rows_in_out = len(load_done_ids(OUT))          # respect cap across resumes

    n_streamed = 0
    n_skipped_defensive = 0
    n_gate_flagged = 0
    n_errors = 0
    gate_flags = []

    for span in spans:
        if rows_in_out >= CAP:
            break
        sid = span["id"]
        if sid in skip:
            continue

        target = span["span_text"]

        # 2) DEFENSIVE re-check (belt-and-suspenders) before spending a cent.
        if not miner.span_is_clean(target, WORK):
            n_skipped_defensive += 1
            continue

        if dry:
            # Pretend we would generate; count toward the cap so --dry mirrors the
            # real run's stopping point without calling the API.
            rows_in_out += 1
            n_streamed += 1
            continue

        # 3 + 4) Flatten, gate, regenerate once on a HARD flag, else SKIP.
        prompt = flat.FLATTEN_PROMPT.replace("__PASSAGE__", target)
        streamed = False
        last_reason = None
        last_excerpt = ""
        for _attempt in range(MAX_ATTEMPTS):
            flat_text = flat.generate(prompt)
            if flat_text.startswith("[ERROR"):
                last_reason = "GENERATION ERROR"
                last_excerpt = flat_text[:140]
                continue
            passed, hard, _soft, _metrics = fidelity_gate(flat_text, target)
            if passed:
                rec = {
                    "id": sid,
                    "bucket": "3",
                    "work": WORK,
                    "char_start": span["char_start"],
                    "char_end": span["char_end"],
                    "real_target": target,
                    "flattened_input": flat_text,
                    "content_hash": span["content_hash"],
                    "model": flat.MODEL,
                    "temperature": flat.TEMPERATURE,
                }
                append_record(OUT, rec)            # 5) crash-safe stream, one row
                streamed = True
                rows_in_out += 1
                n_streamed += 1
                break
            last_reason = hard[0] if hard else "FLAGGED"
            last_excerpt = flat_text[:140]

        if not streamed:
            if last_reason == "GENERATION ERROR":
                n_errors += 1
            else:
                n_gate_flagged += 1
                if len(gate_flags) < 5:
                    gate_flags.append({"reason": last_reason, "excerpt": last_excerpt})

        time.sleep(PACE_SECONDS)

    # ── Lean machine-readable summary (last line is a JSON blob the agent reads) ─
    summary = {
        "work": WORK,
        "n_mined": n_mined,
        "n_skipped_defensive": n_skipped_defensive,
        "n_flattened_clean": n_streamed,
        "n_gate_flagged": n_gate_flagged,
        "n_errors": n_errors,
        "rows_in_out": rows_in_out,
        "cap": CAP,
        "jsonl_path": OUT,
        "gate_flags": gate_flags,
        "dry": dry,
    }
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
