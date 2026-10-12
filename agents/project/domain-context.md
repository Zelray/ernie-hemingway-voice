# Ernie domain context

Verified facts and limitations. New facts follow M5. Historical decisions are in project-decisions.md; current source and upstream license evidence take precedence over old assumptions.

## Dataset and evaluation

- Four buckets produce 1,187 training rows and 100 held-out rows. Buckets 1–3 use real source answers; Bucket 4 supplies generated imitation. Assembly groups near-duplicate answers before choosing the holdout. (c533a5a)
- Training system messages are neutral. Bucket 3 user messages use neutral rewrite instructions; inference uses the same task shape. The baseline receives an explicit Hemingway style prompt. (c533a5a)
- The evaluator reports rewrite and description as real_text, practical_qa as imitation, and reflective_qa separately. The stored independent epoch3 scorecard records 35 wins and 13 losses on real-text comparisons; this is 72.92%, rounded to 73%. (c533a5a)
- stdev_len is population standard deviation of sentence length in words. It is not variance. The public description corrected this terminology. (6286ea8)
- Rhythm consumers share stylometry. The mining splitter serves passage mining and is outside that measurement contract. (c533a5a)
- Fidelity is heuristic. Without a wordlist its garble detector is disabled; cardinal and person checks still run. An offline test must not pretend a missing dictionary establishes garble coverage. (c533a5a)

## Training and serving

- QLoRA uses 4-bit loading, rank 16, alpha 16, the seven configured linear projections, learning rate 2e-4, sequence length 1024, and three epochs with saved checkpoints. Training dependencies live in the Colab notebook. (c533a5a)
- The notebook builder writes the notebook at import time. Gates inspect its declarative constants through AST parsing; they never import it. All 13 cell sources must match. (c533a5a)
- Some generator modules read a local API key at import. Offline gates parse their syntax and inspect calls without importing them. The evaluator's --dry option writes caches and reports, so it is not an offline verification command. (c533a5a)
- New generation scripts call the shared Gemini client in pipeline/gemini_client.py. The five historical generators keep their inlined copies and still read the key at import. (3357af9)
- The browser calls only the local proxy. Endpoint URLs and inference keys stay on the server. The proxy supports local and cloud endpoints. (c533a5a)

## Model license correction

The earlier Apache-2.0 description of Qwen2.5-3B-Instruct is incorrect. Its upstream LICENSE is the Qwen Research License Agreement, which grants research/evaluation use and requires requesting a license for commercial use. Verified on 2026-10-12 against https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/raw/main/LICENSE. The code's MIT license does not change model rights. The README still contains the older claim; correction is a separate documented issue. (514f761)

## Business evidence

The Hemingway demo establishes this pipeline's measured result on these tasks. It does not establish successful voice capture for a thin-data client. The separate client-simulation proof remains required before general service claims. Public corpus status is a US-specific decision; check rights for other jurisdictions. (c533a5a)
