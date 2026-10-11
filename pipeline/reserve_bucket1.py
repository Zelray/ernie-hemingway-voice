"""
Reserve the FINAL curated Bucket-1 targets -> bucket1_targets.jsonl.

This encodes the hand-curation pass over the selector keepers (full-target human
read): dedup the overlap clusters by eye, drop non-self-contained / non-reflective
spans, TRIM the one diluted gem to its reflective core, fold in the original seed.

INTEGRITY: every target is re-sliced VERBATIM from the cleaned corpus by offset and
its content_hash is re-verified against the selector record (catches offset drift).
Trims are located by curly-apostrophe-safe anchor matching, then the RAW slice is
kept. Gemini text is never used as the target.
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine  # noqa: E402
import importlib.util


def _load(modname, fname):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mine = _load("mine04", "04_mine_passages.py")
WORKS = mine.WORKS
CLEAN_DIR = getattr(mine, "_CLEAN_DIR", os.path.join(HERE, "..", "clean"))
flatten_ws = mine._flatten_ws

SEL = os.path.join(HERE, "bucket1_selected.jsonl")
SEED = os.path.join(HERE, "bucket1_reserved.jsonl")
OUT = os.path.join(HERE, "bucket1_targets.jsonl")

# --- curation decisions, keyed by (work, char_start, word_count) ---
# KEEP whole:
KEEP = {
    ("farewell-to-arms", 59337, 15),    # Nobody knew anything... great positiveness
    ("farewell-to-arms", 71827, 25),    # When people realize how bad it is... never realize
    ("farewell-to-arms", 95042, 16),    # I learn how to do it... smoother and better
    ("farewell-to-arms", 132404, 23),   # God knows I had not wanted to fall in love
    ("farewell-to-arms", 188030, 19),   # The thing was not to recognize it... last country
    ("farewell-to-arms", 196015, 15),   # We were apart as when some one comes into a room
    ("farewell-to-arms", 277925, 19),   # Well, we were in it. Every one was caught in it
    ("farewell-to-arms", 322003, 23),   # The questioners had that beautiful detachment
    ("farewell-to-arms", 333580, 25),   # You had lost your cars... no insurance
    ("farewell-to-arms", 334091, 124),  # Anger was washed away... I would have to stop
    ("farewell-to-arms", 347931, 26),   # feeling of a boy... played truant
    ("farewell-to-arms", 353455, 21),   # We could feel alone when we were together
    ("farewell-to-arms", 353567, 21),   # I have been alone while I was with many girls
    ("farewell-to-arms", 409304, 15),   # The war seemed as far away as football games
    ("men-without-women", 220659, 118),  # silk-worms / "Now I Lay Me" meditation
    ("the-sun-also-rises", 42492, 93),   # I never used to realize it... to hell with people
    ("the-sun-also-rises", 56158, 16),   # association of ideas... dead places in a journey
    ("the-sun-also-rises", 186063, 122),  # Aficion means passion
    ("the-sun-also-rises", 212553, 53),  # Perhaps as you went along... how to live in it
}
# TRIM whole-span -> contiguous reflective core (anchors are verbatim, apostrophe-free):
TRIMS = {
    ("farewell-to-arms", 331875, 140): (
        "Doctors did things to you", "not too much remember."),
}


def curly_safe(s):
    """Length-preserving curly->straight (so .find indices map back to raw)."""
    return s.replace("’", "'").replace("‘", "'").replace(
        "“", '"').replace("”", '"')


def flatten_with_map(raw):
    """Flatten whitespace runs to single spaces (matches _flatten_ws) AND return a
    map from each flat-char index -> its raw index, so anchors found in flat space
    can be sliced back out of the raw string byte-exactly (raw has line-wrap \\n)."""
    flat, idx = [], []
    prev_ws = False
    for k, ch in enumerate(raw):
        if ch.isspace():
            if flat and not prev_ws:
                flat.append(" ")
                idx.append(k)
            prev_ws = True
        else:
            flat.append(ch)
            idx.append(k)
            prev_ws = False
    while flat and flat[-1] == " ":
        flat.pop()
        idx.pop()
    return "".join(flat), idx


def load_corpus():
    return {w: open(os.path.join(CLEAN_DIR, f), encoding="utf-8").read()
            for w, f in WORKS.items()}


def reserve_record(work, cs, ce, corpus, grade="", qkind="", note=""):
    raw = corpus[work][cs:ce]
    span_text = flatten_ws(raw)
    return {
        "id": f"b1_{work}_{cs:08d}",
        "bucket": "1", "work": work,
        "char_start": cs, "char_end": ce,
        "span_text": span_text,
        "word_count": len(span_text.split()),
        "content_hash": spine.content_hash(span_text),
        "grade": grade, "question_kind": qkind, "sel_note": note,
    }


def main():
    corpus = load_corpus()
    sel = [json.loads(l) for l in open(SEL, encoding="utf-8") if l.strip()]
    by_sig = {(r["work"], r["char_start"], r["word_count"]): r for r in sel}

    out = []
    errors = []

    # KEEP whole
    for sig in KEEP:
        r = by_sig.get(sig)
        if not r:
            errors.append(f"KEEP sig not found: {sig}")
            continue
        rec = reserve_record(r["work"], r["char_start"], r["char_end"], corpus,
                             r.get("grade", ""), r.get("question_kind", ""), "keep")
        if rec["content_hash"] != r["content_hash"]:
            errors.append(f"HASH MISMATCH on KEEP {sig}: corpus reslice != selector")
        out.append(rec)

    # TRIM to reflective core
    for sig, (a_start, a_end) in TRIMS.items():
        r = by_sig.get(sig)
        if not r:
            errors.append(f"TRIM sig not found: {sig}")
            continue
        cs, ce = r["char_start"], r["char_end"]
        raw_span = corpus[r["work"]][cs:ce]
        flat, idx = flatten_with_map(raw_span)
        cflat = curly_safe(flat)
        i = cflat.find(curly_safe(a_start))
        j = cflat.find(curly_safe(a_end))
        if i < 0 or j < 0:
            errors.append(f"TRIM anchor not found for {sig}: start={i} end={j}")
            continue
        j_flat_end = j + len(a_end)
        cs2 = cs + idx[i]
        ce2 = cs + idx[j_flat_end - 1] + 1
        rec = reserve_record(r["work"], cs2, ce2, corpus,
                             r.get("grade", ""), r.get("question_kind", ""), "trim")
        out.append(rec)

    # Seed (the original hard-coded aphorism) — re-slice + verify
    seed = json.loads(open(SEED, encoding="utf-8").readline())
    srec = reserve_record(seed["work"], seed["char_start"], seed["char_end"], corpus,
                          "seed", "How does the world treat the brave?", "seed")
    if srec["content_hash"] != seed["content_hash"]:
        errors.append("HASH MISMATCH on SEED reslice")
    out.append(srec)

    out.sort(key=lambda r: (r["work"], r["char_start"]))
    if os.path.exists(OUT):
        os.remove(OUT)
    for rec in out:
        spine.append_record(OUT, rec)

    # report
    by_work = {}
    for r in out:
        by_work[r["work"]] = by_work.get(r["work"], 0) + 1
    print(f"reserved {len(out)} bucket-1 targets -> {OUT}")
    print(f"  by work: {by_work}")
    wc = [r["word_count"] for r in out]
    print(f"  word_count: min {min(wc)}  median {sorted(wc)[len(wc)//2]}  max {max(wc)}")
    print(f"  ERRORS: {errors if errors else 'none'}")
    print("\n--- final reserved targets (id | wc | text head) ---")
    for r in out:
        print(f"  {r['id']}  w{r['word_count']:<3} | {r['span_text'][:90]}")


if __name__ == "__main__":
    main()
