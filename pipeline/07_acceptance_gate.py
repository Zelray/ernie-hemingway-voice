"""
07_acceptance_gate.py — DATASET ACCEPTANCE GATE for the assembled bucket-3 set.

This is the go/no-go for training. It MERGES every pipeline/bucket3/<work>.jsonl
into pipeline/bucket3_all.jsonl, then runs the full acceptance battery:

  1. total_pairs            — merged row count (and duplicate-id check)
  2. near_dup_pct           — % of rows that 5-gram-Jaccard >= 0.60 a prior row
                              (uses spine.five_gram_jaccard). Threshold: <= 1%.
  3. self_bleu              — corpus self-BLEU-4 (nltk, method1 smoothing) over
                              real_target. Lower = more diverse. Threshold: <= 0.35.
     distinct_2            — unique bigrams / total bigrams over real_target.
                              Threshold: >= 0.30.
     leak_pct             — % of pairs whose flattened_input vs real_target
                              5-gram Jaccard >= 0.50 (the fidelity_gate's own
                              UNDER-FLATTEN hard threshold). Should be ~0.
     meta_leak_count      — # of real_target texts containing AI/instruction/meta
                              phrases (contamination of the TARGET). Must be 0.
  4. fidelity_sample_pass  — re-grade ~15 random pairs through the de-noised
                              fidelity_gate: facts/numbers/person preserved.

STDLIB + nltk + spine + fidelity_gate. No API, no money.
RUN (Bash; PowerShell hangs this box):
  python pipeline/07_acceptance_gate.py
"""
import glob
import importlib.util
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# spine + fidelity_gate live alongside this file.
sys.path.insert(0, HERE)
import spine  # noqa: E402
import fidelity_gate as fg_mod  # noqa: E402

BUCKET3_DIR = os.path.join(HERE, "bucket3")
MERGED_PATH = os.path.join(HERE, "bucket3_all.jsonl")
# The dress-rehearsal proving set. bucket3_all (the TRAIN set) must share NO span
# with it, so it can serve as a clean held-out reference without train/eval leak.
DRESS_PATH = os.path.join(HERE, "dress_rehearsal_pairs.jsonl")

# The three spoken-dialogue fragments PURGED from three-short during cleanup.
# Stored apostrophe-free + lowercased so a curly U+2019 cannot dodge a straight-
# quote search (the exact trap that bit the cleaner). NOT bare "marsala": a legit
# 3rd-person narration span ("poured the marsala into it") was deliberately kept.
_PURGED_LEAK_FRAGMENTS = ["buon di arturo", "you like marsala", "senta caro"]

# ── Thresholds (the gate's pass/fail bars) ───────────────────────────────────
NEAR_DUP_JACCARD = 0.60      # spine.five_gram_jaccard >= this = near-dup pair
NEAR_DUP_PCT_MAX = 1.0       # near_dup_pct must be <= 1%
SELF_BLEU_MAX = 0.35
DISTINCT2_MIN = 0.30
LEAK_JACCARD = 0.50          # flattened_input vs real_target >= this = leak
SAMPLE_N = 15
SEED = 1337

# AI / instruction / meta phrases that should NEVER appear in a real-Hemingway
# TARGET. If one shows up, generation contaminated the target — a hard fail.
_META_PATTERNS = [
    r"\bas an ai\b", r"\bas a language model\b", r"\blanguage model\b",
    r"\bai language\b", r"\bi am an ai\b", r"\bi cannot\b.{0,30}\bas an? (ai|assistant)\b",
    r"\bopenai\b", r"\bgemini\b", r"\bchatgpt\b", r"\bgpt-?\d", r"\banthropic\b",
    r"\bas a helpful\b", r"\bhelpful assistant\b", r"\byou are an? (ai|assistant|helpful)\b",
    r"\bin (the style|hemingway'?s? (voice|style))\b", r"\brewrite (the|this)\b",
    # "flatten" only as the PIPELINE meta-term (needs a meta object-noun); the
    # bare verb is genuine prose ("the road flattened out" — real Hemingway).
    r"\bflatten(?:ed|s|ing)?\s+(?:version|passage|text|answer|input|prose|output|sentence|paragraph)\b",
    r"\bvoiceless\b", r"\bhere is (the|a|an|my)\b",
    r"\bsure,? here\b", r"\bcertainly[!,]\b", r"\bstep \d\b",
    r"\binstruction[:\s]", r"\bprompt[:\s]", r"\bthe following (passage|text|answer)\b",
    r"\bi'?m sorry,? (but|i)\b", r"```",
]
_META_RE = [re.compile(p, re.IGNORECASE) for p in _META_PATTERNS]


def _tokens(text):
    return re.findall(r"\w+", text.lower())


# ── Step 6 helper: dress-rehearsal content_hash set (train/eval leak guard) ───
def load_dress_hashes():
    hashes = set()
    if not os.path.exists(DRESS_PATH):
        return hashes
    with open(DRESS_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            h = json.loads(line).get("content_hash")
            if h:
                hashes.add(h)
    return hashes


# ── Step 1 (+ Step 6 exclusion): merge ───────────────────────────────────────
def merge():
    """Merge every bucket3/<work>.jsonl, dropping (a) duplicate ids across files
    and (b) any row whose content_hash also appears in the dress-rehearsal set —
    so the written TRAIN artifact cannot leak into a held-out dress reference.
    Exclusion happens HERE, before metrics, so the file AND every downstream
    metric reflect the cleaned set."""
    files = sorted(glob.glob(os.path.join(BUCKET3_DIR, "*.jsonl")))
    dress_hashes = load_dress_hashes()
    rows, seen_ids, dup_ids = [], set(), []
    per_file = {}
    dress_removed = []          # bucket3 ids dropped for matching a dress hash
    for fp in files:
        n = 0
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rid = rec.get("id")
                if rid in seen_ids:
                    dup_ids.append(rid)
                    continue
                if rec.get("content_hash") in dress_hashes:
                    dress_removed.append(rid)   # step-6 leakage guard
                    continue
                seen_ids.add(rid)
                rows.append(rec)
                n += 1
        per_file[os.path.basename(fp)] = n
    # write merged file fresh (post-exclusion rows only)
    if os.path.exists(MERGED_PATH):
        os.remove(MERGED_PATH)
    for rec in rows:
        spine.append_record(MERGED_PATH, rec)
    return rows, per_file, dup_ids, sorted(dress_removed), dress_hashes


# ── Step 2: near-dup ─────────────────────────────────────────────────────────
def near_dup_scan(rows):
    targets = [r.get("real_target", r.get("span_text", "")) for r in rows]
    n = len(targets)
    flagged_rows = set()      # index of the LATER row in a near-dup pair
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = spine.five_gram_jaccard(targets[i], targets[j])
            if sim >= NEAR_DUP_JACCARD:
                flagged_rows.add(j)
                pairs.append((rows[i]["id"], rows[j]["id"], round(sim, 3)))
    pct = 100.0 * len(flagged_rows) / n if n else 0.0
    return pct, pairs, len(flagged_rows)


# ── Step 3: corpus metrics ───────────────────────────────────────────────────
def self_bleu(targets):
    from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
    sm = SmoothingFunction().method1
    toks = [_tokens(t) for t in targets]
    weights = (0.25, 0.25, 0.25, 0.25)
    scores = []
    for i, hyp in enumerate(toks):
        if not hyp:
            continue
        refs = [toks[j] for j in range(len(toks)) if j != i and toks[j]]
        if not refs:
            continue
        scores.append(sentence_bleu(refs, hyp, weights=weights, smoothing_function=sm))
    return sum(scores) / len(scores) if scores else 0.0


def distinct_2(targets):
    total, uniq = 0, set()
    for t in targets:
        tk = _tokens(t)
        bigrams = list(zip(tk, tk[1:]))
        total += len(bigrams)
        uniq.update(bigrams)
    return len(uniq) / total if total else 0.0


def leak_scan(rows):
    n_leak, examples = 0, []
    for r in rows:
        flat = r.get("flattened_input", "")
        tgt = r.get("real_target", r.get("span_text", ""))
        sim = spine.five_gram_jaccard(flat, tgt)
        if sim >= LEAK_JACCARD:
            n_leak += 1
            examples.append((r["id"], round(sim, 3)))
    pct = 100.0 * n_leak / len(rows) if rows else 0.0
    return pct, examples


def meta_leak_scan(rows):
    hits = []
    for r in rows:
        tgt = r.get("real_target", r.get("span_text", ""))
        for rx in _META_RE:
            m = rx.search(tgt)
            if m:
                hits.append((r["id"], rx.pattern, m.group(0)))
                break
    return hits


# ── Step 5: purged dialogue-leak absence (apostrophe-agnostic) ───────────────
def _deapostrophe(text):
    """Lowercase, drop straight + curly apostrophes, collapse whitespace — so a
    curly U+2019 in the source cannot dodge a straight-quote search pattern."""
    t = text.lower().replace("’", "").replace("‘", "").replace("'", "")
    return re.sub(r"\s+", " ", t)


def purged_leak_check(rows):
    """Confirm the 3 purged spoken-dialogue fragments are absent from BOTH the
    target and the flattened input of every row. Returns (hits, control_fires);
    control_fires is a positive-control assertion that the matcher actually fires
    on a string known to contain a fragment — so a 0 means 'absent', not 'matcher
    silently broke'."""
    hits = []
    for r in rows:
        blob = _deapostrophe(
            r.get("real_target", r.get("span_text", "")) + " " +
            r.get("flattened_input", "")
        )
        for frag in _PURGED_LEAK_FRAGMENTS:
            if frag in blob:
                hits.append((r["id"], frag))
    control = _deapostrophe("He said, Buon' di Arturo! and tipped his hat.")
    control_fires = any(frag in control for frag in _PURGED_LEAK_FRAGMENTS)
    return hits, control_fires


# ── Step 6: belt-and-suspenders near-dup vs dress (content_hash is the spec) ──
def dress_overlap_recheck(rows, dress_hashes):
    """Post-merge re-confirmation: how many written rows still carry a dress
    content_hash (must be 0 after exclusion), plus a cheap 5-gram near-twin pass
    that would catch a dress near-duplicate that isn't byte-identical."""
    exact_post = sum(1 for r in rows if r.get("content_hash") in dress_hashes)
    dress_targets = []
    if os.path.exists(DRESS_PATH):
        with open(DRESS_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    dress_targets.append(d.get("real_target", d.get("span_text", "")))
    near_twins = []
    for r in rows:
        tgt = r.get("real_target", r.get("span_text", ""))
        for dt in dress_targets:
            if spine.five_gram_jaccard(tgt, dt) >= NEAR_DUP_JACCARD:
                near_twins.append(r["id"])
                break
    return exact_post, near_twins


# ── Step 4: fidelity spot-check ──────────────────────────────────────────────
def fidelity_sample(rows):
    rng = random.Random(SEED)
    sample = rng.sample(rows, min(SAMPLE_N, len(rows)))
    results = []
    all_pass = True
    for r in sample:
        flat = r.get("flattened_input", "")
        tgt = r.get("real_target", r.get("span_text", ""))
        passed, hard, soft, metrics = fg_mod.fidelity_gate(flat, tgt)
        # Defer fact/person preservation to the de-noised gate's HARD verdict
        # (it already treats a digit<->word number reformat as SOFT, not a loss).
        fact_ok = not any(("ENTITY" in h or "CARDINAL" in h or "GARBLE" in h) for h in hard)
        person_ok = not any("PERSON FLIP" in h for h in hard)
        ok = passed and fact_ok and person_ok
        if not ok:
            all_pass = False
        results.append({
            "id": r["id"], "passed": passed, "fact_ok": fact_ok,
            "person_ok": person_ok, "hard": hard, "soft": soft,
            "five_gram_jaccard": metrics["five_gram_jaccard"],
        })
    return all_pass, results, [r["id"] for r in sample]


def main():
    import collections
    rows, per_file, dup_ids, dress_removed, dress_hashes = merge()
    targets = [r.get("real_target", r.get("span_text", "")) for r in rows]
    total = len(rows)
    per_work = dict(collections.Counter(r["work"] for r in rows))

    near_pct, near_pairs, near_n = near_dup_scan(rows)
    sb = self_bleu(targets)
    d2 = distinct_2(targets)
    leak_pct, leak_ex = leak_scan(rows)
    meta_hits = meta_leak_scan(rows)
    purged_hits, purged_control_fires = purged_leak_check(rows)
    dress_exact_post, dress_near_twins = dress_overlap_recheck(rows, dress_hashes)
    fid_pass, fid_results, fid_ids = fidelity_sample(rows)

    gate = (
        near_pct <= NEAR_DUP_PCT_MAX and
        sb <= SELF_BLEU_MAX and
        d2 >= DISTINCT2_MIN and
        leak_pct <= 0.0 and          # leak must be exactly zero (gate-consistent)
        len(meta_hits) == 0 and
        fid_pass and
        len(purged_hits) == 0 and     # step 5: purged dialogue leaks absent
        purged_control_fires and      # step 5: matcher proven to fire (no false 0)
        dress_exact_post == 0         # step 6: no dress content_hash survives
    )

    report = {
        "total_pairs": total,
        "per_work_counts": per_work,
        "per_file": per_file,
        "duplicate_ids_across_files": dup_ids,
        "dress_overlap_removed_count": len(dress_removed),
        "dress_overlap_removed_ids": dress_removed,
        "dress_exact_overlap_post_merge": dress_exact_post,
        "dress_near_twin_count": len(dress_near_twins),
        "dress_near_twin_ids": dress_near_twins[:20],
        "self_bleu": round(sb, 4),
        "distinct_2": round(d2, 4),
        "near_dup_pct": round(near_pct, 4),
        "near_dup_count": near_n,
        "near_dup_pairs": near_pairs[:20],
        "leak_pct": round(leak_pct, 4),
        "leak_examples": leak_ex[:20],
        "meta_leak_count": len(meta_hits),
        "meta_leak_hits": meta_hits[:20],
        "purged_leak_hits": purged_hits[:20],
        "purged_leak_control_fires": purged_control_fires,
        "fidelity_sample_pass": fid_pass,
        "fidelity_sample_ids": fid_ids,
        "fidelity_results": fid_results,
        "gate_passed": gate,
        "thresholds": {
            "near_dup_pct_max": NEAR_DUP_PCT_MAX, "self_bleu_max": SELF_BLEU_MAX,
            "distinct2_min": DISTINCT2_MIN, "leak_jaccard": LEAK_JACCARD,
            "near_dup_jaccard": NEAR_DUP_JACCARD,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
