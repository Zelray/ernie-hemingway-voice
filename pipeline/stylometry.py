"""
stylometry.py — the ONE frozen sentence-rhythm toolkit for Bucket 4.

WHY THIS EXISTS (plain English):
  Bucket 4 is the only bucket where Gemini IMITATES Hemingway. The #1 failure of
  any "write like Hemingway" prompt is CARICATURE: it collapses into all-short,
  all-choppy fragments ("It was good. The wine was good. He was tired."). Real
  Hemingway does the opposite of a caricature — he MIXES tiny 4-word punches with
  long 25-word flowing sentences. The *variance* is the signature, not shortness.

  To catch caricature we measure sentence rhythm and compare a generated answer to
  what a REAL Hemingway paragraph looks like. That comparison is only valid if the
  SAME splitter measures both sides. So this module is the single source of truth:
  the reference builder and the gate both import split_sentences() from here. If we
  ever changed the splitter, both the reference distribution and the live
  measurement shift together and stay comparable.

  ★ Insight — measure at ANSWER scale, not corpus scale. A 5-sentence answer can't
    have the variance of a 90,000-word novel. So the reference is built from
    ~answer-sized CHUNKS of the corpus (see build_style_reference.py), and every
    metric here is computed per-passage so a chunk and an answer are apples-to-apples.

STDLIB ONLY for the splitter/metrics (re, statistics). numpy is used only by the
reference builder for percentiles; this module stays import-light.

RUN THE SELF-TEST (Bash; PowerShell hangs this box):
  python pipeline/stylometry.py
"""
import re
import statistics

# Abbreviations that end in a period but DON'T end a sentence. Kept small and
# Hemingway-relevant: he rarely uses titles, but "Mr./Mrs./Dr." and military/
# place abbreviations do appear, and a lone capital initial ("F. Puttkamer") must
# not split. We mask these before splitting, then unmask.
_ABBREV = (
    "mr", "mrs", "ms", "dr", "st", "lt", "col", "gen", "capt", "sgt", "maj",
    "sig", "sigra", "ave", "no", "vs", "etc", "jr", "sr",
)
_ABBREV_RE = re.compile(
    r"\b(" + "|".join(_ABBREV) + r")\.", re.IGNORECASE)
# A single capital letter followed by a period = an initial (F. Scott). Mask it.
_INITIAL_RE = re.compile(r"\b([A-Z])\.")
# A period between two digits (decimals, 3.50) — mask so it never splits.
_DECIMAL_RE = re.compile(r"(\d)\.(\d)")

_SENT_BOUNDARY = re.compile(r'(?<=[.!?])["\'”’)]*\s+')
_WORD = re.compile(r"[A-Za-z'’]+")

# Sentinel that won't occur in clean prose; marks a masked, non-splitting period.
_DOT = ""


def split_sentences(text):
    """Split prose into sentences. Deliberately simple and DETERMINISTIC: clean
    digital text (our corpus and Gemini's output) doesn't need a parser. We mask
    abbreviation/initial/decimal periods so they can't trigger a false split, cut
    on sentence-final punctuation followed by whitespace (carrying any trailing
    close-quote/paren with the sentence it ends), then unmask.

    Returns a list of non-empty sentence strings."""
    if not text:
        return []
    s = re.sub(r"\s+", " ", text).strip()
    s = _DECIMAL_RE.sub(lambda m: m.group(1) + _DOT + m.group(2), s)
    s = _ABBREV_RE.sub(lambda m: m.group(1) + _DOT, s)
    s = _INITIAL_RE.sub(lambda m: m.group(1) + _DOT, s)
    parts = _SENT_BOUNDARY.split(s)
    out = []
    for p in parts:
        p = p.replace(_DOT, ".").strip()
        if p:
            out.append(p)
    return out


def word_count(sentence):
    """Words in a sentence = runs of letters/apostrophes (numbers and bare
    punctuation don't count toward sentence LENGTH rhythm)."""
    return len(_WORD.findall(sentence))


def sentence_lengths(text):
    """List of per-sentence word counts (drops empty/0-word sentences)."""
    return [n for n in (word_count(s) for s in split_sentences(text)) if n > 0]


# Thresholds that define "fragment" and "long flowing sentence" for the rhythm
# metrics. Tuned to Hemingway's corpus: fragments are his ≤5-word punches; a
# "long" sentence (≥18 words) is the flowing, polysyndeton-chained kind a
# caricature never produces.
FRAGMENT_MAX = 5
LONG_MIN = 18


def style_metrics(text):
    """The per-passage rhythm fingerprint — computed identically on a corpus chunk
    and on a generated answer. Returns a dict:
      n_sents      : sentence count
      n_words      : total words
      mean_len     : mean sentence length (words)
      stdev_len    : population stdev of sentence length (the VARIANCE signal)
      max_len      : longest sentence (the 'has a flowing sentence?' signal)
      frag_rate    : fraction of sentences with <= FRAGMENT_MAX words
      long_rate    : fraction of sentences with >= LONG_MIN words
      max_consec_frag : longest run of consecutive fragment sentences (caricature
                        tell — 'It was good. He was tired. The wine was cold.')
      and_frac     : fraction of all word-tokens that are 'and' (polysyndeton)
    Returns {} for empty input."""
    sents = split_sentences(text)
    lens = [word_count(s) for s in sents]
    lens = [n for n in lens if n > 0]
    if not lens:
        return {}
    n_words = sum(lens)
    # longest run of consecutive fragments
    max_run = run = 0
    for n in lens:
        if n <= FRAGMENT_MAX:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    and_count = sum(1 for w in _WORD.findall(text.lower()) if w == "and")
    return {
        "n_sents": len(lens),
        "n_words": n_words,
        "mean_len": round(statistics.mean(lens), 3),
        "stdev_len": round(statistics.pstdev(lens), 3) if len(lens) > 1 else 0.0,
        "max_len": max(lens),
        "frag_rate": round(sum(1 for n in lens if n <= FRAGMENT_MAX) / len(lens), 4),
        "long_rate": round(sum(1 for n in lens if n >= LONG_MIN) / len(lens), 4),
        "max_consec_frag": max_run,
        "and_frac": round(and_count / n_words, 5) if n_words else 0.0,
    }


def chunk_text(text, target_words=85):
    """Cut prose into ~target_words windows aligned to sentence boundaries: keep
    adding whole sentences until the window reaches target_words, then emit it.
    This yields ANSWER-SIZED passages so the reference distribution matches what a
    Bucket-4 answer can actually achieve. The trailing remainder is emitted only
    if it holds at least 2 sentences (a 1-sentence tail isn't a fair 'paragraph')."""
    sents = split_sentences(text)
    chunks, cur, cur_w = [], [], 0
    for s in sents:
        w = word_count(s)
        if w == 0:
            continue
        cur.append(s)
        cur_w += w
        if cur_w >= target_words:
            chunks.append(" ".join(cur))
            cur, cur_w = [], 0
    if len(cur) >= 2:
        chunks.append(" ".join(cur))
    return chunks


def _smoke_test():
    # 1) abbreviations / initials / decimals don't cause false splits
    t = "Dr. Rinaldi came at 3.50. He saw Mr. Henry. F. went home."
    s = split_sentences(t)
    assert s == ["Dr. Rinaldi came at 3.50.", "He saw Mr. Henry.", "F. went home."], s
    print("  [pass] split_sentences: abbreviations/initials/decimals safe")

    # 2) real sentence-final punctuation DOES split, close-quote carried along
    t2 = '"It was good," he said. She left! Did she?'
    s2 = split_sentences(t2)
    assert s2 == ['"It was good," he said.', "She left!", "Did she?"], s2
    print("  [pass] split_sentences: ./!/? split, quotes carried")

    # 3) metrics on a known choppy caricature vs a flowing passage
    choppy = "It was good. He was tired. The wine was cold. She left."
    m = style_metrics(choppy)
    assert m["frag_rate"] == 1.0 and m["max_consec_frag"] == 4, m
    flowing = ("In the late summer of that year we lived in a house in a village "
               "that looked across the river and the plain to the mountains, and "
               "the water was clear and swift and blue in the channels.")
    mf = style_metrics(flowing)
    assert mf["long_rate"] == 1.0 and mf["frag_rate"] == 0.0, mf
    print("  [pass] style_metrics: choppy=all-fragments, flowing=all-long")

    # 4) chunk_text yields answer-sized windows
    para = " ".join(["This is a sentence of several words here." for _ in range(40)])
    ch = chunk_text(para, target_words=85)
    assert all(len(c.split()) >= 60 for c in ch[:-1]), [len(c.split()) for c in ch]
    print(f"  [pass] chunk_text: {len(ch)} windows, ~answer-sized")


if __name__ == "__main__":
    print("stylometry.py self-test (no API, no money):")
    _smoke_test()
    print("ALL SMOKE TESTS PASSED.")
