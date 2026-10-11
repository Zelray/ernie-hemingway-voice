"""
04_mine_passages.py — BUCKET-3 (flatten-restore) candidate miner.

WHY THIS EXISTS (plain English):
  Bucket 3 of the dataset is "flatten-restore": take a chunk of REAL Hemingway
  prose, have Gemini FLATTEN it into voiceless bureaucratic English (the training
  INPUT), and train the model to turn the flat version back into the real chunk
  (the training TARGET). The target is always genuine Hemingway, so it cannot
  teach a caricature, and it directly builds the paid "translate my blog into my
  voice" product.

  This script does the FREE, LOCAL half: it scans the 5 cleaned corpus files and
  extracts clean candidate PROSE passages to flatten. It calls NO API and spends
  NO money — it is pure text scissors (per CLAUDE.md: "code chews the bulk data;
  the model only sees small summaries").

THE MINING RECIPE (from the Data-Engineer review in HANDOFF.md):
  - 40-150 words, on FULL sentence boundaries (never cut mid-sentence).
  - PROSE ONLY. Exclude: dialogue / dialogue-heavy spans (double-quote marks,
    attribution), QUOTELESS speech & embedded prayer/monologue (caught by a
    multi-signal vote so first-person narration survives), ALL-CAPS drop-cap story
    openers ("MANUEL GARCIA ...") even mid-paragraph, verse/poetry, chapter
    headings & front/back matter (ALL-CAPS, roman-numeral / title / byline lines,
    copyright/publisher boilerplate), and proper-noun-DENSE spans.
  - NO overlapping spans (every span is claimed through spine.SpanRegistry).
  - STRATEGY: draw the BULK from the 3 clean carrier novels (Farewell, Sun, Men
    Without Women); the 2 thin works (In Our Time 1924, Three Stories) supply only
    a small filter-passing remainder. Carrier cap ≈ 115/work, thin cap ≈ 40/work.
  - Provenance per span: {id, bucket:'3', work, char_start, char_end, span_text,
    word_count, content_hash} written as JSONL.

ORDERING HOOK (the review's fix): buckets 1 (reflective) and 2 (descriptive) draw
  from a SCARCER supply than bucket 3, so they must RESERVE their passages FIRST.
  mine_corpus() therefore accepts a shared SpanRegistry that may already hold
  bucket-1/2 claims; any bucket-3 span overlapping a prior claim is skipped. This
  branch is now EXERCISED: build_reserved_registry() pre-claims a small set of
  scarce BUCKET-1 reflective aphorisms (the "world breaks every one ..." passage)
  as bucket "1" BEFORE bucket-3 mines, writing them to bucket1_reserved.jsonl so
  they survive for the later bucket-1 build and bucket 3 cannot consume them.

RUN (Bash; PowerShell hangs this box):
  python pipeline/04_mine_passages.py            # full supply estimate
  python pipeline/04_mine_passages.py --dress    # + write ~24 dress candidates
"""
import os
import re
import sys

# Run as a script: sys.path[0] is this file's dir, so `import spine` resolves.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spine  # noqa: E402  (path tweak must precede the import)

# Make stdout UTF-8 so printing curly quotes / accents doesn't crash on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Paths (anchored off THIS file, never the cwd — cwd resets between calls) ───
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
_CLEAN_DIR = os.path.join(_ROOT, "clean")
DRESS_OUT = os.path.join(_HERE, "dress_rehearsal_candidates.jsonl")
SUMMARY_OUT = os.path.join(_HERE, "dress_rehearsal_summary.json")
BUCKET1_RESERVED_OUT = os.path.join(_HERE, "bucket1_reserved.jsonl")

# work slug -> cleaned filename
WORKS = {
    "the-sun-also-rises": "the-sun-also-rises_clean.txt",
    "farewell-to-arms": "farewell-to-arms_clean.txt",
    "in-our-time": "in-our-time_clean.txt",
    "men-without-women": "men-without-women_clean.txt",
    "three-short-stories-and-ten-poems": "three-short-stories-and-ten-poems_clean.txt",
}

# STRATEGY (the review's blend fix): 3 CLEAN, full-length novels are the CARRIERS
# and supply the bulk; the 2 THIN works (the 1924 In Our Time vignettes and the
# 1923 Three Stories) are sparse and dialogue-heavy, so they contribute only a
# small filter-passing remainder. A work not listed here is treated as thin.
CARRIER_WORKS = {"farewell-to-arms", "the-sun-also-rises", "men-without-women"}


def work_cap(work):
    """Per-work span cap. Carriers get the full cap; thin works the smaller one
    so no single sparse book over-contributes to the blend."""
    return PER_WORK_CAP if work in CARRIER_WORKS else PER_WORK_CAP_THIN


def dress_n(work):
    """How many evenly-spaced rehearsal samples to draw from `work` (carrier=bulk,
    thin=small remainder). 3 carriers x 6 + 2 thin x 3 = 24 dress candidates."""
    return DRESS_PER_CARRIER if work in CARRIER_WORKS else DRESS_PER_THIN

# ── Tunable knobs (the ONLY safe one to loosen for supply is PROPERNOUN_MAX) ───
MIN_WORDS = 40           # span floor (spec — do NOT lower)
MAX_WORDS = 150          # span ceiling (spec)
PROPERNOUN_MAX = 0.10    # max ratio of non-sentence-initial Capitalized tokens
ALLCAPS_MAX = 0.60       # paragraph alpha chars uppercase above this -> heading/title
VERSE_LINE_LEN = 45      # mean non-final line length below this -> verse/heading block
PER_WORK_CAP = 115       # carrier cap: ~18% of the ~640 real-voice pool
PER_WORK_CAP_THIN = 40   # thin-work cap: the 2 sparse works are a small remainder
REAL_VOICE_POOL = 640    # buckets 1+2+3 combined target (for context)
BUCKET3_TARGET = 350     # what bucket 3 alone needs to supply
DRESS_PER_CARRIER = 6    # carriers supply the BULK of the rehearsal sample
DRESS_PER_THIN = 3       # thin works supply only a small filter-passing remainder

# Double-quote characters that signal dialogue. NOTE: the right single quote
# U+2019 is INTENTIONALLY absent — Hemingway's corpus uses it as an apostrophe
# (you'll, Robert's), so it must never be read as a dialogue marker.
_DQUOTE = '"“”«»'

# Attribution-tag dialogue with NO quote marks (the In Our Time 1924 vignettes
# render speech this way: "This is the queen, he said."). The recipe excludes
# "attribution like '...' he said", so we catch a speech verb sitting next to a
# subject (pronoun or Capitalized name) in EITHER order. Verb list is restricted
# to unambiguous speech tags (no "cried"/"called"/"told" — those fire on
# non-speech narration). No IGNORECASE: subjects are pronouns or Capitalized
# names; verbs appear lowercase mid-sentence.
_SPEECH = r"(?:said|asked|replied|answered|whispered|murmured|muttered|exclaimed|remarked|shouted)"
_ATTRIBUTION = re.compile(
    r"\b(?:[Hh]e|[Ss]he|[Tt]hey|I|[Ww]e|[Yy]ou|[A-Z][a-z]+)\s+" + _SPEECH + r"\b"
    r"|\b" + _SPEECH + r"\s+(?:he|she|they|[A-Z][a-z]+)\b"
)

# Boilerplate / front-back-matter keywords (lowercased substring match).
_BOILERPLATE = (
    "copyright", "all rights reserved", "scribner", "project gutenberg",
    "printed at", "press", "publishing", "contents", "isbn", "by the author",
    "shakespeare & company", "william jackson", "first published",
    "renewal copyright", "contact publishing", "wood-cut", "illustration",
    "this book", "books by",
)

# Common abbreviations whose trailing period is NOT a sentence boundary.
_ABBREV = {"mr", "mrs", "ms", "dr", "st", "sr", "jr", "vs", "etc", "mt", "no", "co"}

_WORDTOK = re.compile(r"[A-Za-z][A-Za-z'’.]*")
_PARA = re.compile(r"[^\n]+(?:\n[^\n]+)*")          # a paragraph = run of non-blank lines
_HEADING = re.compile(r"^\s*(chapter|book|part|volume|section)\b", re.IGNORECASE)
_ROMAN_OR_NUM = re.compile(r"^\s*[IVXLCDM0-9]+\.?\s*$", re.IGNORECASE)


# ── Text helpers ──────────────────────────────────────────────────────────────
def _flatten_ws(s):
    """Join hard-wrapped lines: collapse every whitespace run to one space, strip.
    Also drop Gutenberg italic markers — it renders italics as _underscores_
    (_Avanti_, _caro_); those are formatting cruft, not Hemingway's words, and
    must not leak into a training target. (Offsets index the source, not this
    cleaned text, so removing the markers is safe.)"""
    return re.sub(r"\s+", " ", s.replace("_", "")).strip()


def _allcaps_ratio(s):
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 1.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def is_prose_paragraph(para):
    """True if `para` looks like body prose (not heading / front-matter / verse)."""
    joined = _flatten_ws(para)
    low = joined.lower()
    if len(joined.split()) < MIN_WORDS:        # too short to ever yield a 40-word span
        return False
    if _allcaps_ratio(joined) > ALLCAPS_MAX:    # BOOKS BY ERNEST HEMINGWAY, titles
        return False
    if any(k in low for k in _BOILERPLATE):     # copyright / publisher / TOC blocks
        return False
    if _HEADING.match(para) or _ROMAN_OR_NUM.match(para):
        return False
    # Verse / heading block: several short lines (poetry wraps far tighter than
    # the ~70-char prose wrap). Judge by the NON-final lines (a prose paragraph's
    # last line is legitimately short, the rest are full-width).
    lines = [ln for ln in para.split("\n") if ln.strip()]
    if len(lines) >= 2:
        body = lines[:-1]
        mean_len = sum(len(ln.strip()) for ln in body) / len(body)
        if mean_len < VERSE_LINE_LEN:
            return False
    return True


def split_sentences(para):
    """Return [(start, end)] half-open offsets of full sentences within `para`.

    A boundary is [.!?]+ plus any trailing close-quotes/brackets, that is then
    followed by whitespace + a capital/quote/digit OR the paragraph end. Guards
    against single-letter initials ("A. J.") and common abbreviations ("Mr.")."""
    n = len(para)
    sents = []
    start = 0
    for m in re.finditer(r"[.!?]+", para):
        e = m.end()
        while e < n and para[e] in "”’\")]":   # swallow closing quotes
            e += 1
        rest = para[e:]
        followed_ok = (
            rest == ""
            or re.match(r"\s*$", rest)
            or re.match(r"\s+[\"“('‘]?[A-Z0-9]", rest)
        )
        if not followed_ok:
            continue
        # Inspect the token immediately before the period for abbrev / initial.
        j = m.start()
        k = j
        while k > 0 and (para[k - 1].isalnum() or para[k - 1] in ".'’"):
            k -= 1
        prev = para[k:j]
        bare = prev.rstrip(".").lower()
        if len(prev.rstrip(".")) == 1 and prev[:1].isupper():
            continue                                   # single initial, e.g. "A."
        if bare in _ABBREV:
            continue
        seg = para[start:e]
        if seg.strip():
            sents.append((start, e))
        start = e
    if start < n and para[start:].strip():
        sents.append((start, n))
    return sents


def propernoun_ratio(span_text):
    """Ratio of Capitalized tokens that are NOT sentence-initial (and not 'I').

    Proper nouns mid-sentence (names, places) are the signal; the first word of
    each sentence is capitalized for grammar, not because it's a name, so it is
    excluded. High ratio -> the passage is about specific characters/places and
    makes a poor generic flatten-restore target."""
    sents = split_sentences(span_text) or [(0, len(span_text))]
    initial_starts = set()
    for (s, _e) in sents:
        wm = _WORDTOK.search(span_text, s)
        if wm:
            initial_starts.add(wm.start())
    toks = list(_WORDTOK.finditer(span_text))
    if not toks:
        return 1.0
    caps = 0
    for t in toks:
        w = t.group()
        if t.start() in initial_starts:
            continue
        if w == "I" or w.startswith("I'") or w.startswith("I’"):
            continue
        if w[0].isupper():
            caps += 1
    return caps / len(toks)


def _group_spans(para, pstart):
    """Greedy non-overlapping 40-150 word spans on sentence boundaries.

    Yields (char_start, char_end, span_text, word_count) in ORIGINAL-file offsets
    (pstart = the paragraph's start offset in the cleaned source). Spans never
    overlap: each ends where the next begins."""
    sents = split_sentences(para)
    cur = []          # list of (s, e) sentence offsets in this run
    cur_words = 0
    out = []

    def flush():
        if cur and cur_words >= MIN_WORDS:
            cs, ce = cur[0][0], cur[-1][1]
            txt = _flatten_ws(para[cs:ce])
            out.append((pstart + cs, pstart + ce, txt, len(txt.split())))

    for (s, e) in sents:
        w = len(_flatten_ws(para[s:e]).split())
        if w > MAX_WORDS:                 # a single mega-sentence can't fit -> skip it
            flush()
            cur, cur_words = [], 0
            continue
        if cur_words + w <= MAX_WORDS:
            cur.append((s, e))
            cur_words += w
        else:
            flush()
            cur, cur_words = [(s, e)], w
    flush()
    return out


# ── Edge-case leak detectors (the 3 defects a skeptic found) ──────────────────
# DEFECT 2 (Men Without Women) — an ALL-CAPS drop-cap story opener ("MANUEL
# GARCIA ...") slips past is_prose_paragraph because two caps words barely move a
# whole paragraph's all-caps RATIO. We catch it at the SPAN start instead.
def _has_dropcap_opener(span_text):
    """True if the span OPENS with an all-caps drop-cap / shouted run: >=6
    consecutive uppercase letters in the first word (MANUEL), or >=2 consecutive
    ALL-CAPS words (DON MIGUEL). Leading quotes/brackets are skipped first. A lone
    'I' or single capitalized word (normal sentence start) never trips this, so
    first-person narration is safe; we SKIP rather than trim because trimming a
    drop-cap mid-sentence leaves a lowercase fragment and supply is ample."""
    head = re.sub(r"^[\s\"“”‘’'(\[]+", "", span_text)
    if re.match(r"[A-Z]{6,}", head):
        return True
    if re.match(r"[A-Z]{2,}(?:[’'.\-][A-Z]+)?\s+[A-Z]{2,}\b", head):
        return True
    return False


# DEFECT 2b (Men Without Women) — a SHORT all-caps drop-cap FIRST word ("THE train",
# "IN the fall", "THAT night", "THE road") is a decorative-typography artifact, not a
# heading or a shout: only the FIRST word is uppercased and the SECOND word is ordinary
# lowercase prose. _has_dropcap_opener MISSES it (it needs 6+ caps OR two caps words),
# so it leaked into output looking ugly. The prose itself is excellent carrier work, so
# we NORMALIZE the first word to title case and KEEP the span rather than reject it.
_DROPCAP_WORD = re.compile(r"^[\s\"“”‘’'(\[]*([A-Z][A-Z’'\-]*)\s+[a-z]")


def _normalize_dropcap_word(span_text):
    """Title-case an all-caps drop-cap FIRST word (>=2 letters) when the SECOND word
    is ordinary lowercase ("THE train" -> "The train", "IN the" -> "In the"); return
    the span otherwise unchanged. Guards: a single-letter 'I'/'A' is never touched (the
    >=2-letter test), and a fully-caps first line (a heading) cannot match because its
    second word would be uppercase, not lowercase — headings fall through to the
    all-caps / heading filters untouched. Two-all-caps-word openers ('MANUEL GARCIA')
    also can't match here, so _has_dropcap_opener still rejects them."""
    m = _DROPCAP_WORD.match(span_text)
    if not m:
        return span_text
    word = m.group(1)
    if sum(c.isalpha() for c in word) < 2:          # lone 'I'/'A' — leave alone
        return span_text
    return span_text[:m.start(1)] + word.capitalize() + span_text[m.end(1):]


# DEFECTS 1 & 3 (Three Stories / In Our Time) — quoteless speech & embedded
# prayer/monologue carry NO quote marks and NO subject+speech-verb attribution,
# so _DQUOTE and _ATTRIBUTION both miss them. They betray themselves other ways.
# Each cue ALSO appears in good first-person NARRATION, so we require TWO to agree
# before excluding — that keeps 'My Old Man' and the Farewell opening safe.
_SECOND_PERSON = {"you", "your", "yours", "yourself", "yourselves"}

# Quoteless speech/prayer verbs. Deliberately NARROW: 'called'/'cried' fire on
# narration ('called to the bull', 'cried and cried') so they are EXCLUDED here.
_SPEECH_CUE = {"prayed", "pray", "praying", "prays", "asked", "told",
               "answered", "replied", "begged", "beg", "pleaded"}

# Sentence-initial words that mark an imperative COMMAND (narration does not
# command a listener). 'please' opens prayers/pleas.
_IMPERATIVE_OPENERS = {"give", "get", "take", "come", "go", "let", "bring",
                       "keep", "leave", "put", "send", "wait", "stop",
                       "listen", "hold", "please"}

# Common irregular pasts the "-ed" test below would miss. Listing extras here only
# makes the no-past-tense signal HARDER to trip, which protects narration.
_IRREGULAR_PAST = {
    "was", "were", "had", "did", "went", "said", "saw", "came", "got", "took",
    "made", "knew", "found", "gave", "told", "thought", "felt", "held", "kept",
    "left", "lay", "sat", "stood", "ran", "began", "brought", "bought", "caught",
    "wrote", "drew", "fell", "hung", "heard", "met", "paid", "read", "ate",
    "drank", "spoke", "broke", "rode", "rose", "shot", "struck", "swam", "wore",
    "won", "lost", "led", "fled", "hit", "set", "put", "let", "cut", "shut",
}

# Short stopwords excluded from the back-to-back repetition (anaphora) test.
_ANAPHORA_STOP = {"the", "and", "was", "that", "they", "for", "but", "with", "his", "her"}


def _alpha_tokens(text):
    """Lowercased alphabetic tokens; splits contractions ('you'll' -> you, ll) so
    pronoun membership tests see the bare pronoun."""
    return re.findall(r"[a-z]+", text.lower())


def _imperative_opener(span_text):
    """True if ANY sentence in the span begins with an imperative-command verb."""
    for (s, _e) in (split_sentences(span_text) or [(0, len(span_text))]):
        wm = _WORDTOK.search(span_text, s)
        if wm and wm.group().lower().strip(".'’") in _IMPERATIVE_OPENERS:
            return True
    return False


def _max_adjacent_run(toks):
    """Longest run of one content word repeated BACK-TO-BACK ('please please
    please' -> 3). Spaced repetition ('my old man' ... 'my old man') is NOT a run,
    so Hemingway's deliberate echoes survive; only mechanical anaphora trips it."""
    best = cur = 0
    prev = None
    for t in toks:
        if t == prev and len(t) >= 3 and t not in _ANAPHORA_STOP:
            cur += 1
        else:
            cur, prev = 1, t
        best = max(best, cur)
    return best


def _has_past_tense(toks):
    """True if the span carries any narrative past tense (an irregular past, or a
    >=4-char '-ed' word). Hemingway narration runs on the past; pure
    monologue/prayer runs on present/future/imperative."""
    for t in toks:
        if t in _IRREGULAR_PAST or (len(t) >= 4 and t.endswith("ed")):
            return True
    return False


def _monologue_signals(span_text):
    """Count the quoteless-monologue signals present (>=2 -> exclude). Returns
    (count, [names]); each name is harmless alone but a chorus means dialogue."""
    toks = _alpha_tokens(span_text)
    names = []
    if sum(t in _SECOND_PERSON for t in toks) >= 3:   # direct 2nd-person address
        names.append("2nd-person-address")
    if set(toks) & _SPEECH_CUE:                        # quoteless speech/prayer cue
        names.append("speech-cue")
    if _imperative_opener(span_text):                  # a sentence commands a listener
        names.append("imperative")
    if _max_adjacent_run(toks) >= 3:                   # 'please please please'
        names.append("anaphora")
    if not _has_past_tense(toks):                      # no narrative past tense at all
        names.append("no-past-tense")
    return len(names), names


# ── Structural leak filters (a FULL-POOL scan's bounded, NON-prose remainder) ──
# LEAK A — PLAY/SCRIPT speaker cue (from "Today is Friday"). A dramatic line opens
# "2d Soldier—...", "2d Roman Soldier—...", "GEORGE.—...": an optional ordinal,
# then 1-3 Capitalized name/role words, then a PERIOD-DASH or EM/EN-DASH (never a
# plain hyphen) butted against the speech. The em/en-dash is the discriminator —
# it is what keeps hyphenated NARRATION ("Up-stairs in the office ...",
# "Down-stairs we came out ...") OUT, because those carry a hyphen, not a dash.
_SPEAKER_TAG = re.compile(
    r"^(?:\d{1,2}(?:st|nd|rd|d|th)\.?\s+)?"               # optional ordinal: "2d ", "1st "
    r"[A-Z][A-Za-z'’\-]*(?:\s+[A-Z][A-Za-z'’\-]*){0,2}"   # 1-3 Cap name/role words
    r"\.?[—–]"                                             # period-dash or em/en-dash
)


def _is_speaker_tag(span_text):
    """True if the span OPENS with a dramatic play/script speaker cue."""
    return bool(_SPEAKER_TAG.match(span_text))


# LEAK B — EPISTOLARY content (an embedded letter; e.g. Michael's note in The Sun
# Also Rises). Keyed on LETTER REGISTER, NOT on bare 2nd-person "you" — keying on
# "you" would sweep legitimate first-person narration (advisor's explicit
# warning). Two cues: (1) a SALUTATION at the very START ("Dear Jake", "My dear
# ..."), and (2) a register-specific SIGN-OFF phrase anywhere ("Love to all",
# "all our love", "Yours truly", "send a note", ...). Those phrases do not occur
# in Hemingway's narration, so precision stays high. Bare "love," and "We got
# here" are DELIBERATELY omitted: they false-positive on narration ("made love,",
# "We got here at noon ..."), and the sign-offs already catch the real letter.
_LETTER_SALUTATION = re.compile(r"^(?:My\s+)?[Dd]ear\s+[A-Z]")
_LETTER_SIGNOFF = (
    "love to all", "all our love", "yours truly", "yours sincerely",
    "yours ever", "yours faithfully", "yours,", "send a note",
    "drop me a line", "send word",
)


def _is_letter(span_text):
    """True if the span reads as correspondence (salutation or sign-off register)."""
    if _LETTER_SALUTATION.match(span_text):
        return True
    low = span_text.lower()
    return any(s in low for s in _LETTER_SIGNOFF)


# BASELINE SPAN-VALIDITY (a GENERAL rule, not a one-off) — a well-formed prose
# span must START with a capital letter and END in terminal punctuation (. ! ?),
# optionally followed by a closing quote/bracket. This kills the mid-sign-off
# comma cut ("... Love to all the chaps,") and any other malformed boundary (e.g.
# a speaker tag opening on a digit, "2d Soldier—..."). The gap was silently
# present from the start; enforcing it here is the baseline every span must clear.
_SPAN_END_OK = re.compile(r"[.!?][\"”’')\]]*$")


def _baseline_valid(span_text):
    """True if the span starts with a CAPITAL LETTER and ends in terminal punct."""
    t = span_text.strip()
    if not t or not t[0].isalpha() or not t[0].isupper():
        return False
    return bool(_SPAN_END_OK.search(t))


# DEFECT 4 (THIN vignette works ONLY: In Our Time 1924, Three Stories) — these two
# books PRINT spoken dialogue with NO quote marks AND NO subject+speech-verb
# attribution: vendor patter, Italian greetings/cries, 2nd-person hails. So _DQUOTE,
# _ATTRIBUTION, and the 2-of-N _monologue_signals vote ALL miss it (e.g. "Marsala,
# you like marsala, Signorina? A little marsala?"; "Senta caro!"; "Buon' di Arturo!";
# "Come on Luis."; "Toro! Toro!"). It is unmarked SPOKEN dialogue, NOT the 3rd-person
# free-indirect thought we want to keep — so we reject it, but ONLY in these two
# works and ONLY on hard spoken-cue patterns, never on a bare shared word. The
# carriers never see this filter (work defaults to None below). Kept deliberately
# tight so free-indirect voice survives: "you ought/you know …" do NOT trip pattern
# 1 (it needs "you like …?"), so 'My Old Man' first-person narration is safe.
THIN_DIALOGUE_WORKS = {"in-our-time", "three-short-stories-and-ten-poems"}

_THIN_SPOKEN_PATTERNS = (
    # 2nd-person vendor/sales question: "...you like marsala, Signorina?"
    re.compile(r"\byou like\b[^.?!]*\?"),
    # Italian greeting/attention cry printed unquoted, at a sentence start:
    # "Senta caro!", "Buon' di Arturo!" (note the CURLY apostrophe U+2019), "Avanti".
    # NB: "Buon" is delimited by its own apostrophe/space (Buonarroti won't match),
    # so it carries NO trailing \b — a \b between U+2019 and a space never matches.
    re.compile(r"(?:^|[.!?]\s+)(?:(?:Senta|Avanti|Andiamo|Ciao)\b|Buon['’ ])"),
    # English imperative hail to a NAMED person: "Come on Luis.", "Come on, Manuel!"
    re.compile(r"(?:^|[.!?]\s+)Come on,?\s+[A-Z][a-z]+\b"),
    # Repeated exclamatory cry: "Toro! Toro!", "Ole! Ole!" (same word twice, shouted).
    re.compile(r"\b([A-Z][a-z]+)!\s+\1!"),
    # Exclamatory oath spoken aloud: "For Christ sake ...".
    re.compile(r"\bFor Christ sake\b"),
)


def _is_thin_spoken_dialogue(span_text):
    """True if a THIN-work span carries UNMARKED spoken dialogue (vendor patter,
    Italian greeting/cry, 2nd-person hail to a name, repeated exclamatory cry,
    spoken oath). Applied ONLY for THIN_DIALOGUE_WORKS; never the carrier novels."""
    return any(p.search(span_text) for p in _THIN_SPOKEN_PATTERNS)


def span_is_clean(span_text, work=None):
    """Span-level prose gate: well-formed boundaries (baseline validity), no
    dialogue (quoted OR attribution-tagged), no play/script speaker cue, no
    embedded letter, no ALL-CAPS drop-cap opener, not quoteless monologue, not
    proper-noun-dense. When `work` is a THIN vignette book, also rejects unmarked
    SPOKEN dialogue (DEFECT 4); carriers pass work=None and skip that check."""
    if not _baseline_valid(span_text):                 # BASELINE span validity
        return False
    if any(c in span_text for c in _DQUOTE):
        return False
    if _ATTRIBUTION.search(span_text):
        return False
    if _is_speaker_tag(span_text):                      # LEAK A: play/script cue
        return False
    if _is_letter(span_text):                           # LEAK B: epistolary content
        return False
    if _has_dropcap_opener(span_text):                 # DEFECT 2
        return False
    if _monologue_signals(span_text)[0] >= 2:          # DEFECTS 1 & 3 (>=2 signals agree)
        return False
    if work in THIN_DIALOGUE_WORKS and _is_thin_spoken_dialogue(span_text):
        return False                                    # DEFECT 4: unmarked spoken dialogue
    if propernoun_ratio(span_text) > PROPERNOUN_MAX:
        return False
    return True


# ── Per-work mining ───────────────────────────────────────────────────────────
def mine_work(work, registry, bucket="3", cap=None):
    """Return a list of kept span records for one work, claiming each non-
    overlapping char range through the shared registry (so an earlier bucket's
    reservations are respected). `cap` limits how many spans this work may
    contribute; None = uncapped (used for the raw supply estimate)."""
    path = os.path.join(_CLEAN_DIR, WORKS[work])
    text = open(path, encoding="utf-8").read()
    kept = []
    collisions = 0
    for pm in _PARA.finditer(text):
        para = pm.group()
        if not is_prose_paragraph(para):
            continue
        for (cs, ce, txt, wc) in _group_spans(para, pm.start()):
            txt = _normalize_dropcap_word(txt)          # DEFECT 2b: clean drop-cap word
            if not span_is_clean(txt, work):
                continue
            # Honor bucket-1/2 reservations: claim() fails if the range is taken.
            if not registry.claim(work, cs, ce, bucket):
                collisions += 1
                continue
            kept.append({
                "id": f"b{bucket}_{work}_{cs:08d}",
                "bucket": bucket,
                "work": work,
                "char_start": cs,
                "char_end": ce,
                "span_text": txt,
                "word_count": wc,
                "content_hash": spine.content_hash(txt),
            })
            if cap is not None and len(kept) >= cap:
                return kept, collisions
    return kept, collisions


def mine_corpus(cap=None, registry=None):
    """Mine all works. Returns (per_work: {work: [records]}, total_collisions).

    Pass a pre-populated SpanRegistry to let buckets 1/2 reserve scarce passages
    BEFORE bucket 3 runs (the review's ordering fix). Default = fresh registry."""
    registry = registry or spine.SpanRegistry()
    per_work = {}
    total_collisions = 0
    for work in WORKS:
        recs, coll = mine_work(work, registry, bucket="3", cap=cap)
        per_work[work] = recs
        total_collisions += coll
    return per_work, total_collisions


# ── Bucket-1 reservation (scarce reflective aphorisms, claimed BEFORE bucket 3) ─
# WHY: bucket 1 (reflective) draws from a far SCARCER supply than bucket 3, and
# bucket-3's quoteless-monologue filters keep sweeping the very passages bucket 1
# wants (present-tense, 2nd-person reflective aphorisms read as "monologue"). So
# we RESERVE those passages here — claim their char ranges as bucket "1" in the
# shared registry BEFORE bucket 3 mines, and persist them to bucket1_reserved.jsonl
# so they survive for the later bucket-1 build. This is a RESERVATION, not a
# bucket-3 inclusion. Each entry is (work, start_anchor, end_anchor): unique
# single-line substrings whose offsets bound the reflective unit in the cleaned
# source. (Anchors must NOT cross a hard-wrap newline, or .index() will miss.)
BUCKET1_RESERVED = [
    # A Farewell to Arms — the famous "world breaks every one" meditation.
    ("farewell-to-arms",
     "If people bring so much courage",
     "special hurry."),
]


def build_reserved_registry():
    """Resolve each BUCKET1_RESERVED passage to char offsets, claim it as bucket
    "1" in a fresh SpanRegistry, and (idempotently) rewrite bucket1_reserved.jsonl.
    Returns (registry, records) — pass the registry to mine_corpus() so bucket 3
    cannot consume any reserved range."""
    registry = spine.SpanRegistry()
    records = []
    for (work, start_anchor, end_anchor) in BUCKET1_RESERVED:
        text = open(os.path.join(_CLEAN_DIR, WORKS[work]), encoding="utf-8").read()
        cs = text.find(start_anchor)
        if cs < 0:
            raise ValueError(f"reserved start anchor not found in {work}: {start_anchor!r}")
        ee = text.find(end_anchor, cs)
        if ee < 0:
            raise ValueError(f"reserved end anchor not found in {work}: {end_anchor!r}")
        ce = ee + len(end_anchor)
        span_text = _flatten_ws(text[cs:ce])
        registry.claim(work, cs, ce, bucket="1")       # block this range for bucket 3
        records.append({
            "id": f"b1_{work}_{cs:08d}",
            "bucket": "1",
            "work": work,
            "char_start": cs,
            "char_end": ce,
            "span_text": span_text,
            "word_count": len(span_text.split()),
            "content_hash": spine.content_hash(span_text),
        })
    if os.path.exists(BUCKET1_RESERVED_OUT):            # fresh, idempotent rewrite
        os.remove(BUCKET1_RESERVED_OUT)
    for rec in records:
        spine.append_record(BUCKET1_RESERVED_OUT, rec)
    return registry, records


# ── Dress-rehearsal sampling (deterministic, no cherry-picking) ───────────────
def evenly_spaced(items, k):
    """Pick up to k items at evenly spaced indices across the list (deterministic).
    Spreads samples beginning->end so we eyeball variety, never the 'best' ones."""
    n = len(items)
    if n == 0:
        return []
    if n <= k:
        return list(items)
    idx = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    return [items[i] for i in idx]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import json
    dress = "--dress" in sys.argv

    # RESERVE scarce bucket-1 aphorisms FIRST, then mine bucket 3 on the registry
    # that already holds those claims (so bucket 3 cannot consume a reserved range).
    reserved_reg, reserved = build_reserved_registry()

    # Full uncapped pass = the honest supply estimate (how many clean spans EXIST).
    per_work, collisions = mine_corpus(cap=None, registry=reserved_reg)

    supply = {w: len(recs) for w, recs in per_work.items()}
    total = sum(supply.values())
    capped_total = sum(min(supply[w], work_cap(w)) for w in WORKS)
    can_reach = capped_total >= BUCKET3_TARGET

    print("=" * 64)
    print("BUCKET-3 SUPPLY ESTIMATE (clean non-overlapping prose spans)")
    print("=" * 64)
    for w in WORKS:
        c = supply[w]
        role = "carrier" if w in CARRIER_WORKS else "thin   "
        flag = "  <-- over cap, will be trimmed" if c > work_cap(w) else ""
        print(f"  {w:38s} {c:5d}   ({role} cap {work_cap(w):3d}){flag}")
    print("-" * 64)
    print(f"  {'TOTAL (raw)':38s} {total:5d}")
    print(f"  {'TOTAL (after per-work caps)':38s} {capped_total:5d}")
    print(f"  bucket-3 target = {BUCKET3_TARGET}   -> reachable: {can_reach}")
    print(f"  overlaps_found (registry collisions) = {collisions}")
    print(f"  bucket-1 reserved (claimed before bucket 3) = {len(reserved)} "
          f"-> {os.path.basename(BUCKET1_RESERVED_OUT)}")
    print("=" * 64)

    summary = {
        "per_work_supply": supply,
        "total_est_clean_spans": total,
        "capped_total": capped_total,
        "per_work_cap_carrier": PER_WORK_CAP,
        "per_work_cap_thin": PER_WORK_CAP_THIN,
        "carrier_works": sorted(CARRIER_WORKS),
        "bucket3_target": BUCKET3_TARGET,
        "can_reach_350": can_reach,
        "overlaps_found": collisions > 0,
        "propernoun_max": PROPERNOUN_MAX,
        "bucket1_reserved_count": len(reserved),
    }

    if dress:
        sample = []
        for w in WORKS:
            sample.extend(evenly_spaced(per_work[w], dress_n(w)))
        # Fresh file each run (idempotent rehearsal output).
        if os.path.exists(DRESS_OUT):
            os.remove(DRESS_OUT)
        for rec in sample:
            spine.append_record(DRESS_OUT, rec)
        summary["dress_count"] = len(sample)
        print(f"\nWrote {len(sample)} dress candidates -> {DRESS_OUT}")

    with open(SUMMARY_OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Summary -> {SUMMARY_OUT}")


if __name__ == "__main__":
    main()
