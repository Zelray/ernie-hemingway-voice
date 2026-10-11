# Ernie — M2 Eval Report

> **Judge:** `gemini` — $0 iteration loop (not the final headline).

> **How to read this:** the honest, generalizable proof is the **REAL-TEXT slice** (rewrite + description — targets are actual Hemingway). The practical-Q&A slice is Gemini imitation and is **discounted** (our own red-team called it circular). Reflective-Q&A is only 4 items — **anecdotal**, not a rate.

**Recommended model: EPOCH3** — chosen by real-text win-rate, subject to capability retention not collapsing.

## 1. Blind judge win-rate (fine-tuned vs. fair prompted baseline)

Win-rate = fine-tuned wins / decisive comparisons (ties excluded). Target > 70%.

| epoch | REAL-TEXT (lead) | practical (discounted) | overall | reflective (n=4) |
|---|---|---|---|---|
| epoch1 | **67%** (32-16-0) | 83% | 76% | 100% |
| epoch2 | **69%** (33-15-0) | 92% | 81% | 100% |
| epoch3 | **81%** (39-9-0) | 90% | 86% | 100% |

## 2. Stylometrics vs. real Hemingway (rhythm fingerprint)

Reference (real Hemingway, answer-sized chunks): mean sentence 12.1192w, variance 6.4595, fragment-rate 31%, long-rate 19%, 'and' 3%, -ly 1%.

| column | mean len | variance | frag-rate | long-rate | 'and' | -ly | dialogue |
|---|---|---|---|---|---|---|---|
| baseline (prompted) | 10.0563 | 1.5492 | 38% | 16% | 4% | 1% | 0% |
| epoch1 (fine-tuned) | 9.6005 | 4.6697 | 31% | 11% | 5% | 0% | 0% |
| epoch2 (fine-tuned) | 13.7324 | 6.6417 | 27% | 19% | 6% | 0% | 0% |
| epoch3 (fine-tuned) | 11.121 | 5.9183 | 26% | 18% | 6% | 0% | 0% |

## 3. Capability retention (off-distribution: facts / math / code / reasoning)

Did training cost the model basic ability? (base vs. fine-tuned, neutral prompt both.)

- base model: **100%** (12/12)
- epoch1: **92%** (11/12)
- epoch2: **83%** (10/12)
- epoch3: **92%** (11/12)

⚠ Probes the base model passed but some epoch FAILED (forgetting): math_mul, math_pct, reason_order

---
*This loop's judge is Gemini ($0). The client-facing headline number is re-judged by an INDEPENDENT non-Gemini model (see eval_report_openrouter.md).*
