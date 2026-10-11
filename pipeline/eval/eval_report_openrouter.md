# Ernie — M2 Eval Report

> **Judge:** `openrouter:openai/gpt-4o` — INDEPENDENT non-Gemini judge: this is the client-facing headline number.

> **How to read this:** the honest, generalizable proof is the **REAL-TEXT slice** (rewrite + description — targets are actual Hemingway). The practical-Q&A slice is Gemini imitation and is **discounted** (our own red-team called it circular). Reflective-Q&A is only 4 items — **anecdotal**, not a rate.

**Recommended model: EPOCH3** — chosen by real-text win-rate, subject to capability retention not collapsing.

## 1. Blind judge win-rate (fine-tuned vs. fair prompted baseline)

Win-rate = fine-tuned wins / decisive comparisons (ties excluded). Target > 70%.

| epoch | REAL-TEXT (lead) | practical (discounted) | overall | reflective (n=4) |
|---|---|---|---|---|
| epoch3 | **73%** (35-13-0) | 98% | 86% | 100% |

## 2. Stylometrics vs. real Hemingway (rhythm fingerprint)

Reference (real Hemingway, answer-sized chunks): mean sentence 12.1192w, variance 6.4595, fragment-rate 31%, long-rate 19%, 'and' 3%, -ly 1%.

| column | mean len | variance | frag-rate | long-rate | 'and' | -ly | dialogue |
|---|---|---|---|---|---|---|---|
| baseline (prompted) | 10.0563 | 1.5492 | 38% | 16% | 4% | 1% | 0% |
| epoch3 (fine-tuned) | 11.121 | 5.9183 | 26% | 18% | 6% | 0% | 0% |

## 3. Capability retention (off-distribution: facts / math / code / reasoning)

Did training cost the model basic ability? (base vs. fine-tuned, neutral prompt both.)

- base model: **100%** (12/12)
- epoch3: **92%** (11/12)

⚠ Probes the base model passed but some epoch FAILED (forgetting): math_mul

---
*Judged by `openrouter:openai/gpt-4o`, fully independent of both the model under test (Qwen) and the iteration-loop judge (Gemini). This IS the client-facing headline number.*
