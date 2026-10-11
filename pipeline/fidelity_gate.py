"""
fidelity_gate.py — the reusable, DE-NOISED fidelity gate for flatten->restore pairs.

WHY THIS EXISTS (plain English):
  Bucket 3 builds training pairs as  flat -> real :
    - REAL Hemingway span = the training TARGET (genuine voice).
    - Gemini FLATTENS it   = the training INPUT  (voiceless, bureaucratic prose).
  We need an automated gate that catches the failure modes that actually matter
  (the flatten silently dropped a NAME or a NUMBER, flipped grammatical PERSON,
  under-flattened so the input still echoes the target, or CORRUPTED a rare word)
  WITHOUT crying wolf on harmless rewrites.

  The first version of this gate (inlined in 05_dress_rehearsal_flatten.py) had a
  ~45% FALSE-POSITIVE rate — 10 of 22 pairs flagged, and ALL 10 were artifacts:
    - curly apostrophes tokenized as fake new entities ("Rinaldi’s", "I’d");
    - impersonal "one" ("one could see across a river") miscounted as a numeral;
    - faithful number reformatting ("a quarter to five" -> "4:45");
    - morphology / spelling variants ("Italians"->"Italian", "Turgenieff"->"Turgenev").
  Meanwhile it MISSED the one real defect: a rare-word corruption,
  "the folds of the muleta" -> "theleta's folds".

  This module fixes both directions. It is intentionally LEAN (stdlib + spine only;
  no spaCy/nltk data is installed on this box and we make $0 external calls).

  ★ Insight — separate the SIGNAL from the ARTIFACT:
    A faithful flatten changes the VOICE, never the FACTS. The facts that matter
    are: who is speaking (person), the named people/places (entities), the counts
    (cardinal numbers), and that no word got mangled into gibberish (garble).
    Everything else — how a number is FORMATTED, whether a plural became singular,
    whether "you" became "one" — is style, not fact, and must NOT hard-fail a pair.

WHAT IS A HARD FLAG (fails the pair):
  (1) UNDER-FLATTEN LEAK   — input still echoes the target wording (5-gram Jaccard
                             or raw edit-similarity too high). spine.five_gram_jaccard.
  (2) NAMED-ENTITY LOSS    — a proper name in the target is absent from the flatten
                             (lenient: morphology / spelling / possessive variants
                             do NOT count as loss).
  (3) CARDINAL NUMBER LOSS — a counted quantity (two, five, 12, a dozen ...) vanished
                             AND was not merely re-formatted into digits.
  (4) PERSON FLIP          — first person present in the target but gone from the
                             flatten ("we lived" -> impersonal). The named failure.
  (5) GARBLE               — a flatten token that is not a real reproduction of any
                             source word yet is a near-miss corruption of a rare one
                             ("muleta" -> "theleta") — a likely generation corruption.

WHAT IS A SOFT DIAGNOSTIC (surfaced, never fails the pair):
  impersonal "one", ordinals (first/last/second...), fraction/multiplier words
  (half/quarter/single...), number FORMAT conversions, added entities (possible but
  usually-benign expansions like "the States"->"the United States"), 2nd/3rd-person
  shifts. A human can scan these, but they never block a pair.

STDLIB ONLY: re, difflib, collections (+ spine.py helpers). No pip installs, no API.

RUN (Bash; PowerShell hangs this box) — re-grades the 22 dress-rehearsal pairs:
  python pipeline/fidelity_gate.py
"""
import os
import re
import sys
import json
import difflib
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from spine import five_gram_jaccard, _tokens  # noqa: E402


# ── Quote / apostrophe normalization (run BEFORE any tokenizing) ──────────────
# Curly punctuation is the #1 false-positive source: "Rinaldi’s" (U+2019) and
# "Rinaldi's" (U+0027) must be treated as the same string, or the gate invents a
# "lost" entity and an "added" entity for every possessive.
_QUOTE_MAP = {
    "‘": "'", "’": "'", "ʼ": "'", "`": "'", "´": "'",
    "“": '"', "”": '"',
}
_QUOTE_RE = re.compile("|".join(re.escape(c) for c in _QUOTE_MAP))


def normalize_quotes(text):
    """Map every curly apostrophe/quote to its straight ASCII form so that
    tokenizing and matching see one canonical surface for possessives and quotes."""
    return _QUOTE_RE.sub(lambda m: _QUOTE_MAP[m.group(0)], text)


# ── Person pronouns (the one person-flip we hard-flag is first-person loss) ────
FIRST_PERSON = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves"}
SECOND_PERSON = {"you", "your", "yours", "yourself", "yourselves"}
THIRD_PERSON = {"he", "him", "his", "himself", "she", "her", "hers", "herself",
                "they", "them", "their", "theirs", "themselves"}  # it/its excluded


# ── Number vocabulary, split by what we DEMOTE vs what we KEEP ─────────────────
# HARD on loss: true cardinals (counts) and bare digit runs.
CARDINAL_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
    "million": 1_000_000, "billion": 1_000_000_000, "dozen": 12,
}
# SOFT only: ordinals (position, freely re-expressed: "the last bull" -> "the fifth bull").
ORDINAL_WORDS = {
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
    "ninth", "tenth", "eleventh", "twelfth", "last",
}
# SOFT only: fractions / multipliers / "one" — quantifier-ish, prone to harmless
# rephrasing ("became one" -> "a single entity"; "a quarter to five" -> "4:45").
SOFT_NUM_WORDS = {"one", "half", "quarter", "single", "double", "triple",
                  "once", "twice", "thrice"}


# ── Named-entity proxy ────────────────────────────────────────────────────────
# Capitalized tokens that are NOT sentence-initial, NOT function words, NOT "I".
CAP_STOPLIST = {
    "the", "a", "an", "it", "its", "he", "she", "they", "we", "you", "i", "in", "on",
    "at", "up", "down", "there", "then", "when", "while", "but", "and", "so", "if",
    "as", "his", "her", "him", "them", "their", "this", "that", "these", "those",
    "all", "no", "not", "after", "afterward", "before", "some", "sometimes", "only",
    "perhaps", "dear", "oh", "please", "or", "of", "for", "to", "with", "from", "by",
    "was", "were", "is", "are", "be", "been", "had", "have", "did", "do", "one", "two",
    "three", "living", "knotting", "down-stairs", "troops",
}
_CAP = re.compile(r"[A-Z][A-Za-z'.-]*")
_CONTRACTIONS = ("'s", "'d", "'ll", "'re", "'ve", "'m", "n't")


def _strip_affix(tok):
    """Drop a possessive / contraction tail and edge punctuation from a lowered
    token: 'rinaldi's' -> 'rinaldi', "i'd" -> 'i', 'gillford's' -> 'gillford'.
    This is what stops a possessive from masquerading as a new named entity."""
    for suf in _CONTRACTIONS:
        if tok.endswith(suf) and len(tok) > len(suf):
            tok = tok[: -len(suf)]
            break
    return tok.strip("'.-")


def _named_entities(text):
    """Set of lowercased entity stems: capitalized, mid-sentence, non-function
    tokens with possessives/contractions stripped. Under-detects on purpose; LOSS
    is what we test, and we test it leniently below."""
    text = normalize_quotes(text)
    ents = set()
    for m in _CAP.finditer(text):
        j = m.start() - 1
        while j >= 0 and text[j] in " \t\n\r\"'()—-":
            j -= 1
        if j < 0 or text[j] in ".!?":   # sentence-initial -> not a reliable entity
            continue
        tok = _strip_affix(m.group(0).lower())
        if not tok or tok == "i" or tok in CAP_STOPLIST:
            continue
        ents.add(tok)
    return ents


# ── Fuzzy helpers (shared by entity-leniency and garble detection) ────────────
def _ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def _shared_prefix_len(a, b):
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def _variant_match(a, b):
    """True if b is plausibly the SAME name as a, allowing morphology / spelling:
    'italians'~'italian' (ratio .93), 'turgenieff'~'turgenev' (shared 5-char stem).
    Used only to SUPPRESS a false 'entity lost' flag — it never creates one."""
    if a == b:
        return True
    if _ratio(a, b) >= 0.82:
        return True
    if min(len(a), len(b)) >= 5 and _shared_prefix_len(a, b) >= 5:
        return True
    return False


# ── Garble detector (catches corruption of rare/foreign/archaic source words) ─
# A garble is the failure mode "the muleta" -> "theleta's": the flatten emitted a
# token that is NOT a real English word and was NOT copied from the source span.
# The clean signal for "not a real word" is a real DICTIONARY. We use the 427k-word
# list shipped (offline, $0) with the `unstructured` package; if it is not present
# the check degrades to OFF (returns []) rather than guessing, because a
# dictionary-free fuzzy heuristic mistakes ordinary modern words ("considered",
# "however") for garble. (For the full M2 run, wire spaCy md/lg token.is_oov or
# nltk words; both are cleaner than a bare wordlist file.)
GARBLE_MIN_LEN = 4
_FLAT_TOKEN_RE = re.compile(r"[A-Za-z']+")
_DICT_ENV = "FIDELITY_WORDLIST"
_DICT_CANDIDATES = [
    r"C:/Users/mcgeo/miniconda3/Lib/site-packages/unstructured/nlp/english-words.txt",
]
_DICT_CACHE = None  # frozenset once loaded; False if no wordlist found


def _load_dictionary():
    """Load the English wordlist once (lowercased set). Searches: $FIDELITY_WORDLIST,
    a known path, then any sys.path site-packages copy of unstructured's list.
    Returns a frozenset, or False if none is available (garble check then no-ops)."""
    global _DICT_CACHE
    if _DICT_CACHE is not None:
        return _DICT_CACHE
    paths = []
    if os.environ.get(_DICT_ENV):
        paths.append(os.environ[_DICT_ENV])
    paths.extend(_DICT_CANDIDATES)
    for base in sys.path:
        if base and os.path.isdir(base):
            paths.append(os.path.join(base, "unstructured", "nlp", "english-words.txt"))
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                _DICT_CACHE = frozenset(w.strip().lower() for w in f if w.strip())
            return _DICT_CACHE
        except OSError:
            continue
    _DICT_CACHE = False
    return _DICT_CACHE


def _garble_tokens(flat, source):
    """Return [(token, nearest_source_word, ratio), ...] for flatten tokens that
    are non-dictionary AND not present in the source span. `ratio` is the best
    fuzzy similarity to any source token, reported only so a human can see how far
    the token is from anything real ('theleta'~'muleta' 0.62 = a clear mangle)."""
    words = _load_dictionary()
    if words is False:           # no dictionary -> do not guess
        return []
    src_all = set(_tokens(normalize_quotes(source)))
    pool = [s for s in src_all if len(s) >= 4]
    out, seen = [], set()
    for m in _FLAT_TOKEN_RE.finditer(normalize_quotes(flat)):
        tok = _strip_affix(m.group(0).lower())
        if len(tok) < GARBLE_MIN_LEN or not tok.isalpha():
            continue
        if tok in words or tok in src_all or tok in seen:
            continue                # a real word, or copied from source -> fine
        seen.add(tok)
        best_ratio, best_src = 0.0, None
        for s in pool:
            r = _ratio(tok, s)
            if r > best_ratio:
                best_ratio, best_src = r, s
        if best_ratio >= 0.90:      # essentially a source word (tiny spelling diff)
            continue                # protect a faithful rare-word reproduction
        out.append((tok, best_src, round(best_ratio, 3)))
    return out


# ── Number extraction ─────────────────────────────────────────────────────────
def _cardinal_values(text):
    """Multiset (Counter) of cardinal VALUES: digit runs by int value, plus true
    cardinal words by value. Ordinals/fractions/'one' are excluded (they are soft)."""
    vals = []
    for t in _tokens(normalize_quotes(text)):
        if t.isdigit():
            vals.append(int(t))
        elif t in CARDINAL_WORDS:
            vals.append(CARDINAL_WORDS[t])
    return Counter(vals)


def _digit_tokens(text):
    return {t for t in _tokens(normalize_quotes(text)) if t.isdigit()}


def _soft_num_words(text):
    toks = _tokens(normalize_quotes(text))
    return {t for t in toks if t in ORDINAL_WORDS or t in SOFT_NUM_WORDS}


def _person_flags(text):
    toks = set(_tokens(normalize_quotes(text)))
    return (bool(toks & FIRST_PERSON), bool(toks & SECOND_PERSON), bool(toks & THIRD_PERSON))


def _dominant_person(text):
    toks = _tokens(normalize_quotes(text))
    c1 = sum(t in FIRST_PERSON for t in toks)
    c2 = sum(t in SECOND_PERSON for t in toks)
    c3 = sum(t in THIRD_PERSON for t in toks)
    if c1 == c2 == c3 == 0:
        return "none"
    return {1: "first", 2: "second", 3: "third"}[max((c1, 1), (c2, 2), (c3, 3))[1]]


# ── The gate ──────────────────────────────────────────────────────────────────
def fidelity_gate(flat, target, source=None):
    """Grade a flatten->restore pair.

    Args:
      flat:   the flattened training INPUT (must be voiceless but FAITHFUL).
      target: the real-Hemingway training TARGET.
      source: text to check garble against (defaults to `target`, which IS the
              source span that was flattened).

    Returns (passed, hard_reasons, soft_diags, metrics):
      passed      = (no hard_reasons)
      hard_reasons= the flags that FAIL the pair
      soft_diags  = surfaced-but-non-blocking notes (can NEVER flip `passed`)
      metrics     = numbers for the human-readable report
    """
    if source is None:
        source = target
    hard, soft = [], []

    # (1) UNDER-FLATTEN LEAK — input still echoes the target's exact wording.
    fg = five_gram_jaccard(flat, target)
    ratio = difflib.SequenceMatcher(None, target, flat).ratio()
    if fg >= 0.5 or ratio >= 0.8:
        hard.append(f"UNDER-FLATTEN LEAK: 5gram_jaccard={fg:.2f}, edit_ratio={ratio:.2f} "
                    f"(flatten still echoes the original wording)")

    # (2) NAMED-ENTITY LOSS — lenient: morphology/spelling/possessive variants OK.
    tgt_ents = _named_entities(target)
    flat_ents = _named_entities(flat)
    flat_tok = set(_tokens(normalize_quotes(flat)))
    flat_match_pool = (flat_ents | {t for t in flat_tok if len(t) >= 4})
    lost_ents = sorted(
        e for e in tgt_ents
        if e not in flat_tok and not any(_variant_match(e, f) for f in flat_match_pool)
    )
    if lost_ents:
        hard.append(f"NAMED-ENTITY LOST: {lost_ents}")
    # ADDED entity is a SOFT diagnostic only (the keep-hard list is LOSS, not gain).
    tgt_tok = set(_tokens(normalize_quotes(target)))
    tgt_match_pool = (tgt_ents | {t for t in tgt_tok if len(t) >= 4})
    added_ents = sorted(
        e for e in flat_ents
        if e not in tgt_tok and not any(_variant_match(e, t) for t in tgt_match_pool)
    )
    if added_ents:
        soft.append(f"entity added (usually a benign expansion): {added_ents}")

    # (3) CARDINAL NUMBER LOSS — hard only when NOT a digit reformat.
    tgt_card = _cardinal_values(target)
    flat_card = _cardinal_values(flat)
    lost_card = sorted((tgt_card - flat_card).elements())
    added_card = sorted((flat_card - tgt_card).elements())
    new_digits = _digit_tokens(flat) - _digit_tokens(target)
    if lost_card:
        if new_digits:
            soft.append(f"number reformat: cardinal value(s) {lost_card} re-expressed; "
                        f"flatten introduced digits {sorted(new_digits)} (format conversion)")
        else:
            hard.append(f"CARDINAL NUMBER LOST: {lost_card}")
    if added_card and not new_digits:
        soft.append(f"cardinal value(s) added: {added_card}")
    soft_num_delta = sorted(_soft_num_words(target) ^ _soft_num_words(flat))
    if soft_num_delta:
        soft.append(f"ordinal/fraction/'one' wording differs (soft): {soft_num_delta}")

    # (4) PERSON FLIP — first-person loss is the named hard failure; 2nd/3rd soft.
    t1, t2, t3 = _person_flags(target)
    f1, f2, f3 = _person_flags(flat)
    if t1 and not f1:
        hard.append("PERSON FLIP (first-person dropped): target is first-person but "
                    "flatten is not (e.g. 'we lived' must not become impersonal)")
    if (t2 != f2) or (t3 != f3):
        soft.append(f"2nd/3rd-person presence shift (soft): "
                    f"target(2nd={t2},3rd={t3}) vs flatten(2nd={f2},3rd={f3})")

    # (5) GARBLE — corruption of a rare source word the flatten failed to reproduce.
    garble = _garble_tokens(flat, source)
    if garble:
        hard.append("GARBLE (likely generation corruption): "
                    + ", ".join(f"'{t}'~nearest '{s}'(r={r})" for t, s, r in garble))

    metrics = {
        "five_gram_jaccard": round(fg, 3),
        "edit_ratio": round(ratio, 3),
        "lost_entities": lost_ents,
        "added_entities": added_ents,
        "lost_cardinals": lost_card,
        "added_cardinals": added_card,
        "new_digits": sorted(new_digits),
        "garble": garble,
        # LOUD status: if no wordlist is found the garble check is OFF, not passing.
        "garble_check": "ON" if _load_dictionary() is not False else "DISABLED (no wordlist)",
        "target_person": _dominant_person(target),
        "flatten_person": _dominant_person(flat),
        "target_has_first": t1, "flatten_has_first": f1,
    }
    passed = not hard
    return passed, hard, soft, metrics


# ── Re-grade the dress-rehearsal pairs (the reproducible check; no API, no $) ──
def _regrade_dress_set():
    path = os.path.join(HERE, "dress_rehearsal_pairs.jsonl")
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    before_flagged = 0
    after_flagged = 0
    all_garble = []
    after_flags = []
    print(f"Re-grading {len(rows)} dress-rehearsal pairs through fidelity_gate.py")
    print(f"Garble check status: {'ON' if _load_dictionary() is not False else 'DISABLED (no wordlist)'}\n")
    for r in rows:
        flat = r.get("flattened_input")
        target = r.get("real_target") or r.get("span_text")
        if flat is None or target is None:
            continue
        old = r.get("fidelity", {})
        if old and old.get("passed") is False:
            before_flagged += 1
        passed, hard, soft, metrics = fidelity_gate(flat, target)
        if metrics["garble"]:
            all_garble.append((r["id"], metrics["garble"]))
        tag = "CLEAN" if passed else "HARD-FLAG"
        old_tag = "" if not old else ("  (was FLAGGED)" if old.get("passed") is False else "  (was clean)")
        print(f"[{tag:9}] {r['id']}{old_tag}")
        if not passed:
            after_flagged += 1
            after_flags.append((r["id"], hard))
            for h in hard:
                print(f"            HARD: {h}")
        for s in soft:
            print(f"            soft: {s}")

    print("\n" + "=" * 66)
    print(f"HARD-FLAG COUNT  BEFORE (stored gate) = {before_flagged}")
    print(f"HARD-FLAG COUNT  AFTER  (this gate)   = {after_flagged}")
    print("Garble detector fired on:")
    if all_garble:
        for cid, g in all_garble:
            print(f"  {cid}: " + ", ".join(f"'{t}'<-nearest '{s}'(r={r})" for t, s, r in g))
    else:
        print("  (nothing)")
    print("AFTER hard-flags:")
    for cid, hard in after_flags:
        print(f"  {cid}: {' | '.join(hard)}")


def _smoke_test():
    """A few inline asserts so a regression in the de-noise logic is loud."""
    # apostrophe: curly possessive must not invent a lost/added entity
    p, h, s, m = fidelity_gate("I went back to Rinaldi's bed.",
                               "I went back to Rinaldi’s bed.")
    assert not m["lost_entities"] and not m["added_entities"], (m["lost_entities"], m["added_entities"])
    # impersonal 'one' is never a cardinal loss/add
    p, h, s, m = fidelity_gate("From the village one could see the river.",
                               "We could see the river from the village.")
    assert not any("CARDINAL" in x for x in h), h
    # number reformat is soft, not hard
    p, h, s, m = fidelity_gate("At 4:45 I left.", "At a quarter to five I left.")
    assert not any("CARDINAL" in x for x in h), h
    # morphology entity variant is not a loss
    p, h, s, m = fidelity_gate("She had not known Italian men.",
                               "She had never known Italians before.")
    assert not m["lost_entities"], m["lost_entities"]
    # garble IS caught
    p, h, s, m = fidelity_gate("He drew the sword from theleta's folds.",
                               "He drew the sword from the folds of the muleta.")
    assert m["garble"], "garble detector missed 'theleta'"
    assert not p, "garble must hard-fail the pair"
    # a REAL cardinal drop (no digit reformat) still hard-fails
    p, h, s, m = fidelity_gate("He had to kill the bulls.",
                               "He had to kill five bulls.")
    assert any("CARDINAL" in x for x in h), h
    print("  [pass] de-noise smoke test: apostrophe / one / reformat / morphology / garble / real-loss")


if __name__ == "__main__":
    print("fidelity_gate.py — inline smoke test:")
    _smoke_test()
    print("\n" + "=" * 66 + "\n")
    _regrade_dress_set()
