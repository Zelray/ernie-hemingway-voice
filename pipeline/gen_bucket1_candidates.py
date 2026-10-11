"""
Bucket-1 candidate miner — find REFLECTIVE, answer-shaped Hemingway spans.

WHY: bucket1_reserved.jsonl holds a single HARD-CODED aphorism ("the world breaks
every one"). To build Bucket 1 (reflective Q&A by back-translation) we must first
MINE ~40 reflective spans. This is the SCARCEST thing in the corpus (Hemingway's
iceberg style hides interiority), so the strategy is:

    deterministic WIDE-NET scorer here (recall-biased) -> Gemini SELECTION (next
    step) does the precision sort -> reserve the genuine keepers.

INTEGRITY: this script SLICES verbatim spans by offset; it never rewrites prose.
It REUSES 04_mine_passages.py segmentation + clean-prose filters so Bucket-1 spans
are cut identically to buckets 2/3. No API calls; pure stdlib + spine + mine04.

OUTPUT: pipeline/bucket1_candidates.jsonl (ranked) + a compact stdout summary.
"""
import os
import re
import sys
import json
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine  # noqa: E402


def _load(modname, fname):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mine = _load("mine04", "04_mine_passages.py")

WORKS = mine.WORKS
CLEAN_DIR = getattr(mine, "_CLEAN_DIR", os.path.join(HERE, "..", "clean"))
PARA = mine._PARA
flatten_ws = mine._flatten_ws
group_spans = mine._group_spans
is_prose_paragraph = mine.is_prose_paragraph
span_is_clean = mine.span_is_clean
propernoun_ratio = mine.propernoun_ratio
split_sentences = mine.split_sentences

OUT = os.path.join(HERE, "bucket1_candidates.jsonl")
SHORT_MIN, SHORT_MAX = 15, 40   # sub-paragraph reflective gems (aphorisms run short)
CAND_FLOOR = 1.0                # keep anything scoring above this; tuned for recall

# ---------------------------------------------------------------- lexicons
# Generalizing subjects: a passage ABOUT people/life/the world, not a scene.
# NOTE: "you"/"your" deliberately EXCLUDED — in Hemingway "you" is overwhelmingly
# dialogue ADDRESS, not generic-you; including it ranked conversation as reflection.
GENERIC_SUBJ = {
    "one", "people", "man", "men", "woman", "women", "everybody",
    "everyone", "nobody", "anybody", "anyone", "somebody", "world", "life",
    "lives", "things", "nothing", "everything", "anything", "something", "folks",
    "person", "human", "humans",
}
# Strong gnomic signal: the SUBJECT of a sentence is generic (checked at sent start).
# "you"/"when"/"if" excluded — too common in dialogue ("When did you...", "If you...").
GENERIC_START = {
    "one", "people", "man", "men", "world", "life", "everybody",
    "everyone", "nobody", "nothing", "everything", "love", "death", "war",
    "things",
}
COGN_FEEL = {
    "know", "knew", "knows", "think", "thought", "thinks", "feel", "felt",
    "feels", "believe", "believed", "understand", "understood", "learn",
    "learned", "learns", "realize", "realized", "care", "cared", "matter",
    "mattered", "matters", "mean", "meant", "means", "remember", "remembered",
    "forget", "forgot", "wonder", "wondered", "suppose", "supposed", "hope",
    "hoped", "afraid", "ashamed", "lonely", "tired", "sure", "wish", "wished",
}
ABSTRACT = {
    "courage", "love", "death", "dead", "life", "fear", "pain", "faith", "war",
    "time", "truth", "hope", "loneliness", "happiness", "world", "heart",
    "soul", "mind", "luck", "honor", "glory", "sacrifice", "peace", "sin",
    "grace", "dignity", "strength", "brave", "good", "evil", "gentle", "kind",
    "cruel", "beauty", "joy", "sorrow", "grief", "despair", "nerve", "guts",
    "wisdom", "fool", "coward", "brave",
}
ABSOLUTES = {
    "never", "always", "every", "all", "none", "nothing", "everyone",
    "everybody", "everything", "must", "ever", "cannot", "nobody", "forever",
}
# Concrete scene/action -> NOT reflective. Penalty. (kill/break/live/love/die
# deliberately ABSENT — they recur in genuine reflective/gnomic passages.)
MOTION = {
    # motion / posture
    "walked", "walk", "went", "came", "come", "sat", "sit", "stood", "stand",
    "ran", "run", "rode", "ride", "drove", "drive", "climbed", "climb", "fell",
    "rose", "leaned", "lean", "jumped", "jump", "rowed", "row", "swung", "swing",
    # transitive action (narrative agency)
    "poured", "drank", "drink", "ate", "eat", "looked", "look", "turned", "turn",
    "opened", "open", "closed", "picked", "put", "took", "take", "taken", "got",
    "shot", "shoot", "made", "make", "gave", "give", "given", "lifted", "lift",
    "held", "hold", "carried", "carry", "pushed", "push", "pulled", "pull",
    "threw", "throw", "caught", "catch", "brought", "bring", "sent", "paid",
    "pay", "bought", "buy", "dropped", "kicked", "reached", "reach", "grabbed",
    "fired", "knocked", "hung", "hang", "spilled", "wore", "wear",
    # concrete scene nouns
    "road", "street", "table", "glass", "door", "window", "car", "train",
    "horse", "gun", "bottle", "wine", "bed", "room", "hill", "river", "café",
    "cafe", "money", "francs", "bridge", "rain", "snow", "wagon", "arena",
    "counter", "deer", "beard", "beards", "hat", "basement", "boat", "oars",
    "seat", "box", "wall", "floor", "field", "garden", "kitchen",
}
BACKREF_OPENERS = {"but", "and", "so", "then", "yet", "however", "because",
                   "still", "also", "besides", "though", "anyway", "meanwhile"}
DEP_PRONOUN_OPENERS = {"it", "they", "he", "she", "this", "that", "these",
                       "those", "there", "him", "her", "them"}

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def toks(s):
    return [w.lower() for w in _WORD.findall(s)]


def reflect_score(span_text):
    """Weighted density of reflective markers minus scene/concrete penalties.
    Recall-biased ranker, NOT a classifier. Returns (score, feature_dict)."""
    sents = [s for s in re.split(r"(?<=[.!?])\s+", span_text.strip()) if s]
    tk = toks(span_text)
    n = max(1, len(tk))
    ns = max(1, len(sents))

    def density(vocab):
        return sum(t in vocab for t in tk) / n

    generic_start = 0
    for s in sents:
        head = toks(s)[:3]
        if any(h in GENERIC_START for h in head):
            generic_start += 1
    generic_start /= ns

    first = tk[0] if tk else ""
    backref = 1 if (first in BACKREF_OPENERS or first in DEP_PRONOUN_OPENERS) else 0

    f = {
        "generic_start": round(generic_start, 3),
        "generic_subj": round(density(GENERIC_SUBJ), 4),
        "cogn_feel": round(density(COGN_FEEL), 4),
        "abstract": round(density(ABSTRACT), 4),
        "absolutes": round(density(ABSOLUTES), 4),
        "motion": round(density(MOTION), 4),
        "pn_density": round(propernoun_ratio(span_text), 4),
        "backref_opener": backref,
    }
    score = (
        18.0 * f["generic_start"]
        + 35.0 * f["generic_subj"]
        + 35.0 * f["cogn_feel"]
        + 30.0 * f["abstract"]
        + 25.0 * f["absolutes"]
        - 20.0 * f["motion"]
        - 15.0 * f["pn_density"]
        - 4.0 * f["backref_opener"]
    )
    return round(score, 3), f


# A reflective ANSWER passage is declarative, not a question or narrated talk.
_REPORTED_SPEECH = re.compile(
    r"\b(said|asked|answered|replied|told|shouted|cried|whispered|called|"
    r"remarked|murmured|repeated|added|inquired|exclaimed)\b", re.I)


def is_dialogue_like(span_text):
    if "?" in span_text:
        return True
    if _REPORTED_SPEECH.search(span_text):
        return True
    return False


# ---------------------------------------------------------------- registry
def _subrecords(r):
    """Yield r and any nested dicts that might carry work+offsets (dress pairs)."""
    yield r
    for k in ("target", "answer", "source", "span", "real", "pair"):
        v = r.get(k)
        if isinstance(v, dict):
            yield v


def load_registry():
    reg = spine.SpanRegistry()
    seen_hashes = set()
    counts = {}
    for fname, bucket in [
        ("bucket2_all.jsonl", "2"),
        ("bucket3_all.jsonl", "3"),
        ("dress_rehearsal_pairs.jsonl", "dress"),
        ("bucket1_reserved.jsonl", "1"),
    ]:
        path = os.path.join(HERE, fname)
        c = 0
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for rec in _subrecords(r):
                    w, cs, ce = rec.get("work"), rec.get("char_start"), rec.get("char_end")
                    if w and isinstance(cs, int) and isinstance(ce, int):
                        reg.claim(w, cs, ce, bucket)
                        c += 1
                    h = rec.get("content_hash")
                    if h:
                        seen_hashes.add(h)
        counts[fname] = c
    return reg, seen_hashes, counts


# ---------------------------------------------------------------- mining
def short_spans(para, pstart):
    """Single + adjacent-pair sentences, SHORT_MIN..SHORT_MAX words, self-contained."""
    sents = split_sentences(para)
    out = []
    spans = [(s, e) for (s, e) in sents]
    # singles
    groups = [(s, e) for (s, e) in spans]
    # adjacent pairs
    for i in range(len(spans) - 1):
        groups.append((spans[i][0], spans[i + 1][1]))
    for (s, e) in groups:
        txt = flatten_ws(para[s:e])
        wc = len(txt.split())
        if SHORT_MIN <= wc <= SHORT_MAX:
            out.append((pstart + s, pstart + e, txt, wc))
    return out


def mine():
    reg, seen_hashes, reg_counts = load_registry()
    cands = []
    considered = 0
    standard_ranges = {}  # work -> list of (cs, ce) of accepted standard cands

    def accept(work, cs, ce, span_text, wc, mode):
        nonlocal considered
        considered += 1
        if not span_is_clean(span_text, work):
            return
        if is_dialogue_like(span_text):
            return
        if reg.overlaps(work, cs, ce):
            return
        h = spine.content_hash(span_text)
        if h in seen_hashes:
            return
        score, feats = reflect_score(span_text)
        if score < CAND_FLOOR:
            return
        seen_hashes.add(h)  # de-dupe candidates against each other too
        rec = {
            "id": f"b1cand_{work}_{cs:08d}",
            "bucket": "1",
            "work": work,
            "char_start": cs,
            "char_end": ce,
            "span_text": span_text,
            "word_count": wc,
            "content_hash": h,
            "span_mode": mode,
            "reflect_score": score,
            "score_feats": feats,
        }
        cands.append(rec)
        if mode == "standard":
            standard_ranges.setdefault(work, []).append((cs, ce))

    for work, fname in WORKS.items():
        text = open(os.path.join(CLEAN_DIR, fname), encoding="utf-8").read()
        for pm in PARA.finditer(text):
            para, pstart = pm.group(0), pm.start()
            if not is_prose_paragraph(para):
                continue
            for (cs, ce, span_text, wc) in group_spans(para, pstart):
                accept(work, cs, ce, span_text, wc, "standard")
            for (cs, ce, span_text, wc) in short_spans(para, pstart):
                # coherence guard for short fragments: no back-ref / dependent opener
                head = toks(span_text)[:1]
                if head and (head[0] in BACKREF_OPENERS or head[0] in DEP_PRONOUN_OPENERS):
                    continue
                accept(work, cs, ce, span_text, wc, "short")

    # drop short cands fully contained in an accepted standard cand (keep gems whose
    # containing paragraph-span did NOT itself qualify)
    def contained(work, cs, ce):
        for (s, e) in standard_ranges.get(work, []):
            if s <= cs and ce <= e:
                return True
        return False

    cands = [c for c in cands
             if not (c["span_mode"] == "short" and contained(c["work"], c["char_start"], c["char_end"]))]

    cands.sort(key=lambda c: c["reflect_score"], reverse=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    for c in cands:
        spine.append_record(OUT, c)
    return cands, considered, reg_counts


# ---------------------------------------------------------------- summary
def seed_score():
    """Score the known reserved aphorism as a sanity anchor."""
    path = os.path.join(HERE, "bucket1_reserved.jsonl")
    if not os.path.exists(path):
        return None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        sc, _ = reflect_score(r["span_text"])
        return sc, r["span_text"][:60]
    return None


def summarize(cands, considered, reg_counts):
    print("=" * 64)
    print("BUCKET-1 CANDIDATE MINER — wide-net reflectiveness pass")
    print("=" * 64)
    print(f"registry claimed (overlap-excluded): {reg_counts}")
    print(f"clean spans considered: {considered}")
    print(f"candidates above floor ({CAND_FLOOR}): {len(cands)}")
    by_mode = {}
    by_work = {}
    for c in cands:
        by_mode[c["span_mode"]] = by_mode.get(c["span_mode"], 0) + 1
        by_work[c["work"]] = by_work.get(c["work"], 0) + 1
    print(f"  by mode: {by_mode}")
    print(f"  by work: {by_work}")

    sc = seed_score()
    if sc:
        s_score, s_head = sc
        rank = sum(1 for c in cands if c["reflect_score"] > s_score)
        print(f"seed anchor ('{s_head}...') score={s_score}  "
              f"would rank #{rank + 1} of {len(cands)}")

    scores = [c["reflect_score"] for c in cands]
    print("\nscore distribution (count by band):")
    bands = [(8, 99), (6, 8), (5, 6), (4, 5), (3, 4), (2, 3), (1, 2)]
    for lo, hi in bands:
        n = sum(1 for s in scores if lo <= s < hi)
        bar = "#" * min(60, n)
        print(f"  [{lo:>2}-{hi if hi < 99 else 'max':>3}): {n:>4} {bar}")

    # quality cliff: biggest score drop in the top 80
    top = cands[:80]
    cliff_i, cliff_gap = 0, 0.0
    for i in range(1, len(top)):
        gap = top[i - 1]["reflect_score"] - top[i]["reflect_score"]
        if gap > cliff_gap:
            cliff_gap, cliff_i = gap, i
    if top:
        print(f"\nlargest score gap in top-80 at rank #{cliff_i} "
              f"(gap {round(cliff_gap, 2)}; "
              f"{top[cliff_i-1]['reflect_score']} -> {top[cliff_i]['reflect_score']})")

    def show(c):
        t = c["span_text"]
        t = (t[:150] + "…") if len(t) > 150 else t
        return (f"  [{c['reflect_score']:>5}] {c['span_mode']:<8} {c['work'][:14]:<14} "
                f"w{c['word_count']:<3} | {t}")

    print("\n--- TOP 12 candidates (all modes) ---")
    for c in cands[:12]:
        print(show(c))
    print("\n--- TOP 10 STANDARD-mode (richer multi-sentence reflective paras) ---")
    for c in [c for c in cands if c["span_mode"] == "standard"][:10]:
        print(show(c))
    mid = len(cands) // 2
    print(f"\n--- 4 MID-BAND (around rank {mid}) ---")
    for c in cands[mid:mid + 4]:
        print(show(c))
    print("\n--- BOTTOM 4 (near floor) ---")
    for c in cands[-4:]:
        print(show(c))
    print("\nwrote:", OUT)


if __name__ == "__main__":
    cands, considered, reg_counts = mine()
    summarize(cands, considered, reg_counts)
