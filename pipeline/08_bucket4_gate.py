"""
08_bucket4_gate.py — DATASET ACCEPTANCE GATE for the assembled bucket-4 set.
Analog of 08_bucket1_gate.py, re-aimed at the ONE Gemini-IMITATED bucket.

WHAT (plain English) — THE DEDUP-AXIS FLIP (read this before trusting a run):
  Buckets 1/2/3 are real Hemingway: the TARGET (span_text) is genuine corpus text,
  so those gates dedup on the ANSWER and police cross-bucket span reuse through a
  SpanRegistry. Bucket 4 is the mirror image. Here the ANSWER (hemingway_answer) is
  Gemini PROSE, not a corpus span — there is NO span, NO SpanRegistry, and NO
  cross-bucket span-overlap concern. The only thing two bucket-4 rows can truly
  collide on is the QUESTION. So the dedup axis FLIPS:
    - DEDUP on the INSTRUCTION (the questions) — drop exact-duplicate questions.
    - MEASURE DIVERSITY on the ANSWERS — self-BLEU + distinct-2 over hemingway_answer,
      plus opener/closer frequency tables (temp-0.6 imitation drifts toward formulaic
      "It is a ___ thing." openers; we surface that for a human, never hard-fail it).

WHAT THE GATE DOES (hard vs informational):
  HARD, machine-checkable & PROMOTION-BLOCKING:
    content_hash integrity — every row's stored content_hash MUST equal a fresh
    spine.content_hash(hemingway_answer). Any drift => refuse to promote, exit nonzero.
  DEFENSIVE re-verify (reported, the generator already gated inline):
    cadence_check() over every kept answer — pass/fail counts + a fail-reason histogram.
  INFORMATIONAL (reported, never gated):
    self-BLEU, distinct-2, opener/closer frequency tables, instruction-dups dropped.

  BLIND to what matters most (same caveat as every gate): whether each answer is a
  GOOD, on-topic answer, and word-level parody/purple diction. Those need the human
  read + the adversarial panel. A green gate is NECESSARY, NOT sufficient.

RUN (Bash; PowerShell hangs this box):
  python pipeline/08_bucket4_gate.py            # full gate -> bucket4_all.jsonl + report
  python pipeline/08_bucket4_gate.py --dry      # compute + print report, write NOTHING
  python pipeline/08_bucket4_gate.py --src bucket4 --out bucket4_all.jsonl   # explicit paths
"""
import collections
import glob
import json
import os
import string
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine  # noqa: E402
import bucket4_cadence_gate as cg  # noqa: E402  cadence_check
import importlib  # noqa: E402
gate07 = importlib.import_module("07_acceptance_gate")   # self_bleu / distinct_2 helpers

DEFAULT_SRC = os.path.join(HERE, "bucket4")            # dir of per-category jsonl
DEFAULT_OUT = os.path.join(HERE, "bucket4_all.jsonl")

# Diversity sanity bars over the ANSWERS (informational — Gemini prose is naturally
# more self-similar than mined corpus, so these are reported, not promotion-blocking).
SELF_BLEU_MAX = 0.35
DISTINCT2_MIN = 0.30


def _src_files(src):
    if os.path.isdir(src):
        return [f for f in sorted(glob.glob(os.path.join(src, "*.jsonl")))
                if not os.path.basename(f).startswith("_")]
    return [src]


def merge(src):
    """Merge src (dir of per-category jsonl, or one file) -> one in-memory list,
    dropping dup ids defensively. NO SpanRegistry, NO cross-bucket dedup here: the
    bucket-4 answer is Gemini prose, not a corpus span, so there is nothing to
    register or cross-check. Returns (rows, per_file_counts, dup_ids)."""
    files = _src_files(src)
    rows, seen_ids, dup_ids = [], set(), []
    per_file = {}
    for fp in files:
        n = 0
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = rec.get("id")
                if rid in seen_ids:
                    dup_ids.append(rid)
                    continue
                seen_ids.add(rid)
                rows.append(rec)
                n += 1
        per_file[os.path.basename(fp)] = n
    return rows, per_file, dup_ids


# ── Field accessors ───────────────────────────────────────────────────────────
def _ans(r):
    return r.get("hemingway_answer", "")


def _instr(r):
    return r.get("instruction", "")


# ── HARD: content_hash integrity over the ANSWERS (promotion-blocking) ─────────
def hash_integrity_scan(rows):
    """Every row's stored content_hash MUST equal a fresh recompute over its
    hemingway_answer. Returns the ids whose stored hash has drifted."""
    return [r.get("id") for r in rows
            if spine.content_hash(_ans(r)) != r.get("content_hash")]


# ── Within-bucket dedup on the INSTRUCTION (the dedup-axis flip) ───────────────
def dedup_instructions(rows):
    """Drop rows whose normalized INSTRUCTION repeats one already kept (keyed on
    spine.content_hash(instruction), which normalizes case/whitespace/edge punct).
    Keeps first occurrence. Returns (kept_rows, dropped_ids)."""
    seen, kept, dropped = set(), [], []
    for r in rows:
        h = spine.content_hash(_instr(r))
        if h in seen:
            dropped.append(r.get("id"))
            continue
        seen.add(h)
        kept.append(r)
    return kept, dropped


# ── DEFENSIVE: re-verify cadence over every kept ANSWER ────────────────────────
def cadence_reverify(rows):
    """Re-run the two-sided cadence judge over every kept answer (the generator
    already gated inline; this is a defensive re-check at promotion time).
    Returns (passed_count, fails, reason_counts)."""
    passed, fails = 0, []
    reason_counts = {}
    for r in rows:
        ok, hard, m = cg.cadence_check(_ans(r))
        if ok:
            passed += 1
        else:
            fails.append({"id": r.get("id"), "hard": hard,
                          "mean_len": m.get("mean_len"), "max_len": m.get("max_len"),
                          "frag_rate": m.get("frag_rate"), "max_run": m.get("max_consec_frag")})
            for h in hard:
                reason_counts[h] = reason_counts.get(h, 0) + 1
    return passed, fails, reason_counts


# ── INFORMATIONAL: opener / closer monotony tables over the ANSWERS ────────────
def opener_closer_tables(rows):
    """Top-10 first words of each answer, and top-10 first words of each answer's
    LAST full sentence — so a human can spot 'It is a ___ thing.'-type monotony.
    Reported only; never gated."""
    openers = collections.Counter()
    closers = collections.Counter()
    for r in rows:
        a = _ans(r)
        toks = a.split()
        if toks:
            openers[toks[0].lower().strip(string.punctuation)] += 1
        # first word of the closing sentence (mirror gen_bucket4.pilot_diagnostics)
        if a.count(".") >= 2:
            tail = a.rstrip().split(".")[-2].strip().split()
            if tail:
                closers[tail[0].lower().strip(string.punctuation)] += 1
    return dict(openers.most_common(10)), dict(closers.most_common(10))


def main():
    argv = sys.argv
    dry = "--dry" in argv
    src = DEFAULT_SRC
    out = DEFAULT_OUT
    if "--src" in argv:
        src = os.path.join(HERE, argv[argv.index("--src") + 1])
    if "--out" in argv:
        out = os.path.join(HERE, argv[argv.index("--out") + 1])

    rows, per_file, dup_ids = merge(src)
    total_merged = len(rows)
    per_category = dict(collections.Counter(r.get("category", "") for r in rows))

    # ── HARD GATE: content_hash integrity. Drift => refuse to promote, exit nonzero.
    hash_bad = hash_integrity_scan(rows)
    if hash_bad:
        print(json.dumps({
            "src": src,
            "total_merged": total_merged,
            "FATAL_content_hash_drift_count": len(hash_bad),
            "FATAL_content_hash_drift_ids": hash_bad,
            "gate_passed": False,
            "REFUSED": "content_hash integrity failed over hemingway_answer — NOT promoting. "
                       "Some row's stored hash != fresh spine.content_hash(answer); the data "
                       "was edited after generation or written wrong. Fix the source rows, rerun.",
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # ── Within-bucket dedup on the INSTRUCTION (axis flip) ────────────────────
    kept, instr_dropped = dedup_instructions(rows)

    # ── DEFENSIVE cadence re-verify over kept answers ─────────────────────────
    cad_pass, cad_fails, cad_reasons = cadence_reverify(kept)

    # ── Diversity over the ANSWERS (informational) ────────────────────────────
    answers = [_ans(r) for r in kept]
    diversity = {}
    try:
        diversity["self_bleu"] = round(gate07.self_bleu(answers), 4)
        diversity["distinct_2"] = round(gate07.distinct_2(answers), 4)
        diversity["self_bleu_ok"] = diversity["self_bleu"] <= SELF_BLEU_MAX
        diversity["distinct_2_ok"] = diversity["distinct_2"] >= DISTINCT2_MIN
    except Exception as e:
        # nltk is an optional dep for self_bleu; don't block, just report.
        diversity["error"] = f"{type(e).__name__}: {e}"

    openers, closers = opener_closer_tables(kept)

    # ── Promote (unless --dry) ────────────────────────────────────────────────
    written = 0
    if not dry:
        if os.path.exists(out):
            os.remove(out)
        for r in kept:
            spine.append_record(out, r)
            written += 1

    report = {
        "src": src,
        "out": out,
        "dry_run": dry,
        "total_merged": total_merged,
        "per_category_counts": per_category,
        "per_file": per_file,
        "duplicate_ids": dup_ids,
        "HARD_content_hash_integrity": "PASS (all answers verified)",
        "instruction_dups_dropped_count": len(instr_dropped),
        "instruction_dups_dropped_ids": instr_dropped,
        "kept_after_instruction_dedup": len(kept),
        "cadence_reverify": {
            "passed": cad_pass,
            "failed": len(cad_fails),
            "pass_rate": round(cad_pass / max(1, len(kept)), 3),
            "reason_counts": cad_reasons,
            "fails": cad_fails,
        },
        "INFO_answer_diversity": diversity,
        "INFO_answer_top10_openers": openers,
        "INFO_answer_top10_closer_first_words": closers,
        "REMINDER": "gate_passed is NECESSARY not SUFFICIENT — content_hash + cadence are "
                    "machine-checkable, but the answer's on-topic quality and word-level "
                    "parody/purple diction need the human read + adversarial panel.",
        "written_to_bucket4_all": (0 if dry else written),
        "NOTE": ("--dry: report only, nothing written." if dry
                 else f"promoted {written} rows to {out}"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
