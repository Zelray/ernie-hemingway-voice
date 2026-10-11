"""
09_assemble.py — assemble all 4 buckets into the final Qwen2.5 ChatML training set.

WHAT (plain English):
  Buckets 1-4 are done. This merges them, formats each pair into a ChatML chat
  (system / user / assistant), dedups ACROSS buckets, and carves out a ~100-pair
  blind HOLD-OUT for M2 evaluation. The hold-out is a GROUP split: near-duplicate
  pairs are grouped (union-find over 5-gram Jaccard) so a pair and its near-twin can
  never land on opposite sides of the train/eval line — that silent leak would
  inflate the M2 win-rate and invalidate the whole eval. The hold-out is also
  STRATIFIED by bucket (red-team item: M2 win-rate must be sliceable by question
  type) and kept disjoint from the dress-rehearsal proving set.

  VOICE LIVES IN THE WEIGHTS: the system prompt is NEUTRAL ("You are a helpful
  assistant."). The task is carried by the USER turn (a question, a describe-request,
  or a rewrite instruction). No turn ever names Hemingway — at inference the demo's
  hidden prompt picks the task; the voice is unconditional in the trained weights.

CHAT MAPPING per bucket:
  B1 reflective Q&A : user = invented_question         | assistant = span_text (REAL)
  B2 description    : user = invented_request          | assistant = real_target (REAL)
  B3 flatten-restore: user = <rewrite instr> + flattened_input | assistant = real_target (REAL)  [the product]
  B4 practical Q&A  : user = instruction               | assistant = hemingway_answer (Gemini)

OUTPUT (under pipeline/):
  train.jsonl         — ChatML training rows  {messages:[...], id, bucket, task}
  eval_holdout.jsonl  — ~100 ChatML eval rows (stratified, group-split, dress-disjoint)
  assemble_report.json— counts, dedup, near-dup%, self-BLEU/distinct-2, leak checks

RUN (Bash):
  python pipeline/09_assemble.py            # write train + eval + report
  python pipeline/09_assemble.py --dry      # report only, write nothing
"""
import json, os, sys, hashlib
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine                                              # noqa: E402

SYSTEM_PROMPT = "You are a helpful assistant."

# Neutral rewrite instructions for bucket 3 (NEVER name Hemingway; "your own voice"
# = the honest product framing). Chosen deterministically per-row so no single
# phrasing dominates and the model doesn't overfit one wording.
B3_INSTRUCTIONS = [
    "Rewrite this in your own voice:",
    "Rewrite the following passage:",
    "Say this in your own words:",
    "Put this into your own style:",
    "Rewrite this:",
]

BUCKET_FILES = {
    1: "bucket1_all.jsonl",
    2: "bucket2_all.jsonl",
    3: "bucket3_all.jsonl",
    4: "bucket4_all.jsonl",
}
DRESS_PATH = os.path.join(HERE, "dress_rehearsal_pairs.jsonl")

NEAR_DUP_JACCARD = 0.60       # 5-gram Jaccard >= this = near-duplicate (groups them)
# Stratified hold-out quotas (sum=100). B1 is tiny (20) so it gets a small but real
# slice; the rest scale with bucket size so every question-type is eval-represented.
HOLDOUT_QUOTA = {1: 4, 2: 18, 3: 30, 4: 48}


def _b3_instruction(row_id):
    h = int(hashlib.md5(row_id.encode("utf-8")).hexdigest(), 16)
    return B3_INSTRUCTIONS[h % len(B3_INSTRUCTIONS)]


def to_chat(row, b):
    """Map one bucket row -> (user_text, assistant_text, task_label). `b` is the
    authoritative int bucket from the file key (row['bucket'] type is inconsistent:
    str in buckets 1-3, int in bucket 4)."""
    if b == 1:
        return row["invented_question"], row["span_text"], "reflective_qa"
    if b == 2:
        return row["invented_request"], row["real_target"], "description"
    if b == 3:
        user = _b3_instruction(row["id"]) + "\n\n" + row["flattened_input"]
        return user, row["real_target"], "rewrite"
    if b == 4:
        return row["instruction"], row["hemingway_answer"], "practical_qa"
    raise ValueError(f"unknown bucket {b}")


def load_all():
    items = []
    for b, fn in BUCKET_FILES.items():
        path = os.path.join(HERE, fn)
        for l in open(path, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            user, asst, task = to_chat(r, b)
            items.append({
                "id": r["id"], "bucket": b, "task": task,
                "user": user.strip(), "assistant": asst.strip(),
                "ahash": spine.content_hash(asst),     # dedup key = the ANSWER text
            })
    return items


def exact_dedup(items):
    """Drop exact assistant-text dups across buckets; keep first (bucket order 1->4)."""
    seen, kept, dropped = set(), [], []
    for it in sorted(items, key=lambda x: (x["bucket"], x["id"])):
        if it["ahash"] in seen:
            dropped.append(it["id"])
            continue
        seen.add(it["ahash"])
        kept.append(it)
    return kept, dropped


def five_gram_sets(items):
    return [set(spine._ngrams(spine._tokens(it["assistant"]), 5)) for it in items]


def _jacc(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter) if inter else 0.0


def near_dup_groups(items, sets):
    """Union-find over near-duplicate ANSWER pairs -> connected-component groups."""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    near_pairs = 0
    for i in range(n):
        si = sets[i]
        if not si:
            continue
        for j in range(i + 1, n):
            if _jacc(si, sets[j]) >= NEAR_DUP_JACCARD:
                union(i, j)
                near_pairs += 1
    groups = defaultdict(list)
    for idx in range(n):
        groups[find(idx)].append(idx)
    return list(groups.values()), near_pairs


def load_dress_hashes():
    hashes = set()
    if os.path.exists(DRESS_PATH):
        for l in open(DRESS_PATH, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                for k in ("real_target", "target", "span_text", "hemingway"):
                    if r.get(k):
                        hashes.add(spine.content_hash(r[k].strip()))
    return hashes


def pick_holdout(items, groups):
    """Stratified, group-respecting hold-out: assign whole near-dup groups to eval
    until each bucket's quota is met. A group goes to eval as a unit (so no near-dup
    straddles the split). Deterministic: groups walked in a stable id order."""
    # represent each group by its rows; sort groups by (min bucket, first id) stable
    grp_rows = []
    for g in groups:
        rows = [items[i] for i in g]
        rows.sort(key=lambda x: x["id"])
        grp_rows.append(rows)
    # Order WITHIN each bucket pseudo-randomly (md5 of id), NOT by raw id. Raw-id
    # order makes the eval the alphabetically-first slice of each bucket — which
    # silently skews it (B4 -> all creative_writing; B2/B3 -> all farewell-to-arms),
    # the exact opposite of representative. md5 ordering = a representative sample
    # that mirrors each bucket's real category/work mix. (advisor catch, s12.)
    grp_rows.sort(key=lambda rows: (rows[0]["bucket"],
                                    hashlib.md5(rows[0]["id"].encode("utf-8")).hexdigest()))

    quota = dict(HOLDOUT_QUOTA)
    eval_ids, eval_rows = set(), []
    for rows in grp_rows:
        # only take a (singleton) group if it still helps meet a quota and won't
        # blow it; multi-bucket groups are rare (answers are distinct) -> skip them
        # for eval to keep stratification clean (they stay in train).
        bks = {r["bucket"] for r in rows}
        if len(bks) != 1:
            continue
        b = rows[0]["bucket"]
        if quota.get(b, 0) >= len(rows) and len(rows) > 0:
            for r in rows:
                eval_ids.add(r["id"])
                eval_rows.append(r)
            quota[b] -= len(rows)
        if all(v <= 0 for v in quota.values()):
            break
    return eval_ids, eval_rows, quota


def chatml(it):
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": it["user"]},
            {"role": "assistant", "content": it["assistant"]},
        ],
        "id": it["id"], "bucket": it["bucket"], "task": it["task"],
    }


def self_bleu_distinct(texts):
    # distinct-2 (pure stdlib); self-BLEU is reported by 07 with nltk — keep this lean.
    bigrams, total = set(), 0
    for t in texts:
        toks = spine._tokens(t)
        for k in range(len(toks) - 1):
            bigrams.add((toks[k], toks[k + 1]))
            total += 1
    return round(len(bigrams) / total, 4) if total else 0.0


def main():
    dry = "--dry" in sys.argv

    raw = load_all()
    items, exact_dropped = exact_dedup(raw)
    sets = five_gram_sets(items)
    groups, near_pairs = near_dup_groups(items, sets)
    multi = [g for g in groups if len({items[i]["bucket"] for i in g}) > 1]

    dress_hashes = load_dress_hashes()
    dress_overlap = [it["id"] for it in items if it["ahash"] in dress_hashes]

    eval_ids, eval_rows, quota_left = pick_holdout(items, groups)
    train_rows = [it for it in items if it["id"] not in eval_ids]

    # leak check: no eval answer is a near-dup of any train answer (group-split
    # guarantees this, but verify by re-scanning across the boundary).
    eval_idx = [i for i, it in enumerate(items) if it["id"] in eval_ids]
    train_idx = [i for i, it in enumerate(items) if it["id"] not in eval_ids]
    cross_leaks = 0
    for ei in eval_idx:
        se = sets[ei]
        if not se:
            continue
        for ti in train_idx:
            if _jacc(se, sets[ti]) >= NEAR_DUP_JACCARD:
                cross_leaks += 1
                break

    report = {
        "loaded": len(raw),
        "by_bucket_loaded": dict(Counter(r["bucket"] for r in raw)),
        "exact_dups_dropped": len(exact_dropped),
        "after_dedup": len(items),
        "near_dup_pairs": near_pairs,
        "near_dup_groups_total": len(groups),
        "near_dup_groups_multibucket": len(multi),
        "dress_exact_overlap": len(dress_overlap),
        "holdout": {
            "size": len(eval_rows),
            "by_bucket": dict(Counter(r["bucket"] for r in eval_rows)),
            "by_task": dict(Counter(r["task"] for r in eval_rows)),
            "quota_unfilled": {k: v for k, v in quota_left.items() if v > 0},
        },
        "train_size": len(train_rows),
        "train_eval_cross_near_dup_leaks": cross_leaks,
        "distinct_2_all_answers": self_bleu_distinct([it["assistant"] for it in items]),
        "PASS": {
            "dress_disjoint": len(dress_overlap) == 0,
            "no_train_eval_leak": cross_leaks == 0,
            "holdout_filled": all(v <= 0 for v in quota_left.values()),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if dry:
        print("\n--dry: nothing written.")
        return

    if not all(report["PASS"].values()):
        print("\n[ABORT] a PASS check failed — refusing to write train/eval.")
        sys.exit(2)

    with open(os.path.join(HERE, "train.jsonl"), "w", encoding="utf-8") as f:
        for it in train_rows:
            f.write(json.dumps(chatml(it), ensure_ascii=False) + "\n")
    with open(os.path.join(HERE, "eval_holdout.jsonl"), "w", encoding="utf-8") as f:
        for it in eval_rows:
            f.write(json.dumps(chatml(it), ensure_ascii=False) + "\n")
    with open(os.path.join(HERE, "assemble_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nwrote train.jsonl ({len(train_rows)}) + eval_holdout.jsonl ({len(eval_rows)}) + assemble_report.json")


if __name__ == "__main__":
    main()
