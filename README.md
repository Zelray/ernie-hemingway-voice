# Ernie — a 3B model that answers in Hemingway's voice

**Fine-tuning beat prompting for voice — and here's the measured proof.**

Ernie is Qwen2.5-3B-Instruct fine-tuned with QLoRA on Ernest Hemingway's **public-domain** works
— not to *continue prose*, but to *answer questions* in his voice. It won **73%** of blind,
randomized head-to-head comparisons against the same base model given an honest, strong
"write like Hemingway" prompt — judged by an independent LLM judge (GPT-4o) that had no stake
in the result.

| Headline result (epoch 3) | |
|---|---|
| **Blind-judge win rate vs fairly-prompted baseline (real-text tasks)** | **73%** (GPT-4o judge, 35–13) |
| Overall win rate, all task types | 86% |
| Capability retained vs base model (math / code / facts / reasoning) | 11 / 12 (92%) |
| Sentence-rhythm variance (higher = human-like) | **5.92** — real Hemingway 6.46, prompted baseline 1.55 |

That last row is the thesis in one number. A prompt can make a model *imitate short sentences*
(the baseline's flat 1.55 — a monotone caricature). Only training on real examples teaches the
*rhythm* — the long, and-chained sentences mixed with three-word fragments that make Hemingway
read like Hemingway. Ernie lands almost exactly on the real thing.

---

## The demo

A 3-column compare, built to be a **fair fight** — the kind a skeptical client can't poke holes in:

1. **Left** — you type a question, or paste text to rewrite.
2. **Middle** — the fine-tuned model, given a *neutral* system prompt (`"You are a helpful assistant."`).
   The voice lives entirely in the weights.
3. **Right** — the **same base model**, given a deliberately strong "write like Hemingway" prompt.
   No strawman: the prompt explicitly forbids choppy output and demands varied sentence length.
   The base model still can't do it — which is the point.

Every ⓘ popup in the UI shows the *actual* system prompt used per column, so anyone can verify
the fight was fair.

The prompting baseline's ceiling is structural: we tested three temperatures and a hardened
prompt, and the base 3B model maxed out at ~10-word sentences with variance ≈ 1.6 at every
setting. **You cannot prompt in a rhythm the model doesn't have.**

## Why this project exists

This is the public proof-of-concept for a service idea: **fine-tune a small model on a client's
own writing** (articles, emails, docs) so AI output carries *their* voice. Hemingway is the ideal
public demo because anyone can judge "does this sound like him?" — and because he's the
*conservative* case: his style is already all over pretraining data. A real client's voice is in
no model's pretraining at all. **So this demo is the floor, not the ceiling.**

## What's in the repo

```
├── the-sun-also-rises.txt        ← the 5-work public-domain corpus (Project Gutenberg)
├── farewell-to-arms.txt             (1923–1929 works, all US public domain)
├── in-our-time.txt
├── men-without-women.txt
├── three-short-stories-and-ten-poems.txt
├── clean/                         ← boilerplate-stripped corpus (01 runs on raw → here)
├── generations.json               ← the raw eval material: 100 held-out questions ×
│                                    {3 fine-tuned epochs + fair baseline + capability probes}
├── pipeline/
│   ├── 01–09_*.py                 ← the data pipeline: clean → mine passages → generate →
│   │                                 gates → dedup → assemble train/holdout
│   ├── gen_*.py                   ← per-bucket dataset generators (Gemini API)
│   ├── stylometry.py              ← sentence-rhythm metrics (the 5.92 vs 1.55 measurement)
│   ├── spine.py                   ← near-dup detection (5-gram Jaccard / union-find)
│   ├── fidelity_gate.py           ← rewrite-faithfulness gate
│   ├── train/Ernie_Train_Colab.ipynb  ← the turnkey Colab training notebook (free T4)
│   ├── train.jsonl                ← 1,187 training pairs (Qwen chat format)
│   ├── eval_holdout.jsonl         ← 100 held-out pairs (never seen in training)
│   └── eval/                      ← the eval harness + both judge reports + scorecards
└── demo/                          ← the 3-column compare (FastAPI proxy + single-page UI;
                                      runs local via Ollama or cloud via any OpenAI-compatible API)
```

## How the dataset was built (the actual work)

Training on raw novel text teaches a model to *continue novels* — ask it "how do I reset my
password?" and it writes a café scene. The core of this project is a **question → Hemingway-voice-
answer dataset**, assembled from four complementary buckets (~1,300 candidates → 1,187 train / 100 held out),
built with two complementary techniques:

- **Instruction back-translation** — real Hemingway passages become the *answers*; an LLM invents the matching user turn.
  - **Bucket 1 — Reflective Q&A.** Passages where a character reflects on war, love, loss, or courage are paired with the sincere human question each passage genuinely answers ("How do you get through hard times?") — never a reading-comprehension question *about* the passage.
  - **Bucket 2 — Description.** Real descriptive passages are paired with plain invented requests ("Describe the bulls coming out"), under strict anti-leak rules: the request may name the subject, but may not hand over any image the passage itself supplies.
- **Answer generation** — an LLM writes the Hemingway-voice answer to a given instruction.
  - **Bucket 3 — Style rewriting (the hero feature).** Neutral everyday text (emails, instructions, buzzword-laden corporate prose) flattened and rewritten in-voice. *The training prompt never mentions Hemingway* — so the model learned "rewrite in your own voice," not "do an impression."
  - **Bucket 4 — General instruction-following.** Questions and practical tasks seeded from [Databricks dolly-15k](https://huggingface.co/datasets/databricks/dolly-15k), answered in-voice, so the model stays a *general assistant* that happens to talk like Hemingway.

Quality was enforced by **gates, not vibes**: cadence/stylometry gates on every generated answer,
content-hash + 5-gram-Jaccard near-dup elimination across buckets, faithfulness gates on rewrites,
an 8-way parallel adversarial review pass that caught hallucinated facts and lazy pastiche
(29 flags → 5 worst offenders dropped), and a **group-stratified train/holdout split** that makes
train/eval leakage structurally impossible. Final tally: 0 exact dups, 0 near-dup pairs,
0 train/eval overlap — all recorded in `pipeline/assemble_report.json`.

## Training (a ~$0 run on a free Colab T4)

- **Base:** Qwen2.5-3B-Instruct (Apache-2.0) — an *instruct* model, so LoRA only has to shift voice, not teach Q&A from scratch.
- **Method:** QLoRA (4-bit) via Unsloth — r=16, alpha=16, all linear layers, LR 2e-4, seq-len 1024, loss masked to responses only.
- **Sweep:** 3 epochs with per-epoch checkpoints → one training run yields the 1/2/3-epoch comparison. Each epoch scored blind; epoch 3 won on voice while keeping capability (92% vs base's 100%, ±1 probe = noise).
- Everything is reproducible from `pipeline/train/Ernie_Train_Colab.ipynb` (~1 hour on a free T4).

## Evaluation ("looks good to me" is not an evaluation)

Four independent checks (`pipeline/eval/score_generations.py`):

1. **Blind LLM judge, stratified by task type** — fine-tuned vs baseline, A/B order randomized per row, with a **coherence gate** (an in-voice-but-incoherent answer cannot win). Verdicts cached per epoch so runs are resumable.
2. **An independent judge for the headline** — the in-house iteration judge was Gemini (same family as the generation engine). The client-facing number re-scores epoch 3 with **GPT-4o** to kill the "Google grading Google" objection. It scored *more conservatively* (73% vs 81%) — which is exactly what an honest outside grader should do.
3. **Stylometrics vs a real-Hemingway reference** — sentence-length mean/variance, fragment rate, long-sentence rate, conjunction rate, adverb rate (`stylometry.py`).
4. **Capability retention** — 12 off-distribution probes (math/code/facts/reasoning), base vs fine-tuned, as the catastrophic-forgetting tripwire. An epoch that wins on voice but forgets how to think is disqualified.

**Honest footnotes** (the kind we'd want a critical reviewer to find anyway):
- The three epochs come from one linear-decay LR run, so checkpoint comparison mildly favors epoch 3. A 12-point win isn't explained by annealing alone, but this isn't a paper — it's a demo with receipts.
- The "imitation" slice of the eval (48 items generated by the same LLM family that built the dataset) is circular and **discounted** in reporting; the headline is the 30 rewrite + 18 description items scored against *real* Hemingway targets.
- Ernie is a 3B model: it confabulates facts at high temperature and keeps answers short (all training answers were short, so "a Hemingway answer is short" got learned as a data property). The demo is framed around **voice**, not factual Q&A.

## Reproduce it

```text
1. Corpus     — the 5 .txt files are included (US public domain). python pipeline/01_clean_corpus.py
2. Dataset    — generation scripts call the Gemini API (free tier suffices); see pipeline/gen_*.py
3. Train      — upload pipeline/train.jsonl + eval_holdout.jsonl in Colab, run the notebook (free T4)
4. Evaluate   — python pipeline/eval/score_generations.py --in generations.json
5. Demo       — cd demo && ./run_demo.ps1  (needs Ollama + the merged model; or point the
                ERNIE_* / BASELINE_* env vars at any OpenAI-compatible endpoints — see demo/README.md)
```

## Data sources & licenses

- **Code:** MIT (see `LICENSE`).
- **Corpus:** the 5 works (1923–1929) are US public domain; texts via Project Gutenberg.
- **Base model:** Qwen2.5-3B-Instruct, Apache-2.0.
- **Dataset generation:** Google Gemini API; the Bucket 4 instruction seeds derive from
  [Databricks dolly-15k](https://huggingface.co/datasets/databricks/dolly-15k) (CC-BY-SA-3.0) —
  fetch it separately if regenerating (see `.gitignore`).
- **The trained model itself** lives in a private HuggingFace repo (the demo points at it); happy
  to share on request.

## What this project demonstrates

End-to-end ML engineering on a real constraint set: **corpus licensing diligence** (public-domain-only sourcing, a copyrighted work explicitly dropped), **dataset curation as the actual product** (dedup, leakage-proof splitting, adversarial review, style gates), **honest evaluation methodology** (blind + independent judging, stratification, coherence gating, capability retention), **cost discipline** (free-tier training and generation throughout), and **production serving** (FastAPI/SSE proxy, serverless GPU with scale-to-zero, cold-start handling, rate limiting).

---

*Built as the open showpiece of [Space Coast Labs](https://spacecoastlabs.com) — the same pipeline,
pointed at your own writing instead of Hemingway's, is the product.*
