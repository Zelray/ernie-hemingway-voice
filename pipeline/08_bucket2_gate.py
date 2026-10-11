"""
08_bucket2_gate.py — DATASET ACCEPTANCE GATE for the assembled bucket-2 set.
CLONE of 07_acceptance_gate.py with the bucket-2 deltas.

Bucket-2 pairs are  request -> real :
  - real_target      = genuine Hemingway span (the training TARGET).
  - invented_request = Gemini's plain everyday request (the training INPUT).
So this gate keeps every CORPUS check over real_target (the targets are real
Hemingway, exactly like bucket 3) and ADDS request-side checks over the NEW
invented_request field — which nothing in 07 inspects.

WHAT IT DOES:
  MERGE bucket2/*.jsonl -> bucket2_all.jsonl, dropping (a) duplicate ids, (b) any
  row whose content_hash is in the dress-rehearsal eval set, and (c) any row whose
  content_hash also appears in bucket3_all.jsonl (cross-bucket TARGET dedup —
  expected ~0 thanks to the generator's offset reservation).

  CORPUS checks over real_target (reused from 07): near_dup_scan, self_bleu,
  distinct_2, dress_overlap_recheck, purged_leak_check.

  REQUEST checks over invented_request (new):
    (a) request<->target wording leak (spine.containment n=5 OR >=3 non-stopword
        contiguous run) — count MUST be 0.
    (b) request meta/style leak (07 _META_RE + bare hemingway/ernest + source nouns
        + style words) — count MUST be 0.
    (c) request length band [4,40] words, not multi-sentence, not > the target —
        count outside band MUST be 0.
    (d) FORM DIVERSITY report — opener distribution; gate that no single opener form
        exceeds 75% of requests (informational <=40% rotation flag too).

  DROPPED from 07: fidelity_sample and the flatten-only leak_scan (no flattened_input).

RUN (Bash; PowerShell hangs this box):
  python pipeline/08_bucket2_gate.py            # full gate (needs nltk for self_bleu)
  python pipeline/08_bucket2_gate.py --pilot    # per-pair request checks + samples only
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
gate07 = importlib.import_module("07_acceptance_gate")  # reuse corpus checks + helpers
genb2 = importlib.import_module("gen_bucket2")          # reuse request detectors

BUCKET2_DIR = os.path.join(HERE, "bucket2")
MERGED_PATH = os.path.join(HERE, "bucket2_all.jsonl")
BUCKET3_ALL = os.path.join(HERE, "bucket3_all.jsonl")

# ── Thresholds ───────────────────────────────────────────────────────────────
NEAR_DUP_PCT_MAX = 1.0
SELF_BLEU_MAX = 0.35
DISTINCT2_MIN = 0.30
FORM_MAX_PCT = 75.0      # hard: no single opener form may exceed this (full scale)
FORM_TOP2_MAX_PCT = 45.0 # hard: the top TWO openers combined may not exceed this
FORM_FLAG_PCT = 40.0     # informational: rotation flag if top form exceeds this


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


# ── Merge (+ dress exclusion + cross-bucket3 target dedup) ────────────────────
def merge():
    """Merge every bucket2/<work>.jsonl (NOT the _skip_/_log files), dropping
    duplicate ids, dress-hash rows, and rows whose target hash is already in
    bucket3_all.jsonl. Writes bucket2_all.jsonl fresh."""
    files = [f for f in sorted(glob.glob(os.path.join(BUCKET2_DIR, "*.jsonl")))
             if not os.path.basename(f).startswith("_")]
    dress_hashes = gate07.load_dress_hashes()
    b3_hashes = _load_hashes(BUCKET3_ALL)
    rows, seen_ids, dup_ids = [], set(), []
    per_file = {}
    dress_removed, b3_removed = [], []
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
                    continue   # torn final line from a crash — skip, don't die
                rid = rec.get("id")
                if rid in seen_ids:
                    dup_ids.append(rid)
                    continue
                h = rec.get("content_hash")
                if h in dress_hashes:
                    dress_removed.append(rid)
                    continue
                if h in b3_hashes:
                    b3_removed.append(rid)        # cross-bucket TARGET dedup
                    continue
                seen_ids.add(rid)
                rows.append(rec)
                n += 1
        per_file[os.path.basename(fp)] = n
    if os.path.exists(MERGED_PATH):
        os.remove(MERGED_PATH)
    for rec in rows:
        spine.append_record(MERGED_PATH, rec)
    return rows, per_file, dup_ids, sorted(dress_removed), sorted(b3_removed), dress_hashes


# ── Request-side checks (over invented_request) ───────────────────────────────
def request_leak_scan(rows):
    """Rows whose request lifts wording from the target (containment n=5 OR >=3
    non-stopword contiguous run). MUST be empty."""
    hits = []
    for r in rows:
        req = fidelity_gate.normalize_quotes(r.get("invented_request", ""))
        tgt = fidelity_gate.normalize_quotes(r.get("real_target", r.get("span_text", "")))
        cont = spine.containment(req, tgt, n=5)
        run = genb2._contiguous_run_leak(req, tgt)
        if cont > 0 or run:
            hits.append((r["id"], round(cont, 3), run))
    return hits


def request_meta_scan(rows):
    """Rows whose request names a source / the act of writing / a style word /
    Hemingway. MUST be empty."""
    hits = []
    for r in rows:
        req = fidelity_gate.normalize_quotes(r.get("invented_request", ""))
        hit = genb2._meta_hit(req)
        if hit:
            hits.append((r["id"], hit))
    return hits


def request_length_scan(rows):
    """Rows whose request is outside [4,40] words, longer than its target,
    multi-sentence, or newline-containing. MUST be empty."""
    bad = []
    for r in rows:
        raw = r.get("invented_request", "")
        req = fidelity_gate.normalize_quotes(raw)
        wc = len(req.split())
        twc = len(fidelity_gate.normalize_quotes(r.get("real_target", r.get("span_text", ""))).split())
        if (wc < 4 or wc > 40 or wc > twc or "\n" in raw.strip()
                or genb2._is_multi_sentence(raw)):
            bad.append((r["id"], wc))
    return bad


def unsuitable_scan(rows):
    """Backstop: a written pair must never be an [UNSUITABLE] sentinel."""
    return [r["id"] for r in rows
            if r.get("invented_request", "").strip().upper().startswith("[UNSUITABLE]")]


def answerability_scan(rows):
    """SOFT ($0 corpus-side) signal: per row, does the request share at least one
    non-stopword CONTENT word OR one proper noun with its target? Returns the ids of
    rows with ZERO shared content/proper token. Reported, NOT gated — a pure-synonym
    request (rare here) would otherwise false-fail."""
    zero = []
    for r in rows:
        req = fidelity_gate.normalize_quotes(r.get("invented_request", ""))
        tgt = fidelity_gate.normalize_quotes(r.get("real_target", r.get("span_text", "")))
        req_seq = genb2._content_seq(req)
        tgt_seq = genb2._content_seq(tgt)
        req_words = {w for (w, _p) in req_seq}
        tgt_words = {w for (w, _p) in tgt_seq}
        req_proper = {w for (w, p) in req_seq if p}
        tgt_proper = {w for (w, p) in tgt_seq if p}
        if not ((req_words & tgt_words) or (req_proper & tgt_proper)):
            zero.append(r["id"])
    return zero


def form_diversity(rows):
    """Opener distribution (first word) + first-3-word form, and the top form's %."""
    first_word = collections.Counter()
    form3 = collections.Counter()
    for r in rows:
        req = r.get("invented_request", "").strip()
        toks = re.split(r"\s+", req) if req else []
        w0 = toks[0].lower().strip(string.punctuation) if toks else ""
        first_word[w0] += 1
        form3[" ".join(t.lower().strip(string.punctuation) for t in toks[:3])] += 1
    total = sum(first_word.values())
    fw_dist = {k: round(100.0 * v / total, 1) for k, v in first_word.most_common()}
    f3_dist = {k: round(100.0 * v / total, 1) for k, v in form3.most_common(12)}
    top_pct = (100.0 * first_word.most_common(1)[0][1] / total) if total else 0.0
    top2_pct = (100.0 * sum(v for _, v in first_word.most_common(2)) / total) if total else 0.0
    return fw_dist, f3_dist, round(top_pct, 1), round(top2_pct, 1)


def _samples(rows, limit=40):
    out = []
    for r in rows[:limit]:
        req = r.get("invented_request", "")
        tgt = r.get("real_target", r.get("span_text", ""))
        rc = r.get("request_check", {})
        out.append({
            "id": r["id"], "work": r["work"],
            "request": req,
            "target_head": tgt[:180],
            "hard": rc.get("hard", []), "soft": rc.get("soft", []),
        })
    return out


def main():
    global BUCKET2_DIR, MERGED_PATH
    pilot = "--pilot" in sys.argv
    if "--dir" in sys.argv:                       # read regenerated requests (e.g. bucket2_v2)
        BUCKET2_DIR = os.path.join(HERE, sys.argv[sys.argv.index("--dir") + 1])
    if "--out" in sys.argv:                        # avoid clobbering bucket2_all.jsonl in pilot
        MERGED_PATH = os.path.join(HERE, sys.argv[sys.argv.index("--out") + 1])
    rows, per_file, dup_ids, dress_removed, b3_removed, dress_hashes = merge()
    total = len(rows)
    per_work = dict(collections.Counter(r["work"] for r in rows))

    leak_hits = request_leak_scan(rows)
    meta_hits = request_meta_scan(rows)
    length_bad = request_length_scan(rows)
    unsuitable = unsuitable_scan(rows)
    answerability_zero = answerability_scan(rows)
    fw_dist, f3_dist, top_pct, top2_pct = form_diversity(rows)

    base_pass = (
        len(dup_ids) == 0 and
        len(leak_hits) == 0 and
        len(meta_hits) == 0 and
        len(length_bad) == 0 and
        len(unsuitable) == 0
    )

    report = {
        "mode": "pilot" if pilot else "full",
        "total_pairs": total,
        "per_work_counts": per_work,
        "per_file": per_file,
        "duplicate_ids_across_files": dup_ids,
        "dress_overlap_removed_count": len(dress_removed),
        "dress_overlap_removed_ids": dress_removed[:20],
        "bucket3_cross_dedup_removed_count": len(b3_removed),
        "bucket3_cross_dedup_removed_ids": b3_removed[:20],
        "request_leak_count": len(leak_hits),
        "request_leak_hits": leak_hits[:20],
        "request_meta_count": len(meta_hits),
        "request_meta_hits": meta_hits[:20],
        "request_length_bad_count": len(length_bad),
        "request_length_bad": length_bad[:20],
        "unsuitable_written_count": len(unsuitable),
        "answerability_zero_overlap": len(answerability_zero),       # SOFT flag, not gated
        "answerability_zero_overlap_ids": answerability_zero[:20],
        "form_first_word_distribution_pct": fw_dist,
        "form_first3_distribution_pct": f3_dist,
        "form_top_pct": top_pct,
        "form_top2_pct": top2_pct,
        "form_over_40_flag": top_pct > FORM_FLAG_PCT,
    }

    if pilot:
        # Pilot: per-pair request checks + samples only (skip corpus self_bleu/distinct_2).
        report["form_top_pct_note"] = "informational at pilot scale (N too small to hard-fail)"
        report["samples"] = _samples(rows)
        report["gate_passed"] = base_pass
    else:
        targets = [r.get("real_target", r.get("span_text", "")) for r in rows]
        near_pct, near_pairs, near_n = gate07.near_dup_scan(rows)
        sb = gate07.self_bleu(targets)
        d2 = gate07.distinct_2(targets)
        purged_hits, purged_control = gate07.purged_leak_check(rows)
        dress_exact_post, dress_near = gate07.dress_overlap_recheck(rows, dress_hashes)
        report.update({
            "near_dup_pct": round(near_pct, 4),
            "near_dup_count": near_n,
            "near_dup_pairs": near_pairs[:20],
            "self_bleu": round(sb, 4),
            "distinct_2": round(d2, 4),
            "purged_leak_hits": purged_hits[:20],
            "purged_leak_control_fires": purged_control,
            "dress_exact_overlap_post_merge": dress_exact_post,
            "dress_near_twin_count": len(dress_near),
            "thresholds": {
                "near_dup_pct_max": NEAR_DUP_PCT_MAX, "self_bleu_max": SELF_BLEU_MAX,
                "distinct2_min": DISTINCT2_MIN, "form_max_pct": FORM_MAX_PCT,
                "form_top2_max_pct": FORM_TOP2_MAX_PCT,
            },
        })
        report["gate_passed"] = (
            base_pass and
            near_pct <= NEAR_DUP_PCT_MAX and
            sb <= SELF_BLEU_MAX and
            d2 >= DISTINCT2_MIN and
            len(purged_hits) == 0 and
            purged_control and
            dress_exact_post == 0 and
            top_pct <= FORM_MAX_PCT and
            top2_pct <= FORM_TOP2_MAX_PCT
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
