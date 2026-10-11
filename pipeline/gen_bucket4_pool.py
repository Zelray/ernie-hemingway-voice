"""
gen_bucket4_pool.py — build the Bucket-4 candidate QUESTION pool from Dolly (no API).

WHAT (plain English):
  Bucket 4 answers real everyday questions in Hemingway's voice. The questions come
  from databricks-dolly-15k. We keep only the categories a terse, experiential voice
  can actually answer WITHOUT a source passage:
    KEEP : creative_writing, general_qa, open_qa   (all no-context)
    DROP : brainstorming (list-bait, anti-Hemingway), and every context-bearing
           category (closed_qa, information_extraction, summarization) + classification.
  Then a cheap DETERMINISTIC pre-filter removes the obviously unsuitable (damaged
  encoding, technical/code lookups, bare factual lookups, list-bait, too long/short)
  so the downstream Gemini suitability classifier (gen_bucket4_select.py) only spends
  calls on the genuine judgment calls. We have ~12x headroom over the ~560 we need, so
  it is correct to be picky here.

  ★ Insight — the experiential/factual axis cuts ACROSS categories: "what is a REST API"
    (general_qa) is as unanswerable-in-voice as "what is a polygon" (open_qa). So the
    pre-filter and the classifier judge SUITABILITY, not category.

OUTPUT: pipeline/bucket4_pool.jsonl  (shuffled candidate questions, deterministic seed).

RUN (Bash):  python pipeline/gen_bucket4_pool.py
"""
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine  # noqa: E402
import fidelity_gate  # noqa: E402

DOLLY = os.path.join(HERE, "dolly-15k.jsonl")
OUT = os.path.join(HERE, "bucket4_pool.jsonl")
KEEP_CATS = {"creative_writing", "general_qa", "open_qa"}
SEED = 1926  # The Sun Also Rises — deterministic shuffle

CAT_ABBR = {"creative_writing": "cw", "general_qa": "gq", "open_qa": "oq"}

# Clear technical/code lookups a Hemingway voice cannot answer meaningfully.
_TECH_RE = re.compile(
    r"\b(api|sql|python|java|javascript|html|css|kubernetes|docker|git|github|"
    r"regex|json|xml|html|https?|url|algorithm|database|sql|linux|aws|azure|"
    r"compiler|kernel|frontend|backend|byte|boolean|terraform|kafka|spark|"
    r"pandas|numpy|tensorflow|blockchain|cryptocurrency)\b", re.IGNORECASE)
# Bare factual lookups (open-domain trivia) — wrong target for an experiential voice.
_FACTUAL_RE = re.compile(
    r"^(who|when|where|which|whom)\b|\b(how many|what year|in what year|"
    r"what is the capital|who was the|who is the|when did|when was|where is the|"
    r"how tall|how far|how old is)\b", re.IGNORECASE)
# List-bait — produces enumerations, the opposite of Hemingway cadence.
_LIST_RE = re.compile(
    r"^(list|name)\b|\b(list of|give me a list|top \d|name (a few|some|three|five|ten))\b",
    re.IGNORECASE)
_REPLACEMENT = "�"  # the � mojibake marker present in some Dolly rows


def clean_instruction(s):
    s = fidelity_gate.normalize_quotes(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main():
    rows = [json.loads(l) for l in open(DOLLY, encoding="utf-8") if l.strip()]
    drops = {"category": 0, "has_context": 0, "mojibake": 0, "length": 0,
             "tech": 0, "factual": 0, "list": 0}
    kept = []
    for r in rows:
        cat = r.get("category", "")
        if cat not in KEEP_CATS:
            drops["category"] += 1
            continue
        if r.get("context", "").strip():
            drops["has_context"] += 1
            continue
        instr = clean_instruction(r.get("instruction", ""))
        if _REPLACEMENT in instr or _REPLACEMENT in r.get("instruction", ""):
            drops["mojibake"] += 1
            continue
        wc = len(instr.split())
        if wc < 3 or wc > 40:
            drops["length"] += 1
            continue
        if _TECH_RE.search(instr):
            drops["tech"] += 1
            continue
        if _FACTUAL_RE.search(instr):
            drops["factual"] += 1
            continue
        if _LIST_RE.search(instr):
            drops["list"] += 1
            continue
        kept.append({"category": cat, "instruction": instr})

    # deterministic shuffle for spread across categories, then stable ids
    rng = random.Random(SEED)
    rng.shuffle(kept)
    pool = []
    seen_hash = set()
    seq = {c: 0 for c in CAT_ABBR}
    dup = 0
    for k in kept:
        h = spine.content_hash(k["instruction"])
        if h in seen_hash:   # within-bucket instruction dedup
            dup += 1
            continue
        seen_hash.add(h)
        seq[k["category"]] += 1
        rec = {
            "id": f"b4_{CAT_ABBR[k['category']]}_{seq[k['category']]:05d}",
            "bucket": 4,
            "category": k["category"],
            "instruction": k["instruction"],
            "source": "dolly-15k",
            "instruction_hash": h,
        }
        pool.append(rec)

    if os.path.exists(OUT):
        os.remove(OUT)
    for rec in pool:
        spine.append_record(OUT, rec)

    per_cat = {}
    for rec in pool:
        per_cat[rec["category"]] = per_cat.get(rec["category"], 0) + 1
    print(f"WROTE {OUT}")
    print(f"dolly_total={len(rows)}  pool={len(pool)}  within_bucket_dup_dropped={dup}")
    print(f"per_category_kept={per_cat}")
    print(f"drop_reasons={drops}")


if __name__ == "__main__":
    main()
