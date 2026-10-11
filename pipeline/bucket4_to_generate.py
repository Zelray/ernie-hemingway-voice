"""
bucket4_to_generate.py — deterministic FINAL selection for Bucket-4 generation.

WHAT (plain English):
  gen_bucket4_select.py judged the question pool and banked "keepers" (questions a
  terse experiential voice can answer WELL). This script picks WHICH keepers we
  actually spend generation on, and ENFORCES THE PRODUCT-SHAPE DECISION (Mike, s12):
  Bucket 4 is the "answer everyday questions in voice" bucket, so it must be
  PRACTICAL-MAJORITY — but we keep a generous ~200-answer creative-writing slice as
  the showpiece "dash" (Ernie can still write a story on demand).

  So: cap creative_writing at CREATIVE_CAP, take ALL the practical/experiential
  keepers (general_qa + open_qa), and trim the practical fill to hit TOTAL_TARGET.
  Prefer grade "good" over "ok" everywhere; ties break by id so the choice is
  deterministic and auditable (re-running gives the identical set).

INPUT : bucket4_selected.jsonl  (keeper = suitable==true and grade in {good, ok})
OUTPUT: bucket4_to_generate.jsonl  (the rows gen_bucket4.py will answer)

RUN (Bash):
  python pipeline/bucket4_to_generate.py            # write the selection + print the mix
  python pipeline/bucket4_to_generate.py --dry      # print the mix only, write nothing
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SEL = os.path.join(HERE, "bucket4_selected.jsonl")
OUT = os.path.join(HERE, "bucket4_to_generate.jsonl")

CREATIVE_CAP = 200      # the showpiece "dash" (Mike s12): keep a strong creative slice, not a flood
TOTAL_TARGET = 700      # generate ~700 -> cadence gate keeps ~560 final (≈80% pass)

# "good" before "ok" so the richest, most cadence-teaching answers are generated first.
GRADE_RANK = {"good": 0, "ok": 1}


def is_keeper(r):
    return bool(r.get("suitable")) and r.get("grade") in ("good", "ok")


def sort_key(r):
    # best grade first, then stable by id (deterministic, reproducible selection)
    return (GRADE_RANK.get(r.get("grade"), 9), r["id"])


def main():
    dry = "--dry" in sys.argv
    rows = [json.loads(l) for l in open(SEL, encoding="utf-8") if l.strip()]
    keepers = [r for r in rows if is_keeper(r)]

    creative = sorted((r for r in keepers if r["category"] == "creative_writing"), key=sort_key)
    practical = sorted((r for r in keepers if r["category"] != "creative_writing"), key=sort_key)

    creative_take = creative[:CREATIVE_CAP]
    practical_room = max(0, TOTAL_TARGET - len(creative_take))
    practical_take = practical[:practical_room]

    selected = creative_take + practical_take
    selected.sort(key=sort_key)

    print(f"keepers available: {len(keepers)}  "
          f"(creative {len(creative)} / practical {len(practical)})")
    print(f"CREATIVE_CAP={CREATIVE_CAP}  TOTAL_TARGET={TOTAL_TARGET}")
    print(f"SELECTED: {len(selected)}")
    print(f"  by category : {dict(Counter(r['category'] for r in selected))}")
    print(f"  by grade    : {dict(Counter(r['grade'] for r in selected))}")
    print(f"  by ans_mode : {dict(Counter(r.get('answer_mode','') for r in selected))}")
    creative_pct = round(100 * len(creative_take) / max(1, len(selected)))
    print(f"  creative share: {creative_pct}%  (practical-majority = good)")

    if dry:
        print("\n--dry: nothing written.")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        for r in selected:
            f.write(json.dumps({
                "id": r["id"],
                "bucket": 4,
                "category": r["category"],
                "instruction": r["instruction"],
                "grade": r["grade"],
                "answer_mode": r.get("answer_mode", ""),
            }, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(selected)} rows -> {OUT}")


if __name__ == "__main__":
    main()
