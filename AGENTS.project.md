# Ernie project instructions

Read `AGENTS.md` first. Contracts, project rules, verification, playbooks.
The sanctioned path is the only path; a bypass is a bug even when it works.

## Architecture contracts

### D1 Dataset integrity
Owns: content hashing, span claims, final answer deduplication and whole-group holdout selection.
Path: `content_hash`, `SpanRegistry`, `append_record`, `load_done_ids` in `pipeline/spine.py`; `exact_dedup`, `near_dup_groups`, `pick_holdout`, `chatml` in `pipeline/09_assemble.py`.
Never: replace shared hashing or span-claim helpers in final consumers; split a near-duplicate group between train and evaluation; add voice instructions to the training system turn.
Gate: `tests/test_instruction_gate.py`, `tests/test_pipeline.py`; review representative sampling and factual source provenance.

### D2 Cadence
Owns: sentence rhythm for reference construction, Bucket 4 checking and evaluation.
Path: `split_sentences`, `style_metrics`, `chunk_text` in `pipeline/stylometry.py`; `cadence_check` in `pipeline/bucket4_cadence_gate.py`.
Never: define replacement rhythm helpers in the reference builder, cadence checker or evaluator. The mining splitter has a different concern.
Gate: `tests/test_instruction_gate.py`, `tests/test_pipeline.py`; review on-topic answers and word-level pastiche.

### D3 Final rewrite fidelity
Owns: mechanical fidelity acceptance for final Bucket 3 generation and validation.
Path: `fidelity_gate`, `normalize_quotes` in `pipeline/fidelity_gate.py`.
Never: define a local fidelity gate in final Bucket 3 generators or acceptance. The historical dress rehearsal is exempt.
Gate: `tests/test_instruction_gate.py`, `tests/test_pipeline.py`; review full factual equivalence and dictionary coverage.

### D4 Evaluation counting
Owns: blind answer assignment, coherence-gated wins, task slices and capability scoring.
Path: `ab_assignment`, `tally`, `TASK_GROUP`, `score_capability` in `pipeline/eval/score_generations.py`.
Never: count an incoherent or degenerate fine-tuned winner as a win; classify practical imitation as real-text evidence.
Gate: `tests/test_pipeline.py`; review judge independence, cache identity and the capability recommendation fallback recorded in the out-of-scope ledger.

### D5 Demo proxy
Owns: inference endpoint configuration, server-held credentials and prompt disclosure.
Path: `TARGETS`, `stream`, `info`, `build_user_message` in `demo/server.py`.
Never: send inference keys or upstream endpoint URLs to browser requests; style the fine-tuned column through its system prompt; omit the style prompt from the baseline.
Gate: `tests/test_instruction_gate.py`, `tests/test_demo.py`; review model lineage, baseline fairness, request validation and streaming recovery.

### D6 Notebook generation
Owns: training notebook cell types, order and source.
Path: `cells`, `to_lines` in `pipeline/train/build_notebook.py`; output `pipeline/train/Ernie_Train_Colab.ipynb`.
Never: hand-edit notebook cells independently of their builder.
Gate: `tests/test_instruction_gate.py` compares all generated cells without importing the writer; review training-method and prompt validity.

### D7 Gemini client
Owns: Gemini endpoint call, key handling, retry/backoff, `[ERROR ...]` tagging, inter-call pacing.
Path: `load_key`, `GeminiClient` in `pipeline/gemini_client.py`; `tests/test_gemini_client.py`.
Never: define a local retry/backoff Gemini `generate()` in a new run script; read the API key at import time.
Gate: `tests/test_gemini_client.py`; review.

## Project rules

- R1. Run commands from the repo root. Run `git config core.hooksPath .githooks` once per clone. Gate: review; CI reruns gates.
- R2. Prose people read is written with the slop-mop skill; prose reviews use its detect mode on the harness's top coding model. Gate: review.
- R3. UI behavior or navigation changes need an outcome-based end-to-end test. Cosmetic changes use existing gates. Gate: review until a browser runner is added; static control labels are counted by `scripts/ratchet.py`.
- R4. A feat PR links its spec or explains why none is needed in ## Spec. PR acceptance lines must have content. Gate: `scripts/pr_body_check.py` in pr-acceptance CI.
- R5. Agent GitHub comments end with Posted by <agent>, assisting @Zelray. Gate: review.
- R6. Obtain explicit approval for spending money, changing a live system or an operation hard to undo. Unrelated production systems are off limits. Gate: review.
- R7. General client-service claims require a separate blind test on an obscure writer with thin data. Flag choices that do not transfer to client-owned writing. Gate: review.
- R8. Challenge premises, correct misconceptions and surface material risks early. Substantive ambiguous decisions receive independent agent review or debate; record assumptions and report the synthesis. Settled decisions change only with new evidence. Gate: review.
- R9. Use scripts for bulk cleaning and assembly; use models for semantic generation. Gate: review.
- R10. Use only the five approved public-domain source texts for this demo. Exclude the copyrighted 1952 work. Gate: `tests/test_instruction_gate.py`; review jurisdiction and provenance.
- R11. Model success claims require evaluated artifacts and more than 70% wins on decisive real-text comparisons against the prompted baseline. Capability retention and evidence scope require review. Gate: review; stored scorecards are evidence, not automatic release authorization.
- R12. Keep secrets, model weights and private operational notes out of public files. Gate: `tests/test_instruction_gate.py`; review private prose and releases.
- R13. Verify the exact base-model license before commercial use. The current 3B model uses the Qwen Research License; the earlier Apache claim was incorrect. Gate: review.

## Verification

```text
python scripts/gates.py         # pytest, syntax, lint/quality ratchet, mutation smoke
make gates                     # same command when make is installed
python -m pytest -q
python scripts/ratchet.py       # Ruff JSON, strict new-file lint, quality counts
python scripts/mutation_smoke.py
```

Per commit, run the applicable checks; run the full set before push or PR (P3).
Lower ratchet counts with `python scripts/ratchet.py --update`, which refuses rises.
Raising a baseline is a hand edit with a reason in the commit message (C7).
CI also runs `python scripts/proven_red.py <base> <head>` and pr-acceptance.
State completed checks in the handoff. Offline checks require no keys or model services.

## Playbooks

| Work | Read first |
|---|---|
| Multi-agent or long-running work | `agents/generic/agent-workflows.md` |
| Naming, briefs, proposing work | `agents/project/glossary.md`, `agents/project/out-of-scope.md` |
| Tests, UI or platform checks | `agents/project/testing.md` |
| Developer or user documentation | `agents/project/documentation.md` |
| Pipeline, training, evaluation, serving | `agents/project/domain-context.md`, `agents/project/project-decisions.md` |
