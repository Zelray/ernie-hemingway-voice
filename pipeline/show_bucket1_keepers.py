"""View + dedup-flag the Bucket-1 selector keepers. Deterministic, no API.

Sorts A/B keepers by (work, char_start) so overlapping spans of the same passage
sit adjacent, flags overlap clusters + 5-gram near-dups, and lists C-grade
borderlines separately. This is the QA view before reserving the final set.
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine  # noqa: E402

SEL = os.path.join(HERE, "bucket1_selected.jsonl")
recs = [json.loads(l) for l in open(SEL, encoding="utf-8") if l.strip()]

keepers = [r for r in recs if r["grade"] in ("A", "B")]
cs = [r for r in recs if r["grade"] == "C"]
keepers.sort(key=lambda r: (r["work"], r["char_start"]))

# overlap + near-dup clustering
def overlaps(a, b):
    return a["work"] == b["work"] and a["char_start"] < b["char_end"] and b["char_start"] < a["char_end"]

flagged = set()
clusters = []
for i in range(len(keepers)):
    for j in range(i + 1, len(keepers)):
        a, b = keepers[i], keepers[j]
        if overlaps(a, b):
            clusters.append(("OVERLAP", a["id"], b["id"]))
            flagged.add(a["id"]); flagged.add(b["id"])
        elif a["work"] == b["work"]:
            jac = spine.five_gram_jaccard(a["span_text"], b["span_text"])
            if jac >= 0.5:
                clusters.append((f"NEAR-DUP j={jac:.2f}", a["id"], b["id"]))
                flagged.add(a["id"]); flagged.add(b["id"])

print(f"=== {len(keepers)} A/B KEEPERS (sorted by work, position) ===\n")
cur_work = None
for r in keepers:
    if r["work"] != cur_work:
        cur_work = r["work"]
        print(f"\n###### {cur_work} ######")
    dup = "  <<DUP/OVERLAP>>" if r["id"] in flagged else ""
    print(f"\n[{r['grade']}] {r['id']}  score={r['reflect_score']} mode={r['span_mode']} "
          f"w={r['word_count']}{dup}")
    print(f"   Q-kind: {r['question_kind']}")
    print(f"   {r['span_text']}")

print("\n\n=== OVERLAP / NEAR-DUP CLUSTERS (must dedup before reserving) ===")
for kind, a, b in clusters:
    print(f"  {kind}: {a}  <->  {b}")
if not clusters:
    print("  (none)")

print(f"\n\n=== {len(cs)} C-GRADE BORDERLINES (rescue pool) ===")
for r in sorted(cs, key=lambda r: -r["reflect_score"]):
    print(f"\n[C] {r['id']} score={r['reflect_score']}  Q-kind: {r['question_kind']}")
    print(f"   {r['span_text']}")
