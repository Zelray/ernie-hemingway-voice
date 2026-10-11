"""
hand_fix_bucket1.py — apply the panel-driven hand-fixes to bucket-1 questions.

Represents the FINAL desired question text for every hand-authored row, plus the
rows to DROP. Idempotent: re-running converges to this exact state.

History (the leak<->answerable seesaw on short reflective passages):
  PASS 1 fixed 7 ANSWERABILITY HARD-fails (panel-sourced rewrites).
  The changed-rows RE-REVIEW then cleared 4 but flipped 3 to LEAK (the rewrites
  restated the passage's payoff). PASS 2 (this file, per the CONVERGENCE STOP
  RULE — hand-author, do NOT loop the panel):
    - 00333580: re-aimed so it asks how you PROCESS the loss; the passage supplies
      the "no insurance" punch (no longer leaked).
    - 00353567: made an OPEN question ("when?") so the passage delivers the
      surprising "with many girls" answer instead of the question pre-stating it.
    - 00277925: DROPPED — single-observation + context-dependent "it"; no honest
      question is both answerable and non-restating (advisor-blessed drop). 21->20.

Reads bucket1_requests/<work>.jsonl, sets invented_question for FIXES ids
(preserving the ORIGINAL question as prior_question), removes DROP_IDS rows, and
rewrites each file atomically.

RUN (Bash): python pipeline/hand_fix_bucket1.py
"""
import os
import sys
import json
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "bucket1_requests")

FIXES = {
    "b1_farewell-to-arms_00196015":
        "What does it feel like when the ease between two people suddenly turns stiff?",
    "b1_farewell-to-arms_00333580":
        "How do you take it in when everything you were responsible for is suddenly gone?",
    "b1_farewell-to-arms_00353455":
        "How many times in a life do you find someone you can take on everyone with?",
    "b1_farewell-to-arms_00353567":
        "When do you feel the most cut off from other people?",
    "b1_men-without-women_00220659":
        "What gets you through a night when sleep won't come?",
    "b1_the-sun-also-rises_00056158":
        "Why does one stretch of a trip suddenly feel flat when nothing about it has changed?",
}
DROP_IDS = {
    "b1_farewell-to-arms_00277925",   # irreducible leak<->answerable seesaw + context-dependent "it"
}


def work_of(_id):
    """id = b1_<work>_<zero-padded-offset>; <work> may contain hyphens."""
    return _id[len("b1_"):].rsplit("_", 1)[0]


def main():
    by_file = defaultdict(dict)
    for fid, q in FIXES.items():
        by_file[work_of(fid)][fid] = q
    drop_by_file = defaultdict(set)
    for did in DROP_IDS:
        drop_by_file[work_of(did)].add(did)

    works = set(by_file) | set(drop_by_file)
    changed = dropped = 0
    for work in works:
        path = os.path.join(DIR, work + ".jsonl")
        if not os.path.exists(path):
            print(f"[FATAL] missing {path}")
            sys.exit(2)
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        ids_here = {r["id"] for r in rows}
        for fid in list(by_file[work]) + list(drop_by_file[work]):
            if fid not in ids_here:
                print(f"[FATAL] {fid} not found in {work}.jsonl")
                sys.exit(2)

        out = []
        for r in rows:
            if r["id"] in drop_by_file[work]:
                dropped += 1
                continue
            if r["id"] in by_file[work] and r.get("invented_question") != by_file[work][r["id"]]:
                if "prior_question" not in r:                 # keep the ORIGINAL across passes
                    r["prior_question"] = r.get("invented_question")
                r["invented_question"] = by_file[work][r["id"]]
                r["hand_authored"] = True
                r["hand_fix_reason"] = "panel: answerability+leak (converged)"
                changed += 1
            out.append(r)

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, path)

    print(f"CHANGED={changed}  DROPPED={dropped}  (expect CHANGED>=2, DROPPED=1)")


if __name__ == "__main__":
    main()
