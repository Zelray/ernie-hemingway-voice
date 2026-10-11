"""
08_bucket1_gate.py — DATASET ACCEPTANCE GATE for the assembled bucket-1 set.
Analog of 08_bucket2_gate.py, re-aimed at QUESTION->real pairs.

Bucket-1 pairs are  question -> real :
  - real_target (span_text) = genuine Hemingway reflective span (the TARGET).
  - invented_question       = Gemini's sincere reflective question (the INPUT).

WHAT THE GATE CAN AND CANNOT SEE (read this before trusting a green run):
  HARD, machine-checkable:  ends-with-'?', length band [3,30], single sentence,
  no source/quiz meta, no CRUDE wording leak (>=5-word containment or >=3 non-
  stopword run), no dup ids, content_hash integrity, cross-bucket target dedup,
  no dress-set leakage.
  BLIND to the two failures that matter most: a SINGLE payoff word leaking into
  the question, and whether the passage actually ANSWERS the question. Those need
  the full human read (this gate PRINTS every pair for that) + the adversarial
  panel. A green gate is NOT 'done'.

NOTE — answerability INVERTS vs bucket 2: a B1 question SHOULD share few/no words
  with its oblique target (that means no leak), so zero-lexical-overlap is
  EXPECTED here and is reported, never gated.

RUN (Bash; PowerShell hangs this box):
  python pipeline/08_bucket1_gate.py                                  # full gate -> bucket1_all.jsonl + prints pairs
  python pipeline/08_bucket1_gate.py --src bucket1_requests_pilot.jsonl --out _b1_pilot_merged.jsonl   # gate a pilot file
"""
import collections
import glob
import importlib
import json
import os
import re
import string
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine  # noqa: E402
import fidelity_gate  # noqa: E402
gate07 = importlib.import_module("07_acceptance_gate")       # corpus checks + helpers
genb2 = importlib.import_module("gen_bucket2")               # leak/run detectors
genb1 = importlib.import_module("gen_bucket1_requests")      # _b1_meta_hit, question_check

DEFAULT_SRC = os.path.join(HERE, "bucket1_requests")        # dir of per-work jsonl
DEFAULT_OUT = os.path.join(HERE, "bucket1_all.jsonl")
BUCKET2_ALL = os.path.join(HERE, "bucket2_all.jsonl")
BUCKET3_ALL = os.path.join(HERE, "bucket3_all.jsonl")

# Thresholds (targets are the fixed curated 21 — these are sanity bars).
SELF_BLEU_MAX = 0.35
DISTINCT2_MIN = 0.30
NEAR_DUP_PCT_MAX = 1.0


def _load_hashes(path):
    hashes = set()
    if not os.path.exists(path):
        return hashes
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                h = json.loads(line).get("content_hash")
            except json.JSONDecodeError:
                continue
            if h:
                hashes.add(h)
    return hashes


def _src_files(src):
    if os.path.isdir(src):
        return [f for f in sorted(glob.glob(os.path.join(src, "*.jsonl")))
                if not os.path.basename(f).startswith("_")]
    return [src]


def merge(src, out_path):
    """Merge src (dir of per-work jsonl, or one file) -> out_path, dropping dup ids,
    dress-hash rows, and rows whose TARGET hash is already in bucket2_all/bucket3_all."""
    files = _src_files(src)
    dress_hashes = gate07.load_dress_hashes()
    b2_hashes = _load_hashes(BUCKET2_ALL)
    b3_hashes = _load_hashes(BUCKET3_ALL)
    rows, seen_ids, dup_ids = [], set(), []
    dress_removed, xbucket_removed = [], []
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
                h = rec.get("content_hash")
                if h in dress_hashes:
                    dress_removed.append(rid)
                    continue
                if h in b2_hashes or h in b3_hashes:
                    xbucket_removed.append(rid)
                    continue
                seen_ids.add(rid)
                rows.append(rec)
                n += 1
        per_file[os.path.basename(fp)] = n
    if os.path.exists(out_path):
        os.remove(out_path)
    for rec in rows:
        spine.append_record(out_path, rec)
    return rows, per_file, dup_ids, sorted(dress_removed), sorted(xbucket_removed), dress_hashes


# ── Question-side checks (over invented_question) ──────────────────────────────
def _q(r):
    return r.get("invented_question", "")


def _t(r):
    return r.get("real_target", r.get("span_text", ""))


def qmark_scan(rows):
    return [r["id"] for r in rows if not _q(r).strip().endswith("?")]


def leak_scan(rows):
    hits = []
    for r in rows:
        q = fidelity_gate.normalize_quotes(_q(r))
        t = fidelity_gate.normalize_quotes(_t(r))
        cont = spine.containment(q, t, n=5)
        run = genb2._contiguous_run_leak(q, t)
        if cont > 0 or run:
            hits.append((r["id"], round(cont, 3), run))
    return hits


def meta_scan(rows):
    hits = []
    for r in rows:
        hit = genb1._b1_meta_hit(fidelity_gate.normalize_quotes(_q(r)))
        if hit:
            hits.append((r["id"], hit))
    return hits


def length_scan(rows):
    bad = []
    for r in rows:
        raw = _q(r)
        wc = len(fidelity_gate.normalize_quotes(raw).split())
        if wc < 3 or wc > 30 or "\n" in raw.strip() or genb2._is_multi_sentence(raw):
            bad.append((r["id"], wc))
    return bad


def hash_integrity_scan(rows):
    """A target's stored content_hash MUST equal a fresh recompute of span_text."""
    return [r["id"] for r in rows
            if spine.content_hash(_t(r)) != r.get("content_hash")]


def answerability_overlap(rows):
    """INFORMATIONAL ONLY (inverts vs B2): ids whose question shares no content/
    proper word with the target. Expected high for oblique B1 questions = good."""
    zero = []
    for r in rows:
        qseq = genb2._content_seq(fidelity_gate.normalize_quotes(_q(r)))
        tseq = genb2._content_seq(fidelity_gate.normalize_quotes(_t(r)))
        qw, tw = {w for w, _ in qseq}, {w for w, _ in tseq}
        qp, tp = {w for w, p in qseq if p}, {w for w, p in tseq if p}
        if not ((qw & tw) or (qp & tp)):
            zero.append(r["id"])
    return zero


def question_diversity(rows):
    """Opener distribution + distinct-2 over the QUESTIONS (informational at N=21)."""
    first = collections.Counter()
    for r in rows:
        toks = re.split(r"\s+", _q(r).strip())
        w0 = toks[0].lower().strip(string.punctuation) if toks and toks[0] else ""
        first[w0] += 1
    total = sum(first.values()) or 1
    fw = {k: round(100.0 * v / total, 1) for k, v in first.most_common()}
    q_distinct2 = gate07.distinct_2([_q(r) for r in rows])
    return fw, round(q_distinct2, 4)


def pairs(rows):
    return [{"id": r["id"], "work": r["work"], "grade": r.get("grade", ""),
             "question": _q(r), "answer": _t(r)} for r in rows]


def main():
    src = DEFAULT_SRC
    out = DEFAULT_OUT
    if "--src" in sys.argv:
        src = os.path.join(HERE, sys.argv[sys.argv.index("--src") + 1])
    if "--out" in sys.argv:
        out = os.path.join(HERE, sys.argv[sys.argv.index("--out") + 1])

    rows, per_file, dup_ids, dress_removed, xbucket_removed, dress_hashes = merge(src, out)
    total = len(rows)
    per_work = dict(collections.Counter(r["work"] for r in rows))

    qmark_bad = qmark_scan(rows)
    leak_hits = leak_scan(rows)
    meta_hits = meta_scan(rows)
    length_bad = length_scan(rows)
    hash_bad = hash_integrity_scan(rows)
    answ_zero = answerability_overlap(rows)
    fw_dist, q_distinct2 = question_diversity(rows)

    # corpus sanity over the fixed targets (guarded: nltk may be absent)
    targets = [_t(r) for r in rows]
    corpus = {}
    try:
        near_pct, near_pairs, near_n = gate07.near_dup_scan(rows)
        corpus["near_dup_pct"] = round(near_pct, 4)
        corpus["near_dup_count"] = near_n
        corpus["self_bleu"] = round(gate07.self_bleu(targets), 4)
        corpus["distinct_2"] = round(gate07.distinct_2(targets), 4)
        corpus_ok = (corpus["near_dup_pct"] <= NEAR_DUP_PCT_MAX
                     and corpus["self_bleu"] <= SELF_BLEU_MAX
                     and corpus["distinct_2"] >= DISTINCT2_MIN)
    except Exception as e:
        corpus["error"] = f"{type(e).__name__}: {e}"
        corpus_ok = True   # don't block on a missing optional dep; report it

    gate_passed = (
        len(qmark_bad) == 0 and len(leak_hits) == 0 and len(meta_hits) == 0
        and len(length_bad) == 0 and len(dup_ids) == 0 and len(hash_bad) == 0
        and corpus_ok
    )

    report = {
        "src": src,
        "out": out,
        "total_pairs": total,
        "per_work_counts": per_work,
        "per_file": per_file,
        "duplicate_ids": dup_ids,
        "dress_overlap_removed": dress_removed,
        "cross_bucket_target_removed": xbucket_removed,
        "HARD_qmark_missing": qmark_bad,
        "HARD_request_leak_count": len(leak_hits),
        "HARD_request_leak_hits": leak_hits,
        "HARD_meta_count": len(meta_hits),
        "HARD_meta_hits": meta_hits,
        "HARD_length_bad": length_bad,
        "HARD_content_hash_drift": hash_bad,
        "INFO_answerability_zero_overlap_count": len(answ_zero),
        "INFO_answerability_zero_overlap_ids": answ_zero,
        "INFO_question_first_word_pct": fw_dist,
        "INFO_question_distinct_2": q_distinct2,
        "corpus_target_checks": corpus,
        "gate_passed": gate_passed,
        "REMINDER": "gate_passed is NECESSARY not SUFFICIENT — do the full human read "
                    "(pairs below) for single-word payoff leak + answerability, then the "
                    "adversarial panel.",
        "pairs": pairs(rows),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
