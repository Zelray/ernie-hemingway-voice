"""
05_dress_rehearsal_flatten.py — the $0 DRESS REHEARSAL for bucket-3 (flatten-restore).

WHY THIS EXISTS (plain English):
  Bucket 3 is the HERO feature: paste an article, get it back in Hemingway's voice.
  We build training pairs as  flat -> real :
    - REAL Hemingway span  = the training TARGET (genuine voice, never imitated).
    - Gemini FLATTENS it    = the training INPUT  (voiceless, bureaucratic prose).
  Before we pay for the full ~350-pair run, we rehearse on ~22 hand-vetted spans
  to prove (a) the flatten machinery works and (b) an automated FIDELITY GATE can
  catch the two failure modes the review named:
    1. UNDER-FLATTEN LEAK — the "flattened" input still echoes the original wording
       (shared 5-word runs / high edit-similarity) -> the pair is trivial/leaky.
    2. CONTENT DRIFT — the flatten silently dropped a NAME, a NUMBER, or flipped the
       grammatical PERSON (the "we lived in a house" -> "the residents occupied a
       house" failure). The flatten must change the VOICE, never the FACTS.

  This reuses the proven Gemini call machinery from 02/03 (retry/backoff,
  thinkingBudget=0, gemini-2.5-flash, key via ?key=) and the spine.py integrity
  helpers (content_hash, five_gram_jaccard, append_record, load_done_ids).

RUN (Bash; PowerShell hangs this box):
  python pipeline/05_dress_rehearsal_flatten.py
"""
import os, json, time, re, difflib, urllib.request, urllib.error, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from spine import content_hash, five_gram_jaccard, append_record, load_done_ids, _tokens

# ── Gemini call config (identical machinery to 03_flatten_pilot.py) ───────────
MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.3   # flatten wants RELIABILITY, not creativity -> low heat
ROOT = "https://generativelanguage.googleapis.com/v1beta"
KEY = open(os.path.join(HERE, "..", "gemini_key.txt"), encoding="utf-8").read().strip()

CANDIDATES_PATH = os.path.join(HERE, "dress_rehearsal_candidates.jsonl")
OUT_JSONL = os.path.join(HERE, "dress_rehearsal_pairs.jsonl")
OUT_MD = os.path.join(HERE, "dress_rehearsal_pairs.md")

# ── Skeptic's flagged ids — SKIP these (recorded in the .md for the record) ───
SKEPTIC_FLAGGED = {
    "b3_three-short-stories-and-ten-poems_00021369":
        "HARD FAIL - pure unmarked DIALOGUE/monologue, zero narration (imperatives). "
        "Training the model to 'restore' an article into spoken dialogue is the caricature failure.",
    "b3_men-without-women_00002112":
        "FLAG - all-caps drop-cap artifact ('MANUEL GARCIA') would teach the model to SHOUT names; "
        "also proper-noun-dense (pn=9.3%).",
    "b3_in-our-time_00005830":
        "BORDERLINE FLAG - hands ~half the span to a repetitive embedded prayer/monologue; "
        "a flattened article would never produce 'please please please christ'.",
}

# ── The amended FLATTEN prompt (03's voice-stripping + review's fidelity fixes) ─
FLATTEN_PROMPT = """You will be given a short passage of literary prose. Rewrite it in plain, neutral, expository English that conveys the SAME literal information and meaning, but strips ALL distinctive style.

Requirements:
- Ordinary modern vocabulary. No literary or poetic word choices.
- Standard medium-to-long sentences with normal subordination (because, which, although, since). Do NOT copy the original's sentence lengths, phrasing, or rhythm. Re-order and re-structure freely.
- Neutral, explanatory tone — like a flat paraphrase a bored student or a textbook would write.
- The result must NOT sound like the original author. Erase the voice completely.

PRESERVE EXACTLY (this is critical — change the VOICE, never the FACTS):
- Every concrete FACT. Add no new facts. Remove no facts.
- Every NUMBER and quantity (e.g. "five bulls", "a quarter to five", "the second course"). Do not round, drop, or change them.
- Every NAMED ENTITY — all proper names of people and places (e.g. Cohn, Brett, Bayonne, Milan) exactly as written. Do not rename, omit, or invent names.
- The SAME grammatical PERSON and point of view. If the passage is first person ("I", "we"), keep it first person — do NOT convert "we lived in a house" into "the residents occupied a house". If it is third person ("he", "she", "they"), keep it third person. Never change who is speaking or whose viewpoint it is.

Output ONLY the rewritten plain version. No preamble, no quotes, no explanation.

Passage:
__PASSAGE__"""


def generate(prompt, retries=4):
    """Proven Gemini call: POST to generateContent, key via ?key=, thinkingBudget=0,
    exponential backoff on 429/500/503. Returns text or an "[ERROR ...]" string."""
    url = f"{ROOT}/models/{MODEL}:generateContent?key={KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": 1000,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return f"[ERROR HTTP {e.code}: {e.read().decode('utf-8')[:160]}]"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return f"[ERROR {type(e).__name__}: {e}]"


# ── Fidelity-gate helpers (stdlib + spine only; proxies bias toward catching loss) ─
FIRST_PERSON = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves"}
SECOND_PERSON = {"you", "your", "yours", "yourself", "yourselves"}
THIRD_PERSON = {"he", "him", "his", "himself", "she", "her", "hers", "herself",
                "they", "them", "their", "theirs", "themselves"}  # "it/its" excluded: dummy pronoun, not narrative person

NUMBER_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety", "hundred", "thousand", "million", "billion", "dozen",
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
    "ninth", "tenth", "eleventh", "twelfth", "last",
    "once", "twice", "thrice", "half", "quarter", "single", "double", "triple",
}

# Common capitalized function/sentence-starter words that are NOT named entities.
CAP_STOPLIST = {
    "the", "a", "an", "it", "its", "he", "she", "they", "we", "you", "i", "in", "on",
    "at", "up", "down", "there", "then", "when", "while", "but", "and", "so", "if",
    "as", "his", "her", "him", "them", "their", "this", "that", "these", "those",
    "all", "no", "not", "after", "afterward", "before", "some", "sometimes", "only",
    "perhaps", "dear", "oh", "please", "or", "of", "for", "to", "with", "from", "by",
    "was", "were", "is", "are", "be", "been", "had", "have", "did", "do", "one", "two",
    "three", "while", "living", "knotting", "down-stairs", "troops",
}

_CAP = re.compile(r"[A-Z][\w'’.-]*", re.UNICODE)


def _named_entities(text):
    """Proxy for named entities: Capitalized tokens that are NOT sentence-initial,
    NOT in the function-word stoplist, and not the bare pronoun 'I'. Returns a set
    of lowercased surface forms. UNDER-detects (misses names that only ever appear
    at a sentence start, e.g. behind 'Mrs.'); that is fine — it is a screen, and we
    check LOSS by literal-token survival below, which is robust to position."""
    ents = set()
    for m in _CAP.finditer(text):
        start = m.start()
        # sentence-initial? walk back over whitespace/quotes to the prior real char.
        j = start - 1
        while j >= 0 and text[j] in " \t\n\r\"'’“”‘()—-":
            j -= 1
        sentence_initial = (j < 0) or (text[j] in ".!?")
        if sentence_initial:
            continue
        tok = m.group(0).strip(".'’-“”\"").lower()
        if not tok or tok == "i" or tok in CAP_STOPLIST:
            continue
        ents.add(tok)
    return ents


def _numbers(text):
    """Set of distinct number tokens: digit runs plus spelled-out cardinals,
    ordinals, fractions and multipliers."""
    toks = _tokens(text)
    return {t for t in toks if t.isdigit() or t in NUMBER_WORDS}


def _person_flags(text):
    """(has_first, has_second, has_third) presence booleans over narrative pronouns."""
    toks = set(_tokens(text))
    return (bool(toks & FIRST_PERSON), bool(toks & SECOND_PERSON), bool(toks & THIRD_PERSON))


def _dominant_person(text):
    toks = _tokens(text)
    c1 = sum(t in FIRST_PERSON for t in toks)
    c2 = sum(t in SECOND_PERSON for t in toks)
    c3 = sum(t in THIRD_PERSON for t in toks)
    if c1 == c2 == c3 == 0:
        return "none"
    return {1: "first", 2: "second", 3: "third"}[max((c1, 1), (c2, 2), (c3, 3))[1]]


def fidelity_gate(flat, target):
    """Run the automated gate on a {flattened_input, real_target} pair.
    Returns (passed: bool, reasons: [str], metrics: dict). Reasons name the
    SPECIFIC offending token so a human can adjudicate in one glance."""
    reasons = []

    # (a) UNDER-FLATTEN LEAK: shared 5-word runs / high raw edit-similarity.
    fg = five_gram_jaccard(flat, target)
    ratio = difflib.SequenceMatcher(None, target, flat).ratio()
    if fg >= 0.5 or ratio >= 0.8:
        reasons.append(f"UNDER-FLATTEN LEAK: 5gram_jaccard={fg:.2f}, edit_ratio={ratio:.2f} "
                       f"(flatten still echoes the original wording)")

    # (b) NAMED-ENTITY drift: a target name absent from the flatten, or a new name invented.
    tgt_ents = _named_entities(target)
    flat_tokens = set(_tokens(flat))
    lost_ents = sorted(e for e in tgt_ents if e not in flat_tokens)
    flat_ents = _named_entities(flat)
    target_tokens = set(_tokens(target))
    added_ents = sorted(e for e in flat_ents if e not in target_tokens)
    if lost_ents:
        reasons.append(f"NAMED-ENTITY LOST: {lost_ents}")
    if added_ents:
        reasons.append(f"NAMED-ENTITY ADDED (possible hallucination): {added_ents}")

    # (c) NUMBER drift: a target number absent from the flatten, or a new number added.
    tgt_nums = _numbers(target)
    flat_nums = _numbers(flat)
    lost_nums = sorted(tgt_nums - flat_nums)
    added_nums = sorted(flat_nums - tgt_nums)
    if lost_nums:
        reasons.append(f"NUMBER LOST: {lost_nums}")
    if added_nums:
        reasons.append(f"NUMBER ADDED/CHANGED: {added_nums}")

    # (d) PERSON drift: HARD-flag first-person retention only (the named failure mode).
    #     Second/third shifts are SOFT diagnostics (generic 'you'->'one' is a good move).
    t1, t2, t3 = _person_flags(target)
    f1, f2, f3 = _person_flags(flat)
    if t1 != f1:
        reasons.append(f"PERSON DRIFT (HARD): first-person present in target={t1} vs flatten={f1} "
                       f"(e.g. 'we lived' must not become impersonal)")
    second_diag = None
    if t2 != f2:
        second_diag = f"second-person target={t2} vs flatten={f2} (soft: generic 'you'->'one' is OK)"

    metrics = {
        "five_gram_jaccard": round(fg, 3),
        "edit_ratio": round(ratio, 3),
        "lost_entities": lost_ents,
        "added_entities": added_ents,
        "lost_numbers": lost_nums,
        "added_numbers": added_nums,
        "target_person": _dominant_person(target),
        "flatten_person": _dominant_person(flat),
        "target_has_first": t1, "flatten_has_first": f1,
        "second_person_diag": second_diag,
    }
    passed = len(reasons) == 0
    return passed, reasons, metrics


def main():
    # Load candidates (provenance: char offsets + content_hash) keyed by id.
    cands = []
    with open(CANDIDATES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cands.append(json.loads(line))

    clean = [c for c in cands if c["id"] not in SKEPTIC_FLAGGED]

    # Idempotent resume: don't re-spend on ids already in the output jsonl.
    done = load_done_ids(OUT_JSONL)
    existing = {}
    if os.path.exists(OUT_JSONL):
        with open(OUT_JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        r = json.loads(line)
                        existing[r["id"]] = r
                    except json.JSONDecodeError:
                        continue

    results = []
    errors = []
    for c in clean:
        cid = c["id"]
        if cid in done and cid in existing:
            results.append(existing[cid])
            continue
        target = c["span_text"]
        flat = generate(FLATTEN_PROMPT.replace("__PASSAGE__", target))
        if flat.startswith("[ERROR"):
            errors.append((cid, flat))
            # still record the error so a resume retries it next run (not in jsonl)
            results.append({"id": cid, "work": c["work"], "error": flat,
                            "real_target": target, "flattened_input": None,
                            "fidelity": {"passed": False, "reasons": ["GENERATION ERROR"]}})
            time.sleep(1.2)
            continue
        passed, reasons, metrics = fidelity_gate(flat, target)
        rec = {
            "id": cid,
            "bucket": "3",
            "work": c["work"],
            "char_start": c["char_start"],
            "char_end": c["char_end"],
            "span_text": target,
            "real_target": target,
            "flattened_input": flat,
            "content_hash": content_hash(target),
            "model": MODEL,
            "temperature": TEMPERATURE,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "fidelity": {"passed": passed, "reasons": reasons, "metrics": metrics},
        }
        append_record(OUT_JSONL, rec)   # crash-safe, one row at a time
        results.append(rec)
        time.sleep(1.2)

    # ── Write the human-readable .md ──────────────────────────────────────────
    graded = [r for r in results if "error" not in r]
    n_clean = sum(1 for r in graded if r["fidelity"]["passed"])
    n_flagged = sum(1 for r in graded if not r["fidelity"]["passed"])
    fg_vals = [r["fidelity"]["metrics"]["five_gram_jaccard"] for r in graded]

    md = ["# Bucket-3 dress rehearsal — flatten-restore fidelity check",
          f"\nModel `{MODEL}` · temperature {TEMPERATURE} · "
          f"{len(graded)} attempted, {n_clean} clean, {n_flagged} flagged, {len(errors)} errors.\n",
          "FLATTENED = training INPUT (must be voiceless/bureaucratic). "
          "REAL TARGET = training answer (genuine Hemingway). "
          "Gate checks: under-flatten leak, named-entity loss, number loss, first-person drift.\n"]
    if fg_vals:
        md.append(f"\n5-gram-Jaccard(flatten,target) distribution — "
                  f"min {min(fg_vals):.3f} / median {statistics.median(fg_vals):.3f} / "
                  f"max {max(fg_vals):.3f} (lower = more thoroughly re-worded).\n")
    md.append("\n---\n")

    for r in results:
        if "error" in r:
            md.append(f"\n## ⚠️ {r['id']} — GENERATION ERROR\n\n`{r['error']}`\n\n---\n")
            continue
        f = r["fidelity"]
        tag = "✅ CLEAN" if f["passed"] else "🚩 FLAGGED"
        m = f["metrics"]
        md.append(f"\n## {tag} — {r['id']}\n")
        md.append(f"_{r['work']} · chars [{r['char_start']}:{r['char_end']}] · "
                  f"5gram={m['five_gram_jaccard']} edit={m['edit_ratio']} · "
                  f"person {m['target_person']}→{m['flatten_person']}_\n")
        if not f["passed"]:
            for reason in f["reasons"]:
                md.append(f"- 🚩 {reason}\n")
        if m["second_person_diag"]:
            md.append(f"- (diag) {m['second_person_diag']}\n")
        md.append(f"\n**FLATTENED (input):** {r['flattened_input']}\n")
        md.append(f"\n**REAL TARGET (answer):** {r['real_target']}\n")
        md.append("\n---\n")

    md.append("\n## Skipped (skeptic-flagged, NOT attempted)\n")
    for sid, why in SKEPTIC_FLAGGED.items():
        md.append(f"- **{sid}** — {why}\n")

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))

    # ── Lean stdout summary (the orchestrating agent reads this) ───────────────
    print(f"ATTEMPTED={len(graded)} CLEAN={n_clean} FLAGGED={n_flagged} ERRORS={len(errors)}")
    if fg_vals:
        print(f"FIVEGRAM min={min(fg_vals):.3f} median={statistics.median(fg_vals):.3f} max={max(fg_vals):.3f}")
    for r in graded:
        if not r["fidelity"]["passed"]:
            print(f"FLAG {r['id']}: {' | '.join(r['fidelity']['reasons'])}")
    for cid, err in errors:
        print(f"ERROR {cid}: {err[:80]}")
    print(f"JSONL={OUT_JSONL}")
    print(f"MD={OUT_MD}")


if __name__ == "__main__":
    main()
