"""
gen_bucket2.py — BUCKET-2 (request->real) generator, ONE parameterized file for
all 5 works. CLONE of gen_bucket3_farewell.py with the bucket-2 deltas.

WHAT IT DOES (plain English):
  Bucket 2 is the "answer in voice" half: a real person types a plain everyday
  REQUEST ("Describe the river and the plain ...") and the model must answer in
  Hemingway's voice. Each training pair is  request -> real :
    - REAL Hemingway span = the training TARGET (genuine voice, never imitated).
    - Gemini INVENTS the matching request = the training INPUT (a plain task, NOT
      a style instruction). The request is the thing we generate; the answer is
      always real Hemingway.

  This REUSES, never reinvents, the proven machinery:
    - 04_mine_passages.mine_work + span_is_clean  -> this work's clean prose spans.
    - spine.SpanRegistry / append_record / load_done_ids / containment / content_hash.
    - fidelity_gate.normalize_quotes                -> curly->ascii before matching.
    - 07_acceptance_gate._META_RE                   -> proven meta/AI-leak patterns.

CRITICAL CORRECTNESS — RESERVATION:
  Before mining, we pre-claim EVERY span already used by training or held out for
  eval, so Bucket 2 cannot collide with them:
    1. bucket1_reserved.jsonl          (reserved reflective spans)
    2. bucket3/*.jsonl   (the 367 PER-WORK rows — NOT bucket3_all.jsonl's 362; the
       5 trimmed rows are still training-adjacent and must stay reserved)
    3. dress_rehearsal_pairs.jsonl     (22 held-out eval spans)
  A False claim (an overlap, e.g. a dress span sitting inside a bucket3 span) is
  harmless — first claim wins. We then mine bucket "2" on that loaded registry,
  shuffle for spread, and stream each accepted request->real pair.

NEVER-RE-PAY: accepted pairs stream to bucket2/<work>.jsonl; rejects ([UNSUITABLE]/
  [ERROR]/failed per-pair check) stream their span id to bucket2/_skip_<work>.jsonl.
  On resume, done = accepted ids UNION skip ids, so we never pay for a span twice.

RUN (Bash; PowerShell hangs this box):
  python pipeline/gen_bucket2.py --work farewell-to-arms --dry       # mine+reserve, no API/no $
  python pipeline/gen_bucket2.py --work farewell-to-arms --smoke 8   # produce 8 NEW pairs
  python pipeline/gen_bucket2.py --work the-sun-also-rises --cap 120  # override ceiling
"""
import os, sys, json, time, glob, random, string, re, urllib.request, urllib.error, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spine                                            # noqa: E402
miner = importlib.import_module("04_mine_passages")     # mine_work, span_is_clean
gate07 = importlib.import_module("07_acceptance_gate")  # _META_RE (proven meta patterns)
import fidelity_gate                                    # noqa: E402  normalize_quotes

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
VALID_WORKS = {
    "farewell-to-arms", "the-sun-also-rises", "men-without-women",
    "in-our-time", "three-short-stories-and-ten-poems",
}
MODEL = "gemini-2.5-flash"
TEMP = 0.7                 # request invention wants natural variety, not reliability
TEMP_RETRY = 0.9          # decorrelate the one regeneration
MAX_TOKENS = 256          # a request is one short sentence
INTER_CALL_SLEEP = 1.3
SEED = 222                # deterministic shuffle (stable across resumes)
DEFAULT_CAP = 115         # ceiling on CLEAN OUTPUT pairs per work (override w/ --cap)

ROOT = "https://generativelanguage.googleapis.com/v1beta"

# Lazy-loaded secrets: importing this module must need NO key file and NO prompt
# file (so 08_bucket2_gate can import us, and --dry can run, with both absent).
# These are read-and-cached on first call, only at generation time.
KEY = None
REQUEST_PROMPT = None


def get_key():
    """Read-and-cache the Gemini API key on first use (not at import)."""
    global KEY
    if KEY is None:
        KEY = open(os.path.join(HERE, "..", "gemini_key.txt"), encoding="utf-8").read().strip()
    return KEY


def get_prompt():
    """Read-and-cache the request-invention prompt template on first use."""
    global REQUEST_PROMPT
    if REQUEST_PROMPT is None:
        REQUEST_PROMPT = open(os.path.join(HERE, "bucket2_request_prompt.txt"),
                              encoding="utf-8").read()
    return REQUEST_PROMPT

B1_RESERVED = os.path.join(HERE, "bucket1_reserved.jsonl")
B3_DIR = os.path.join(HERE, "bucket3")
DRESS = os.path.join(HERE, "dress_rehearsal_pairs.jsonl")

OPENERS = {"describe", "tell", "write", "what", "paint", "set", "explain",
           "recount", "give", "picture", "show", "capture", "walk", "how"}

# ── Request-side leak detection (the load-bearing check) ───────────────────────
# 5-gram Jaccard is BLIND to a one-sentence request (a 12-word request shares no
# 5-gram with a 120-word target even when it lifts a 3-word phrase verbatim). So we
# add a contiguous-run check: flag any shared run of >=3 consecutive NON-STOPWORD
# tokens after dropping stopwords, UNLESS the whole run is proper nouns (one shared
# proper-name run is allowed). This complements spine.containment(n=5) (>=5-word run).
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "at", "by",
    "for", "with", "from", "as", "into", "onto", "over", "under", "up", "down", "out",
    "off", "about", "than", "this", "that", "these", "those", "there", "here", "then",
    "when", "while", "where", "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "have", "has", "had", "will", "would", "shall", "should",
    "can", "could", "may", "might", "must", "not", "no", "so", "such", "very", "too",
    "more", "most", "much", "many", "few", "some", "any", "all", "i", "me", "my",
    "we", "us", "our", "you", "your", "he", "him", "his", "she", "her", "it", "its",
    "they", "them", "their", "what", "which", "who", "whom", "how", "why", "whose",
    "like", "through", "across", "along", "around", "just", "also", "only", "one",
    # request-scaffold words (never lifted from the target — drop so they don't
    # manufacture a spurious shared run)
    "describe", "tell", "write", "paint", "walk", "picture", "show", "capture",
    "give", "explain", "recount", "scene", "short", "piece", "sentences", "sentence",
    "quick", "subject", "set",
}


def _content_seq(text):
    """[(lower_token, is_proper)] over word tokens, stopwords dropped. is_proper =
    capitalized AND not the first token AND not 'I' (the openers are capitalized but
    sentence-initial, so they are never marked proper)."""
    toks = re.findall(r"[A-Za-z'’]+", text)
    out = []
    for i, t in enumerate(toks):
        low = t.lower().strip("'’")
        if not low or low in _STOPWORDS:
            continue
        is_proper = (i > 0 and t[:1].isupper() and low != "i")
        out.append((low, is_proper))
    return out


def _contiguous_run_leak(request, target, n=3):
    """Return the offending run string if request and target share a contiguous run
    of >=n non-stopword tokens that is NOT entirely proper nouns IN THE TARGET; else
    None. Properness (the exemption) is decided by the TARGET's capitalization, not
    the request's — so a Title-Cased lift of a lowercase common-noun run ("old stone
    bridge" -> "the Old Stone Bridge") is still flagged, while a genuinely proper run
    in the target ("San Sebastian") stays exempt."""
    req = [w for (w, _p) in _content_seq(request)]
    tgt = _content_seq(target)
    if len(req) < n or len(tgt) < n:
        return None
    # Map each target word-run -> whether that run is entirely proper IN THE TARGET.
    # If a word-run occurs both proper and common in the target, the common (non-
    # exempt) occurrence wins, so a shared run still gets flagged.
    tgt_ngrams = {}
    for i in range(len(tgt) - n + 1):
        window = tgt[i:i + n]
        key = tuple(w for (w, _p) in window)
        all_proper = all(p for (_w, p) in window)
        tgt_ngrams[key] = (tgt_ngrams[key] and all_proper) if key in tgt_ngrams else all_proper
    for i in range(len(req) - n + 1):
        key = tuple(req[i:i + n])
        if key in tgt_ngrams and not tgt_ngrams[key]:
            return " ".join(key)
    return None


# ── Request-side meta/style leak detection ────────────────────────────────────
# Bucket-2's REQUEST is a NEW artifact nothing in 07 inspects. Ban: 07's proven
# _META_RE (AI/instruction/'gemini'/'in the style of' ...), bare hemingway/ernest,
# the source nouns, and explicit style words. We OMIT bare "line"/"page" — they are
# real content words ("line of troops", "front page"); the text-line sense is caught
# by the "this line/page" pointer instead, with near-zero false-positive cost.
_REQUEST_META_WORDS = ("passage", "text", "excerpt", "author", "writer", "novel",
                       "story", "book", "chapter", "style", "voice", "narrator")
_REQUEST_META_WORD_RE = re.compile(r"\b(" + "|".join(_REQUEST_META_WORDS) + r")\b",
                                   re.IGNORECASE)
_REQUEST_META_EXTRA = [re.compile(p, re.IGNORECASE) for p in (
    r"\bin the style of\b", r"\bwrite like\b",
    r"\bpoetically\b", r"\bvividly\b", r"\bbeautifully\b", r"\blyrically\b",
    r"\bevocatively\b", r"\btone\b",
    r"\bhemingway\b", r"\bernest\b",
    r"\bthis (passage|text|excerpt|scene|river|story|book|chapter|line|page)\b",
)]


def _meta_hit(req_norm):
    """Return a short reason string if the request trips any meta/style ban, else None."""
    for rx in gate07._META_RE:
        if rx.search(req_norm):
            return "metaRE:" + rx.pattern
    m = _REQUEST_META_WORD_RE.search(req_norm)
    if m:
        return "word:" + m.group(1).lower()
    for rx in _REQUEST_META_EXTRA:
        if rx.search(req_norm):
            return "extra:" + rx.pattern
    return None


# Abbreviations / single initials whose trailing period is NOT a sentence boundary.
# Reuse the miner's set so "St. Louis", "Mr. Frazer", "Mt. Tamalpais", "J. Barnes"
# are not mis-read as two sentences (mirror 04_mine_passages._ABBREV + initial guard).
_ABBREV = miner._ABBREV


def _is_multi_sentence(request):
    """True if the request carries an internal sentence boundary (terminal punct +
    space + capital/digit) — i.e. it is more than one sentence. A period preceded by
    a single capital initial ("J.") or a known abbreviation ("St.", "Mr.") is NOT a
    boundary (mirror the miner's guard); '!'/'?' always split."""
    s = request.strip()
    for m in re.finditer(r"[.!?][\"'’)\]]*\s+[A-Z0-9]", s):
        if s[m.start()] == ".":
            j = m.start()
            k = j
            while k > 0 and (s[k - 1].isalnum() or s[k - 1] in ".'’"):
                k -= 1
            prev = s[k:j]
            bare = prev.rstrip(".").lower()
            if len(prev.rstrip(".")) == 1 and prev[:1].isupper():
                continue                                   # single initial, e.g. "J."
            if bare in _ABBREV:
                continue                                   # known abbrev, e.g. "St."
        return True
    return False


# ── Per-pair request check (replaces the bucket-3 fidelity_gate call) ──────────
def request_check(request, target):
    """Grade an invented request against its real-Hemingway target.

    Returns (passed, hard, soft, metrics):
      HARD 'leak'   -> request lifts wording from the target (>=5-word run via
                       containment, OR >=3 non-stopword contiguous run).
      HARD 'meta'   -> request names a source/the act of writing/a style word/Hemingway.
      HARD 'length' -> request word count outside [4,40], longer than the target,
                       newline-containing, or multi-sentence (degenerate shape).
      SOFT 'opener' -> request does not start with a known request verb (rotation hint).
    """
    req_norm = fidelity_gate.normalize_quotes(request)
    tgt_norm = fidelity_gate.normalize_quotes(target)
    hard, soft, metrics = [], [], {}

    words = req_norm.split()
    wc = len(words)
    tgt_wc = len(tgt_norm.split())
    metrics["word_count"] = wc

    # length / shape (degenerate requests)
    if (wc < 4 or wc > 40 or wc > tgt_wc or "\n" in request.strip()
            or _is_multi_sentence(request)):
        hard.append("length")

    # meta / style leak
    mh = _meta_hit(req_norm)
    if mh:
        metrics["meta_hit"] = mh
        hard.append("meta")

    # wording leak (two detectors; either fires)
    cont = spine.containment(req_norm, tgt_norm, n=5)
    metrics["containment_5"] = round(cont, 3)
    run = _contiguous_run_leak(req_norm, tgt_norm)
    if run:
        metrics["leak_run"] = run
    if cont > 0 or run:
        hard.append("leak")

    # SOFT opener-rotation hint
    first = words[0].lower().strip(string.punctuation) if words else ""
    metrics["opener"] = first
    if first not in OPENERS:
        soft.append("opener:" + first)

    return (not hard), hard, soft, metrics


# ── Gemini call (proven machinery: empty-candidate guard + jittered backoff) ────
def generate(prompt, temperature, retries=6):
    """POST generateContent, key via ?key=, thinkingBudget=0, exponential backoff
    with jitter on 429/500/503. Returns text, or an "[ERROR ...]" string. A safety-
    blocked / empty-candidates response is returned as an error IMMEDIATELY."""
    url = f"{ROOT}/models/{MODEL}:generateContent?key={get_key()}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": MAX_TOKENS,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cands = data.get("candidates")
            if not cands:
                fb = json.dumps(data.get("promptFeedback", {}))[:160]
                return f"[ERROR NO_CANDIDATES: {fb}]"
            parts = cands[0].get("content", {}).get("parts")
            if not parts:
                return f"[ERROR NO_PARTS finish={cands[0].get('finishReason','?')}]"
            return parts[0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 30) + random.uniform(0, 1.5))
                continue
            return f"[ERROR HTTP {e.code}: {e.read().decode('utf-8')[:160]}]"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 30) + random.uniform(0, 1.5))
                continue
            return f"[ERROR {type(e).__name__}: {e}]"


# ── Reservation (pre-claim B1 + B3 per-work + dress BEFORE mining) ─────────────
def _claim_file(reg, path):
    """Claim every (work, char_start, char_end) row in a jsonl file into reg. A
    torn/overlapping row is tolerated (first claim wins). Returns rows seen."""
    n = 0
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("work") and r.get("char_start") is not None and r.get("char_end") is not None:
                reg.claim(r["work"], r["char_start"], r["char_end"], bucket=str(r.get("bucket", "x")))
                n += 1
    return n


def reserved_registry():
    """Fresh registry pre-loaded with B1 + the 367 per-work B3 rows + dress."""
    reg = spine.SpanRegistry()
    counts = {"bucket1": _claim_file(reg, B1_RESERVED)}
    b3 = 0
    for fp in sorted(glob.glob(os.path.join(B3_DIR, "*.jsonl"))):
        if os.path.basename(fp).startswith("_"):
            continue   # skip run logs / skip files
        b3 += _claim_file(reg, fp)
    counts["bucket3"] = b3
    counts["dress"] = _claim_file(reg, DRESS)
    counts["claimed_total"] = reg.claimed_count()
    return reg, counts


def _skip_ids(path):
    return spine.load_done_ids(path)


def main():
    argv = sys.argv
    dry = "--dry" in argv
    work = argv[argv.index("--work") + 1] if "--work" in argv else None
    smoke = int(argv[argv.index("--smoke") + 1]) if "--smoke" in argv else None
    cap = int(argv[argv.index("--cap") + 1]) if "--cap" in argv else DEFAULT_CAP
    if work not in VALID_WORKS:
        print(f"[FATAL] --work must be one of {sorted(VALID_WORKS)}; got {work!r}")
        sys.exit(2)

    OUT = os.path.join(HERE, "bucket2", work + ".jsonl")
    SKIP = os.path.join(HERE, "bucket2", "_skip_" + work + ".jsonl")

    reg, rcounts = reserved_registry()
    recs, collisions = miner.mine_work(work, reg, bucket="2", cap=None)
    n_mined = len(recs)
    random.Random(SEED).shuffle(recs)

    if dry:
        print(f"WORK={work}")
        print(f"RESERVED_B1_ROWS={rcounts['bucket1']}")
        print(f"RESERVED_B3_ROWS={rcounts['bucket3']}")
        print(f"RESERVED_DRESS_ROWS={rcounts['dress']}")
        print(f"RESERVED_CLAIMED_TOTAL={rcounts['claimed_total']}")
        print(f"B2_CANDIDATE_SUPPLY={n_mined}")
        print(f"COLLISIONS={collisions}")
        print(f"CAP={cap}  (dry: no API, no $)")
        return

    accepted = spine.load_done_ids(OUT)
    skipped = _skip_ids(SKIP)
    done = accepted | skipped
    n_clean = len(accepted)
    new_this_run = 0
    r_unsuitable = r_error = r_leak = r_meta = r_length = 0
    examples = []

    for c in recs:
        if n_clean >= cap:
            break
        if smoke is not None and new_this_run >= smoke:
            break
        cid = c["id"]
        if cid in done:
            continue
        target = c["span_text"]
        prompt = get_prompt().replace("__PASSAGE__", target)

        used_temp = TEMP
        request = generate(prompt, TEMP).strip()
        reason = passed = hard = soft = metrics = None
        bad_request = request    # the actually-rejected text (for skip-list audit)
        detail = ""

        if request.startswith("[ERROR"):
            reason = "error"
        elif request == "[UNSUITABLE]" or request.upper().startswith("[UNSUITABLE]"):
            reason = "unsuitable"
        else:
            passed, hard, soft, metrics = request_check(request, target)
            if not passed:
                request2 = generate(prompt, TEMP_RETRY).strip()
                bad_request = request2
                if request2.startswith("[ERROR"):
                    reason = "error"
                elif request2 == "[UNSUITABLE]" or request2.upper().startswith("[UNSUITABLE]"):
                    reason = "unsuitable"
                else:
                    p2, h2, s2, m2 = request_check(request2, target)
                    if p2:
                        request, passed, hard, soft, metrics, used_temp = \
                            request2, p2, h2, s2, m2, TEMP_RETRY
                    else:
                        reason = h2[0] if h2 else "length"
                        # surface the offending run / meta hit so a leak-skip is auditable
                        detail = (m2.get("leak_run") or m2.get("meta_hit")
                                  or f"wc={m2.get('word_count')}")

        if reason:
            spine.append_record(SKIP, {
                "id": cid, "work": work,
                "char_start": c["char_start"], "char_end": c["char_end"],
                "reason": reason, "detail": detail, "bad_request": bad_request[:160],
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            done.add(cid)
            if reason == "unsuitable":
                r_unsuitable += 1
            elif reason == "error":
                r_error += 1
            elif reason == "leak":
                r_leak += 1
            elif reason == "meta":
                r_meta += 1
            elif reason == "length":
                r_length += 1
            time.sleep(INTER_CALL_SLEEP)
            continue

        rec = {
            "id": cid, "bucket": "2", "work": work,
            "char_start": c["char_start"], "char_end": c["char_end"],
            "span_text": target, "real_target": target,
            "invented_request": request,
            "content_hash": spine.content_hash(target),
            "word_count": c["word_count"],
            "model": MODEL, "temperature": used_temp,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "request_check": {"passed": passed, "hard": hard, "soft": soft, "metrics": metrics},
        }
        spine.append_record(OUT, rec)
        done.add(cid)
        accepted.add(cid)
        n_clean += 1
        new_this_run += 1
        if len(examples) < 12:
            examples.append((request[:90], metrics.get("opener", "")))
        time.sleep(INTER_CALL_SLEEP)

    # ── Lean machine-readable summary (the orchestrating agent reads this) ─────
    skip_total = len(_skip_ids(SKIP))
    print(f"WORK={work}")
    print(f"N_MINED={n_mined}")
    print(f"N_ACCEPTED_TOTAL={n_clean}")
    print(f"NEW_THIS_RUN={new_this_run}")
    print(f"REJECT_UNSUITABLE={r_unsuitable}")
    print(f"REJECT_ERROR={r_error}")
    print(f"REJECT_LEAK={r_leak}")
    print(f"REJECT_META={r_meta}")
    print(f"REJECT_LENGTH={r_length}")
    print(f"SKIP_FILE_TOTAL={skip_total}")
    print(f"COLLISIONS={collisions}")
    print(f"OUT={OUT}")
    for ex, op in examples:
        print(f"SAMPLE [{op}] :: {ex}")


if __name__ == "__main__":
    main()
