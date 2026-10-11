"""
score_generations.py — the M2 eval harness.

INPUT  : generations.json (downloaded from the Colab training notebook). Schema:
  {
    "baseline_system_prompt": "...",
    "n_epochs": 3,
    "rows": [ {id, task, question, reference, baseline, epoch1, epoch2, epoch3}, ... ],   # 100 held-out
    "capability": [ {id, kind, question, expect[], base, epoch1, epoch2, epoch3}, ... ]   # ~12 probes
  }

OUTPUT : eval_scorecard.json (machine) + eval_report.md (plain-English, for Mike).

THE FOUR CHECKS (all per-epoch):
  1. BLIND LLM-JUDGE WIN-RATE — fine-tuned (neutral prompt, voice in weights) vs the FAIR-FIGHT
     baseline (same base model + an honest "write like Hemingway" prompt). A/B order is randomized
     per row to kill position bias. The judge also flags each answer coherent/on-topic; a fine-tuned
     "win" is COHERENCE-GATED — choppy gibberish or an evasive answer cannot win on voice alone.
     Reported STRATIFIED BY TASK, and the report LEADS WITH THE REAL-TEXT SLICE (rewrite+description),
     because those targets are ACTUAL Hemingway and therefore the honest, generalizable proof. The
     practical-Q&A slice is Gemini imitation (per our red-team: circular) → reported but DISCOUNTED.
     reflective_qa is n=4 → ANECDOTAL, footnoted, never headlined.
  2. STYLOMETRICS vs a REAL-HEMINGWAY reference — sentence-length mean/variance, fragment & long-
     sentence rates, polysyndeton ("and"), -ly adverb rate, dialogue density. Shows the fine-tune
     moved toward Hemingway's RHYTHM (descriptive, not pass/fail).
  3. COHERENCE GATE — folded into the judge (a_coherent/b_coherent), plus a cheap degeneracy
     pre-flag (empty / runaway-repetition answers).
  4. CAPABILITY RETENTION — base vs each epoch on off-distribution probes (facts/math/code/reason).
     Catches catastrophic forgetting AND stylistic collapse (answering everything in-voice).

JUDGE = gemini-2.5-flash for the iteration loop ($0; key in ../gemini_key.txt). The FINAL headline
number gets an INDEPENDENT non-Gemini judge later (Mike-approved small spend) — swap via --judge.
Verdicts are CACHED per-epoch (eval_cache/) so re-runs never re-pay.

RUN (Bash; PowerShell hangs this box):
  python pipeline/eval/score_generations.py                      # score real generations.json
  python pipeline/eval/score_generations.py --dry                # offline self-test (no API, mock judge)
  python pipeline/eval/score_generations.py --in path/to.json    # explicit input
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import stylometry  # noqa: E402  the ONE frozen segmenter — reused so the eval can't drift from the gate

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DEFAULT_IN = os.path.join(HERE, "generations.json")
CACHE_DIR = os.path.join(HERE, "eval_cache")
SCORECARD = os.path.join(HERE, "eval_scorecard.json")
REPORT = os.path.join(HERE, "eval_report.md")

# Task -> reporting bucket. The report LEADS with real_text (real Hemingway targets).
TASK_GROUP = {
    "rewrite": "real_text",        # bucket 3 flatten-restore — the hero feature
    "description": "real_text",    # bucket 2 — real Hemingway target
    "practical_qa": "imitation",   # bucket 4 — Gemini imitation, discounted per red-team
    "reflective_qa": "anecdotal",  # bucket 1 — n=4, footnote only
}

# ---------------------------------------------------------------------------
# Gemini judge
# ---------------------------------------------------------------------------
GEM_MODEL = "gemini-2.5-flash"
GEM_ROOT = "https://generativelanguage.googleapis.com/v1beta"

JUDGE_PROMPT = """You are a careful literary judge. Two answers respond to the same REQUEST. Decide which one is MORE in the writing voice of Ernest Hemingway WHILE still being a genuinely good answer.

Hemingway's voice: mostly short, plain, declarative sentences, varied with the occasional long flowing one; simple concrete words; emotional restraint (the "iceberg" — feeling shown through fact and action, not named); very few adjectives or adverbs.

REQUEST:
\"\"\"__Q__\"\"\"

ANSWER A:
\"\"\"__A__\"\"\"

ANSWER B:
\"\"\"__B__\"\"\"

Step 1 — judge each answer ON ITS OWN: is it COHERENT and ON-TOPIC, i.e. does it actually and sensibly answer the request? A stylish answer that is evasive, off-topic, contradictory, or nonsense is NOT coherent.
Step 2 — decide which answer is MORE in Hemingway's voice. An answer that is NOT coherent cannot win; if one side is incoherent, the other wins (or "tie" only if both are similarly coherent AND similarly in-voice).

Return STRICT JSON ONLY, no prose, no code fence:
{"a_coherent": true|false, "b_coherent": true|false, "more_hemingway": "A"|"B"|"tie", "reason": "<one short clause>"}"""


def gemini_judge(prompt, key, retries=4):
    url = f"{GEM_ROOT}/models/{GEM_MODEL}:generateContent?key={key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 300,
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
            return f"[ERROR HTTP {e.code}]"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return f"[ERROR {type(e).__name__}]"


OR_MODEL_DEFAULT = "openai/gpt-4o"
OR_URL = "https://openrouter.ai/api/v1/chat/completions"


def openrouter_judge(prompt, key, model, retries=4):
    """Independent (non-Gemini) judge for the client-facing headline number.
    OpenAI-compatible chat-completions. Key comes from $OPENROUTER_API_KEY (never stored in repo)."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 300,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    for attempt in range(retries):
        req = urllib.request.Request(OR_URL, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return f"[ERROR HTTP {e.code}]"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return f"[ERROR {type(e).__name__}]"


def parse_verdict(raw):
    if raw.startswith("[ERROR"):
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        if "more_hemingway" in v:
            return v
    except json.JSONDecodeError:
        pass
    return None


def mock_judge(prompt):
    """Offline stand-in for --dry: deterministic, leans toward the fine-tuned side so the
    pipeline's win-rate plumbing is exercised. NOT a real measurement."""
    # A and B are randomized upstream; the mock just always says A is coherent & more-hemingway,
    # B coherent — so wins/losses/ties all get exercised across randomized assignments.
    h = int(hashlib.md5(prompt.encode("utf-8")).hexdigest(), 16)
    mh = {0: "A", 1: "B", 2: "tie"}[h % 3]
    return json.dumps({"a_coherent": True, "b_coherent": (h % 5 != 0),
                       "more_hemingway": mh, "reason": "mock"})


# ---------------------------------------------------------------------------
# Check 1 — blind, coherence-gated, stratified win-rate
# ---------------------------------------------------------------------------
def ab_assignment(row_id, epoch):
    """Deterministic per-(row,epoch) A/B swap → reproducible, position-bias-balanced.
    Returns True if A=fine-tuned (B=baseline), False if A=baseline."""
    h = int(hashlib.md5(f"{row_id}|{epoch}".encode("utf-8")).hexdigest(), 16)
    return (h & 1) == 0


def degenerate(text):
    """Cheap pre-flag: empty, or one token repeated to death (a known small-model failure)."""
    t = (text or "").strip()
    if len(t) < 2:
        return True
    words = t.lower().split()
    if len(words) >= 8 and len(set(words)) <= max(2, len(words) // 8):
        return True
    return False


def judge_epoch(data, epoch_key, key, dry, judge_name="gemini", judge_model=OR_MODEL_DEFAULT):
    """Judge every row for one epoch (cached). Returns list of per-row verdict dicts.
    Cache is namespaced per judge backend so each judge keeps its OWN verdicts — the
    independent OpenRouter run can never re-read Gemini's cached grades (and vice-versa)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    tag = "" if judge_name == "gemini" else f"{judge_name}_"   # keep gemini cache path unchanged
    cache = os.path.join(CACHE_DIR, f"judge_{tag}{'dry_' if dry else ''}{epoch_key}.jsonl")
    done = {}
    if os.path.exists(cache):
        for line in open(cache, encoding="utf-8"):
            r = json.loads(line)
            done[r["id"]] = r
    out = []
    fh = open(cache, "a", encoding="utf-8")
    for row in data["rows"]:
        rid = row["id"]
        if rid in done:
            out.append(done[rid])
            continue
        ft, base = row.get(epoch_key, ""), row.get("baseline", "")
        a_is_ft = ab_assignment(rid, epoch_key)
        a_text, b_text = (ft, base) if a_is_ft else (base, ft)
        prompt = (JUDGE_PROMPT.replace("__Q__", row["question"])
                  .replace("__A__", a_text).replace("__B__", b_text))
        if dry:
            raw = mock_judge(prompt)
        elif judge_name == "openrouter":
            raw = openrouter_judge(prompt, key, judge_model)
        else:
            raw = gemini_judge(prompt, key)
        v = parse_verdict(raw)
        rec = {"id": rid, "task": row["task"], "a_is_ft": a_is_ft,
               "verdict": v, "ft_degenerate": degenerate(ft)}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        done[rid] = rec
        out.append(rec)
        if not dry:
            time.sleep(0.6)
    fh.close()
    return out


def tally(verdicts):
    """Coherence-gated win/loss/tie, overall + by reporting group."""
    groups = {"overall": {"win": 0, "loss": 0, "tie": 0, "n": 0}}
    for g in set(TASK_GROUP.values()):
        groups[g] = {"win": 0, "loss": 0, "tie": 0, "n": 0}
    for rec in verdicts:
        v = rec["verdict"]
        grp = TASK_GROUP.get(rec["task"], "overall")
        for bucket in ("overall", grp):
            groups[bucket]["n"] += 1
        if not v:  # judge error → counts toward n but not win/loss/tie
            continue
        a_is_ft = rec["a_is_ft"]
        # map A/B to ft/baseline
        if v["more_hemingway"] == "tie":
            outcome = "tie"
        else:
            ft_won = (v["more_hemingway"] == "A") == a_is_ft
            ft_coherent = v["a_coherent"] if a_is_ft else v["b_coherent"]
            if ft_won and not ft_coherent:
                outcome = "loss"          # COHERENCE GATE: in-voice but incoherent ≠ a win
            elif ft_won:
                outcome = "win"
            else:
                outcome = "loss"
        if rec["ft_degenerate"]:          # cheap degeneracy pre-flag overrides any "win"
            outcome = "loss" if outcome == "win" else outcome
        for bucket in ("overall", grp):
            groups[bucket][outcome] += 1
    for g in groups.values():
        decisive = g["win"] + g["loss"]
        g["win_rate"] = round(g["win"] / decisive, 4) if decisive else None
        g["win_rate_incl_ties"] = round(g["win"] / g["n"], 4) if g["n"] else None
    return groups


# ---------------------------------------------------------------------------
# Check 2 — stylometrics vs a real-Hemingway reference
# ---------------------------------------------------------------------------
_LY = re.compile(r"\b[A-Za-z]+ly\b")
_WORD = re.compile(r"[A-Za-z'’]+")


def extra_metrics(text):
    words = _WORD.findall(text)
    nw = len(words) or 1
    ly = len(_LY.findall(text))
    sents = stylometry.split_sentences(text)
    dlg = sum(1 for s in sents if '"' in s or "“" in s or "”" in s)
    return {"ly_rate": round(ly / nw, 5),
            "dialogue_rate": round(dlg / len(sents), 4) if sents else 0.0}


def agg_style(texts):
    """Average the frozen rhythm fingerprint + extras over a list of answers."""
    keys = ["mean_len", "stdev_len", "max_len", "frag_rate", "long_rate", "and_frac"]
    acc = {k: [] for k in keys + ["ly_rate", "dialogue_rate"]}
    for t in texts:
        m = stylometry.style_metrics(t)
        if not m:
            continue
        for k in keys:
            acc[k].append(m[k])
        e = extra_metrics(t)
        acc["ly_rate"].append(e["ly_rate"])
        acc["dialogue_rate"].append(e["dialogue_rate"])
    return {k: round(sum(v) / len(v), 4) if v else None for k, v in acc.items()}


def hemingway_reference():
    """Reference rhythm from the cleaned corpus, measured at ANSWER scale (same chunker the
    Bucket-4 gate used). Falls back to None if the clean corpus isn't present."""
    files = glob.glob(os.path.join(ROOT, "clean", "*_clean.txt"))
    if not files:
        return None
    chunks = []
    for f in files:
        txt = open(f, encoding="utf-8").read()
        chunks.extend(stylometry.chunk_text(txt, target_words=85))
    return agg_style(chunks)


# ---------------------------------------------------------------------------
# Check 4 — capability retention
# ---------------------------------------------------------------------------
def score_capability(data, epoch_keys):
    probes = data.get("capability", [])
    out = {"base": {"pass": 0, "n": 0}, "details": []}
    for ek in epoch_keys:
        out[ek] = {"pass": 0, "n": 0}
    for p in probes:
        exp = [e.lower() for e in p.get("expect", [])]

        def ok(ans):
            a = (ans or "").lower()
            return any(e in a for e in exp) if exp else None
        row = {"id": p["id"], "kind": p["kind"]}
        b_ok = ok(p.get("base", ""))
        out["base"]["n"] += 1
        out["base"]["pass"] += 1 if b_ok else 0
        row["base"] = b_ok
        for ek in epoch_keys:
            e_ok = ok(p.get(ek, ""))
            out[ek]["n"] += 1
            out[ek]["pass"] += 1 if e_ok else 0
            row[ek] = e_ok
        out["details"].append(row)
    for k in ["base"] + epoch_keys:
        out[k]["rate"] = round(out[k]["pass"] / out[k]["n"], 4) if out[k]["n"] else None
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def pct(x):
    return "n/a" if x is None else f"{x*100:.0f}%"


def build_report(data, per_epoch, ref, cap, recommended, judge_label="gemini"):
    L = []
    L.append("# Ernie — M2 Eval Report\n")
    L.append(f"> **Judge:** `{judge_label}`"
             + (" — INDEPENDENT non-Gemini judge: this is the client-facing headline number.\n"
                if judge_label != "gemini" else " — $0 iteration loop (not the final headline).\n"))
    L.append("> **How to read this:** the honest, generalizable proof is the **REAL-TEXT slice** "
             "(rewrite + description — targets are actual Hemingway). The practical-Q&A slice is "
             "Gemini imitation and is **discounted** (our own red-team called it circular). "
             "Reflective-Q&A is only 4 items — **anecdotal**, not a rate.\n")
    epochs = sorted(per_epoch.keys())
    L.append(f"**Recommended model: {recommended.upper()}** — chosen by real-text win-rate, "
             "subject to capability retention not collapsing.\n")
    L.append("## 1. Blind judge win-rate (fine-tuned vs. fair prompted baseline)\n")
    L.append("Win-rate = fine-tuned wins / decisive comparisons (ties excluded). Target > 70%.\n")
    L.append("| epoch | REAL-TEXT (lead) | practical (discounted) | overall | reflective (n=4) |")
    L.append("|---|---|---|---|---|")
    for ek in epochs:
        g = per_epoch[ek]["winrate"]
        L.append(f"| {ek} | **{pct(g['real_text']['win_rate'])}** "
                 f"({g['real_text']['win']}-{g['real_text']['loss']}-{g['real_text']['tie']}) "
                 f"| {pct(g['imitation']['win_rate'])} | {pct(g['overall']['win_rate'])} "
                 f"| {pct(g['anecdotal']['win_rate'])} |")
    L.append("")
    L.append("## 2. Stylometrics vs. real Hemingway (rhythm fingerprint)\n")
    if ref:
        L.append(f"Reference (real Hemingway, answer-sized chunks): mean sentence {ref['mean_len']}w, "
                 f"variance {ref['stdev_len']}, fragment-rate {pct(ref['frag_rate'])}, "
                 f"long-rate {pct(ref['long_rate'])}, 'and' {pct(ref['and_frac'])}, "
                 f"-ly {pct(ref['ly_rate'])}.\n")
    L.append("| column | mean len | variance | frag-rate | long-rate | 'and' | -ly | dialogue |")
    L.append("|---|---|---|---|---|---|---|---|")
    bs = per_epoch[epochs[0]]["style_baseline"]
    L.append(f"| baseline (prompted) | {bs['mean_len']} | {bs['stdev_len']} | {pct(bs['frag_rate'])} "
             f"| {pct(bs['long_rate'])} | {pct(bs['and_frac'])} | {pct(bs['ly_rate'])} | {pct(bs['dialogue_rate'])} |")
    for ek in epochs:
        s = per_epoch[ek]["style_ft"]
        L.append(f"| {ek} (fine-tuned) | {s['mean_len']} | {s['stdev_len']} | {pct(s['frag_rate'])} "
                 f"| {pct(s['long_rate'])} | {pct(s['and_frac'])} | {pct(s['ly_rate'])} | {pct(s['dialogue_rate'])} |")
    L.append("")
    L.append("## 3. Capability retention (off-distribution: facts / math / code / reasoning)\n")
    L.append("Did training cost the model basic ability? (base vs. fine-tuned, neutral prompt both.)\n")
    L.append(f"- base model: **{pct(cap['base']['rate'])}** ({cap['base']['pass']}/{cap['base']['n']})")
    for ek in epochs:
        L.append(f"- {ek}: **{pct(cap[ek]['rate'])}** ({cap[ek]['pass']}/{cap[ek]['n']})")
    drops = [d for d in cap["details"] if d.get("base") and any(d.get(ek) is False for ek in epochs)]
    if drops:
        L.append(f"\n⚠ Probes the base model passed but some epoch FAILED (forgetting): "
                 f"{', '.join(d['id'] for d in drops)}")
    if judge_label == "gemini":
        L.append("\n---\n*This loop's judge is Gemini ($0). The client-facing headline number is "
                 "re-judged by an INDEPENDENT non-Gemini model (see eval_report_openrouter.md).*\n")
    else:
        L.append(f"\n---\n*Judged by `{judge_label}`, fully independent of both the model under test "
                 "(Qwen) and the iteration-loop judge (Gemini). This IS the client-facing headline number.*\n")
    return "\n".join(L)


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN)
    ap.add_argument("--dry", action="store_true", help="offline self-test, mock judge, no API")
    ap.add_argument("--judge", default="gemini", choices=["gemini", "openrouter"],
                    help="judge backend. gemini=$0 iteration loop; openrouter=independent headline number")
    ap.add_argument("--judge-model", default=OR_MODEL_DEFAULT,
                    help="OpenRouter model id for the independent judge (e.g. openai/gpt-4o)")
    ap.add_argument("--epochs", default="",
                    help="comma-list to restrict judged epochs (e.g. epoch3) — saves spend on the independent run")
    args = ap.parse_args()

    if not os.path.exists(args.inp):
        sys.exit(f"input not found: {args.inp}\n(run the Colab notebook, bring back generations.json)")
    data = json.load(open(args.inp, encoding="utf-8"))
    key = ""
    if not args.dry:
        if args.judge == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if not key:
                sys.exit("set $OPENROUTER_API_KEY for the independent judge (not stored in repo)")
        else:
            kp = os.path.join(ROOT, "gemini_key.txt")
            key = open(kp, encoding="utf-8").read().strip() if os.path.exists(kp) else ""
            if not key:
                sys.exit("no gemini_key.txt — use --dry for an offline self-test")

    epoch_keys = [f"epoch{i}" for i in range(1, data.get("n_epochs", 3) + 1)
                  if any(f"epoch{i}" in r for r in data["rows"])]
    if args.epochs.strip():
        want = {e.strip() for e in args.epochs.split(",") if e.strip()}
        epoch_keys = [ek for ek in epoch_keys if ek in want]
        if not epoch_keys:
            sys.exit(f"--epochs {args.epochs} matched none of the available epochs")
    ref = hemingway_reference()
    cap = score_capability(data, epoch_keys)

    per_epoch = {}
    for ek in epoch_keys:
        verdicts = judge_epoch(data, ek, key, args.dry, args.judge, args.judge_model)
        winrate = tally(verdicts)
        style_ft = agg_style([r.get(ek, "") for r in data["rows"]])
        style_baseline = agg_style([r.get("baseline", "") for r in data["rows"]])
        per_epoch[ek] = {"winrate": winrate, "style_ft": style_ft, "style_baseline": style_baseline}

    # recommend: best real-text win-rate among epochs whose capability didn't collapse
    base_cap = cap["base"]["rate"] or 0.0
    eligible = [ek for ek in epoch_keys if (cap[ek]["rate"] or 0.0) >= base_cap - 0.15]
    pool = eligible or epoch_keys
    recommended = max(pool, key=lambda ek: per_epoch[ek]["winrate"]["real_text"]["win_rate"] or -1)

    judge_label = args.judge if args.judge == "gemini" else f"{args.judge}:{args.judge_model}"
    suffix = "" if args.judge == "gemini" else f"_{args.judge}"
    scorecard_path = SCORECARD.replace(".json", f"{suffix}.json")
    report_path = REPORT.replace(".md", f"{suffix}.md")
    scorecard = {"n_epochs": len(epoch_keys), "dry_run": args.dry, "reference": ref,
                 "judge": judge_label, "capability": cap, "recommended": recommended,
                 "per_epoch": per_epoch}
    json.dump(scorecard, open(scorecard_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(report_path, "w", encoding="utf-8").write(
        build_report(data, per_epoch, ref, cap, recommended, judge_label))
    print(f"Scored {len(epoch_keys)} epochs over {len(data['rows'])} held-out questions"
          f"{' (DRY)' if args.dry else ''}.")
    print(f"Recommended: {recommended}")
    for ek in epoch_keys:
        rt = per_epoch[ek]["winrate"]["real_text"]
        print(f"  {ek}: real-text win-rate {pct(rt['win_rate'])} "
              f"({rt['win']}-{rt['loss']}-{rt['tie']}); capability {pct(cap[ek]['rate'])}")
    print(f"Judge: {judge_label}")
    print(f"Wrote {scorecard_path}\nWrote {report_path}")


if __name__ == "__main__":
    main()
