"""
Promote bucket2_all_v3.jsonl -> bucket2_all.jsonl (FINAL). GATED: only run AFTER
the changed-rows re-review is clean (0 hard leak + 0 hard/false-entity answerability).

Footgun guards (HANDOFF + advisor):
  - The argless `python pipeline/08_bucket2_gate.py` re-merges the V1 bucket2/*.jsonl
    into bucket2_all.jsonl -> would CLOBBER this promotion. So we ALSO copy the v3
    per-work files into bucket2/ (after backing up the v1 originals), making an
    accidental argless re-merge reproduce v3, not v1.
  - real_target is identical v1<->v3 (only invented_request changed), so overwriting
    bucket2_all.jsonl does NOT disturb the canonical 228 targets / the regen source.

Backups written (reversible): bucket2_all_v1.jsonl, bucket2_v1_backup/.
"""
import os, shutil, json

PIPE = r"C:\Users\mcgeo\antigravity_projects\~Hemingway\pipeline"
v1_merged = os.path.join(PIPE, "bucket2_all.jsonl")
v3_merged = os.path.join(PIPE, "bucket2_all_v3.jsonl")
v1_backup_merged = os.path.join(PIPE, "bucket2_all_v1.jsonl")
v1_dir = os.path.join(PIPE, "bucket2")
v3_dir = os.path.join(PIPE, "bucket2_v3")
v1_dir_backup = os.path.join(PIPE, "bucket2_v1_backup")

# sanity: both merged files exist and are 228 rows with identical targets
def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

v1 = {r["id"]: r for r in load(v1_merged)}
v3 = {r["id"]: r for r in load(v3_merged)}
assert len(v1) == 228 and len(v3) == 228, f"row count off: v1={len(v1)} v3={len(v3)}"
tgt_mismatch = [i for i in v3 if v1.get(i, {}).get("real_target", v1.get(i, {}).get("span_text")) !=
                v3[i].get("real_target", v3[i].get("span_text"))]
assert not tgt_mismatch, f"TARGET DRIFT on {len(tgt_mismatch)} ids — ABORT: {tgt_mismatch[:5]}"

# 1. back up pristine v1 (merged + per-work dir)
if not os.path.exists(v1_backup_merged):
    shutil.copy(v1_merged, v1_backup_merged)
if os.path.isdir(v1_dir) and not os.path.exists(v1_dir_backup):
    shutil.copytree(v1_dir, v1_dir_backup)

# 2. promote merged
shutil.copy(v3_merged, v1_merged)

# 3. neutralize the argless-gate clobber: copy v3 per-work over bucket2/
os.makedirs(v1_dir, exist_ok=True)
for fn in os.listdir(v3_dir):
    if fn.endswith(".jsonl"):
        shutil.copy(os.path.join(v3_dir, fn), os.path.join(v1_dir, fn))

print("PROMOTED: bucket2_all_v3.jsonl -> bucket2_all.jsonl  (228 rows, targets verified identical)")
print(f"  v1 backed up -> {v1_backup_merged} and {v1_dir_backup}")
print(f"  v3 per-work copied into {v1_dir} (argless-gate clobber neutralized)")
hand = sum(1 for r in v3.values() if r.get("hand_authored"))
print(f"  final set: 228 rows, {hand} hand_authored")
