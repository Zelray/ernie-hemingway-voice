"""
spine.py — the data-integrity backbone every dataset generator writes through.

WHY THIS EXISTS (plain English):
  We are about to mine ~640 real-Hemingway spans (buckets 1/2/3) and generate
  ~560 Gemini answers (bucket 4) into one training set. Two silent killers can
  quietly inflate our eval win-rate and ruin the fine-tune:
    1. DUPLICATES / NEAR-DUPES — the same passage mined twice, or a short span
       that sits entirely inside a longer span another bucket already used.
    2. TRAIN/EVAL LEAKAGE — a passage (or a near-twin of it) landing in BOTH the
       training set and the held-out eval set, so the model "wins" by memorizing.

  This module is the shared toolkit that stops both. It is deliberately LEAN:
  this is a ~640-span problem, not a million-document one, so we use EXACT
  word-n-gram set math (pure Python stdlib) — no MinHash, no LSH, no third-party
  libraries. Exact comparison over a few hundred spans is fast and obvious.

  ★ Insight — "content hash" vs "fuzzy match" are two different jobs:
    - content_hash() catches BYTE-FOR-BYTE repeats (after normalizing case /
      whitespace / surrounding punctuation). Cheap, exact, O(1) set lookup.
    - five_gram_jaccard() / containment() catch NEAR-twins that aren't identical
      (a passage re-mined with one extra sentence, or a span nested in a bigger
      one). These are O(n*m) over spans, fine at our scale.

STDLIB ONLY: hashlib, json, re, os (+ tempfile in the self-test). No pip installs.

RUN THE SELF-TEST (Bash; PowerShell hangs this box):
  python pipeline/spine.py
"""
import hashlib
import json
import os
import re

# ── Record schema (the one shape every generator appends) ────────────────────
# Standardize on these field names so dedup, resume, and the group-split all
# read the same keys no matter which bucket wrote the row.
RECORD_FIELDS = (
    "id",            # stable unique id, e.g. "b3_farewell_000123"
    "bucket",        # 1 | 2 | 3 | 4
    "work",          # source work slug, e.g. "farewell-to-arms"
    "char_start",    # span start offset in the cleaned source file
    "char_end",      # span end offset (half-open: [char_start, char_end))
    "span_text",     # the real-Hemingway span (the training TARGET for 1/2/3)
    "content_hash",  # content_hash(span_text) — the dedup / split key
    # optional, bucket-3 (flatten-restore) only:
    "flattened_input",  # Gemini's voiceless flatten == the training INPUT
    "real_target",      # == span_text, named for clarity at training time
)

# Matches runs of word characters. Used for n-gram tokenization (drops the
# commas/quotes/periods that would otherwise split "white" and "white," apart).
_WORD = re.compile(r"\w+", re.UNICODE)


# ── Normalization + exact content hashing ────────────────────────────────────
def normalize(text):
    """Canonical form for hashing: lowercase, collapse all whitespace to single
    spaces, strip surrounding punctuation/whitespace. So '"Hello,  world."' and
    'hello world' collapse to the same canonical string 'hello, world' vs
    'hello world' — note INTERNAL punctuation is preserved (only the ENDS are
    stripped); that is intentional, normalize() is for hashing whole spans, the
    n-gram functions below do the word-level tokenizing."""
    s = text.lower()
    s = re.sub(r"\s+", " ", s)          # collapse every whitespace run -> 1 space
    s = re.sub(r"^[^\w]+", "", s)        # strip leading punctuation/space
    s = re.sub(r"[^\w]+$", "", s)        # strip trailing punctuation/space
    return s


def content_hash(text):
    """Stable SHA-1 of the normalized text. Same passage (modulo case/whitespace/
    edge punctuation) -> same hash -> exact-duplicate detection in O(1)."""
    return hashlib.sha1(normalize(text).encode("utf-8")).hexdigest()


# ── n-gram set helpers (the fuzzy / near-dup math) ───────────────────────────
def _tokens(text):
    """Lowercased word tokens — the unit of all n-gram comparisons."""
    return _WORD.findall(text.lower())


def _ngrams(tokens, n):
    """Set of contiguous n-grams (as tuples) over a token list. If the text is
    shorter than n, fall back to one gram = the whole token tuple, so short
    spans still compare sensibly instead of yielding an empty set."""
    if not tokens:
        return set()
    if len(tokens) < n:
        return {tuple(tokens)}
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _jaccard(set_a, set_b):
    """|A ∩ B| / |A ∪ B|. Two empty sets count as identical (1.0); one empty
    and one not count as disjoint (0.0)."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def five_gram_jaccard(a, b):
    """EXACT word-5-gram Jaccard similarity in [0.0, 1.0]. Our near-duplicate
    test: flag a pair as a near-dup when this is >= 0.6. Identical text -> 1.0;
    text sharing no 5-word run -> 0.0."""
    return _jaccard(_ngrams(_tokens(a), 5), _ngrams(_tokens(b), 5))


def containment(a, b, n=8):
    """|A ∩ B| / min(|A|, |B|) over word-8-gram sets — an ASYMMETRIC overlap that
    detects a short span sitting fully INSIDE a long one. Used at SPLIT time:
    flag at >= 0.8 so a short passage nested in a longer passage can't straddle
    train/eval. (If a span is shorter than n words, n is reduced to the shorter
    span's length so the comparison stays meaningful instead of degenerating to
    0.) Returns a value in [0.0, 1.0]."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    eff_n = min(n, len(ta), len(tb))
    set_a, set_b = _ngrams(ta, eff_n), _ngrams(tb, eff_n)
    denom = min(len(set_a), len(set_b))
    if denom == 0:
        return 0.0
    return len(set_a & set_b) / denom


# ── Crash-safe JSONL streaming (write one row, flush to disk, every time) ─────
def append_record(path, record_dict):
    """Append ONE JSON object as a single line (JSONL), flushed and fsync'd to
    disk immediately. This is what makes a paid generation run crash-safe: if the
    process dies mid-batch, every row written before the crash is already
    durable, and load_done_ids() lets us resume without re-paying for them."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())   # force OS buffers to physical disk -> crash-safe


def load_done_ids(path, id_field="id"):
    """Return the set of ids already present in a JSONL file, for idempotent
    resume. A torn final line (a crash mid-write) is skipped rather than
    crashing the loader — that is the whole point of crash-safe resume."""
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue   # partial/torn line from a crash — ignore, don't die
            if id_field in rec:
                done.add(rec[id_field])
    return done


# ── Global span registry (no two buckets reuse the same passage) ─────────────
class SpanRegistry:
    """Tracks every (work, char_start, char_end) span claimed across ALL buckets,
    so a later bucket can't silently reuse a character range an earlier bucket
    already mined. Offsets are half-open intervals [start, end) into the cleaned
    source file. Overlap is true interval-intersection, so even a PARTIAL overlap
    (a span that shares some characters with an already-claimed one) is caught,
    not just exact-range repeats."""

    def __init__(self):
        # work slug -> list of (start, end, bucket) already claimed
        self._by_work = {}

    def overlaps(self, work, start, end):
        """True if [start, end) intersects any span already claimed for `work`."""
        for (s, e, _bucket) in self._by_work.get(work, ()):
            if start < e and s < end:   # half-open interval intersection
                return True
        return False

    def claim(self, work, start, end, bucket):
        """Try to claim [start, end) for `work` on behalf of `bucket`. Returns
        True and records the claim if the range is free; returns False (and
        records nothing) if it overlaps an existing claim — the caller should
        then SKIP this span and mine another. This makes mining idempotent: the
        same span offered twice is claimed at most once."""
        if self.overlaps(work, start, end):
            return False
        self._by_work.setdefault(work, []).append((start, end, bucket))
        return True

    def claimed_count(self, work=None):
        """How many spans are claimed — for a single work, or globally if work
        is None. Handy for build-time logging/acceptance reporting."""
        if work is not None:
            return len(self._by_work.get(work, ()))
        return sum(len(v) for v in self._by_work.values())


# ── Self-test (no API, no money) ─────────────────────────────────────────────
def _smoke_test():
    import tempfile

    # 1) normalize + content_hash: invariant to case / whitespace / EDGE punctuation
    #    (internal punctuation like the comma is preserved on purpose).
    assert normalize('  "Hello,   WORLD."  ') == "hello, world"
    assert content_hash('  "Hello,  world."  ') == content_hash("Hello, world")
    assert content_hash("a totally different string") != content_hash("hello world")
    print("  [pass] normalize + content_hash are canonical & stable")

    # 2) five_gram_jaccard: identical -> 1.0 ; disjoint -> 0.0
    txt = "in the late summer of that year we lived in a house in a village"
    assert five_gram_jaccard(txt, txt) == 1.0
    other = "completely unrelated wording sharing none of the same running phrases here"
    assert five_gram_jaccard(txt, other) == 0.0
    # a near-dup (same span re-mined with a short trailing clause) clears 0.6
    near = txt + " near the mountains"
    assert five_gram_jaccard(txt, near) >= 0.6
    print("  [pass] five_gram_jaccard: 1.0 identical / 0.0 disjoint / >=0.6 near-dup")

    # 3) containment: a short span fully inside a long one -> ~1.0
    long_span = ("in the late summer of that year we lived in a house in a village "
                 "that looked across the river and the plain to the mountains")
    short_span = "we lived in a house in a village"   # verbatim substring, 8 words
    assert containment(short_span, long_span) == 1.0
    assert containment(short_span, other) < 0.8        # unrelated -> below split bar
    print("  [pass] containment: nested span ~1.0 / unrelated < 0.8")

    # 4) append_record + load_done_ids round-trip an id (crash-safe resume)
    tmp_dir = tempfile.mkdtemp(prefix="spine_smoke_")
    jsonl = os.path.join(tmp_dir, "out.jsonl")
    rec = {"id": "b3_farewell_000123", "bucket": 3, "work": "farewell-to-arms",
           "char_start": 100, "char_end": 240, "span_text": long_span,
           "content_hash": content_hash(long_span)}
    append_record(jsonl, rec)
    append_record(jsonl, {"id": "b2_sun_000001", "bucket": 2})
    done = load_done_ids(jsonl)
    assert done == {"b3_farewell_000123", "b2_sun_000001"}, done
    # idempotent resume: a torn final line is skipped, not fatal
    with open(jsonl, "a", encoding="utf-8") as f:
        f.write('{"id": "b4_partial", "bu')   # simulate a crash mid-write
    assert load_done_ids(jsonl) == {"b3_farewell_000123", "b2_sun_000001"}
    os.remove(jsonl)
    os.rmdir(tmp_dir)
    print("  [pass] append_record + load_done_ids round-trip & survive a torn line")

    # 5) SpanRegistry: claim once, block overlaps, allow disjoint
    reg = SpanRegistry()
    assert reg.claim("farewell-to-arms", 0, 100, bucket=3) is True
    assert reg.overlaps("farewell-to-arms", 50, 150) is True     # partial overlap
    assert reg.claim("farewell-to-arms", 50, 150, bucket=2) is False  # blocked
    assert reg.claim("farewell-to-arms", 100, 200, bucket=2) is True  # disjoint OK
    assert reg.overlaps("the-sun-also-rises", 0, 100) is False   # other work, free
    assert reg.claimed_count("farewell-to-arms") == 2
    assert reg.claimed_count() == 2
    print("  [pass] SpanRegistry: claims, blocks overlaps, isolates by work")


if __name__ == "__main__":
    print("spine.py self-test (no API, no money):")
    _smoke_test()
    print("ALL SMOKE TESTS PASSED.")
