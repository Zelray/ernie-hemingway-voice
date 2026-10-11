"""
build_style_reference.py — freeze the real-Hemingway CADENCE reference for Bucket 4.

WHAT (plain English):
  The two-sided cadence gate needs to know what a real Hemingway PARAGRAPH looks
  like — not the whole corpus, a paragraph, because a Bucket-4 answer is paragraph-
  sized. So we cut the cleaned corpus into ~85-word chunks (chunk_text), fingerprint
  each chunk's sentence rhythm (style_metrics), and record the 10th/50th/90th
  percentile of every metric across all chunks. The middle 80% band [p10, p90] is
  the gate's "this reads like real Hemingway cadence" window: below p10 on mean
  length = too choppy (caricature); above p90 = too flowery (not him).

  The same split_sentences() that built this reference is the one the gate uses, so
  reference and live measurement are apples-to-apples.

OUTPUT: pipeline/bucket4_style_reference.json  (the frozen bands the gate reads)

RUN (Bash):  python pipeline/build_style_reference.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stylometry  # noqa: E402

CLEAN_DIR = os.path.join(os.path.dirname(HERE), "clean")
OUT = os.path.join(HERE, "bucket4_style_reference.json")
CHUNK_TARGET_WORDS = 85
BAND_METRICS = ("mean_len", "stdev_len", "max_len", "frag_rate", "long_rate",
                "max_consec_frag", "and_frac")


def pct_band(values):
    a = np.array(values, dtype=float)
    return {
        "p05": round(float(np.percentile(a, 5)), 4),
        "p10": round(float(np.percentile(a, 10)), 4),
        "p25": round(float(np.percentile(a, 25)), 4),
        "p50": round(float(np.percentile(a, 50)), 4),
        "p75": round(float(np.percentile(a, 75)), 4),
        "p90": round(float(np.percentile(a, 90)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
        "mean": round(float(a.mean()), 4),
    }


def main():
    works, all_chunks = [], []
    all_sent_lens = []
    for fn in sorted(os.listdir(CLEAN_DIR)):
        if not fn.endswith("_clean.txt"):
            continue
        works.append(fn)
        txt = open(os.path.join(CLEAN_DIR, fn), encoding="utf-8").read()
        all_sent_lens.extend(stylometry.sentence_lengths(txt))
        all_chunks.extend(stylometry.chunk_text(txt, CHUNK_TARGET_WORDS))

    # per-chunk metric vectors
    metrics = [stylometry.style_metrics(c) for c in all_chunks]
    metrics = [m for m in metrics if m]
    bands = {k: pct_band([m[k] for m in metrics]) for k in BAND_METRICS}

    # corpus-aggregate (all sentences pooled) — secondary sanity report only
    sl = np.array(all_sent_lens, dtype=float)
    corpus_aggregate = {
        "n_sentences": len(all_sent_lens),
        "mean_len": round(float(sl.mean()), 3),
        "median_len": round(float(np.median(sl)), 3),
        "stdev_len": round(float(sl.std()), 3),
        "frag_rate_le5": round(float((sl <= 5).mean()), 4),
        "long_rate_ge18": round(float((sl >= stylometry.LONG_MIN).mean()), 4),
    }

    ref = {
        "built_from": works,
        "n_chunks": len(metrics),
        "chunk_target_words": CHUNK_TARGET_WORDS,
        "fragment_max": stylometry.FRAGMENT_MAX,
        "long_min": stylometry.LONG_MIN,
        "per_chunk_bands": bands,
        "corpus_aggregate": corpus_aggregate,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(ref, f, ensure_ascii=False, indent=2)

    print(f"WROTE {OUT}")
    print(f"n_chunks={len(metrics)}  chunk_target_words={CHUNK_TARGET_WORDS}")
    print("\n=== per-chunk cadence bands (p10 .. p50 .. p90) ===")
    for k in BAND_METRICS:
        b = bands[k]
        print(f"  {k:16}  p10={b['p10']:7}  p50={b['p50']:7}  p90={b['p90']:7}   (mean {b['mean']})")
    print("\n=== corpus aggregate (all sentences) ===")
    for k, v in corpus_aggregate.items():
        print(f"  {k:16} {v}")


if __name__ == "__main__":
    main()
