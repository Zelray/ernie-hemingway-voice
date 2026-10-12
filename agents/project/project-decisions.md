# Preserved project decisions

Safe technical excerpts from the original local CLAUDE.md (2026-06-27), preserved at clause boundaries. These record the kickoff; domain-context.md describes the verified implementation. Private profile and infrastructure context is omitted. Quotes retain original wording.

## Purpose and scope

> Hemingway is the **demo, not the product**. The product is: *"give us your articles and emails; we'll train an AI that writes in YOUR voice."*

Status: intended service. Thin-data client validation remains required; the Hemingway result alone does not establish it.

> Every technical choice must generalize — swap the Hemingway corpus for a client corpus and the pipeline still works. If a decision helps Hemingway but wouldn't help a real client, flag it.

Status: project rule R7 owns transfer limitations.

> A separate visual-model project comes later; out of scope for now.

Status: deferred scope.

> The productized per-client version is the **"[Client]-fier"**

> Working name, not chiseled in stone.

Status: provisional naming. Public demo names are Ernie, Ernifier and Ernestifier.

## Corpus

> **Corpus = 5 public-domain .txt works:** The Sun Also Rises (1926), A Farewell to Arms (1929), In Our Time (1924 Paris ed.), Men Without Women (1927), Three Stories & Ten Poems (1923). All solidly US public domain in 2026 (95-yr term). All from Project Gutenberg (uniform legal header + license footer to strip).

Status: current US corpus selection. The cleaner owns the approved file list; other jurisdictions require review.

> **DROP `oldmansea.pdf` (The Old Man and the Sea, 1952)** — under US copyright until 2048, and a PDF-extraction hassle. 5 works is plenty of corpus.

Status: current exclusion. The absent file is not a sanctioned input.

> the file on hand is the short **1924 Paris edition** (~538 lines, just the experimental vignettes), confirmed by its title page — NOT the fuller **1925** collection (Indian Camp, Big Two-Hearted River, …). Both are public domain.

Status: edition distinction remains current; the old line-count estimate is superseded by 919 raw and 529 cleaned lines. Public-domain statement is US-specific.

> consider sourcing the 1925 edition later for breadth. Not blocking — the other 4 works carry the corpus.

Status: deferred expansion.

## Dataset

> Training on raw novel text teaches the model to *continue prose*, not *answer questions*. Ask a raw-prose-trained model "how do I reset my password?" and it writes a café scene.

Status: rationale and illustrative hypothetical, not a recorded experiment.

> We must build an **instruction→Hemingway-voice dataset** of ~800–1,500 Q&A pairs

> *Style-rewrite pairs (primary):* take a standard instruction set (e.g., an Alpaca/Dolly slice), rewrite the **answers** into Hemingway's voice with a strong LLM.

> *Instruction back-translation (supplement):* take real Hemingway dialogue/first-person passages as the answers, have an LLM invent the matching question. ~60/40 rewrite/back-translation blend. Hold out ~100 pairs for eval. Use the model's chat template.

Status: original design superseded by four buckets (20 reflective, 228 description, 362 flatten-restore, 677 practical), 1,187 training and 100 held-out rows. Dolly seeds are used; Alpaca was an option. Buckets 1–3 retain original source answers; only Bucket 4 generates imitation answers. The holdout and chat-template requirements remain active.

## Model and training

> **Base model = INSTRUCT, not raw base** (it must already answer; LoRA only shifts voice — it can't teach Q&A from scratch on tiny data).

> Primary: **Qwen2.5-3B-Instruct** (Apache-2.0 — cleanest license for resale).

Status: selected instruct model remains current. **The Apache-2.0 and resale rationale are incorrect.** Upstream uses the Qwen Research License with commercial-use licensing requirements; see domain-context.md. This quote must never be used as clearance.

> Alt: Llama-3.2-3B-Instruct / Llama-3.2-1B-Instruct. Start at 3B for demo quality; 1B optional later for a starker contrast.

Status: unselected alternatives and deferred 1B experiment. Alternative licenses were not verified in setup.

> **Method = QLoRA (4-bit) via Unsloth**, NOT full fine-tune. Few epochs (2–3), modest LoRA rank (r≈16, alpha≈16 on all linear layers), LR ≈ 2e-4, seq-len ≈ 1024. Overfitting tiny data is the #1 quality killer (too many epochs / rank too high → it parrots memorized lines and breaks Q&A).

Status: current configuration is three epochs; overfitting statement is risk rationale.

> **Compute = train on free Google Colab T4 (16GB); serve the demo locally.**

> Expected train time on T4: 1B ≈ 15–30 min, 3B ≈ 45–90 min, ≈ $0.

Status: original estimates. Free availability is conditional; serving supports local or cloud endpoints.

> **$10 RunPod (e.g., A5000 ~$0.50/hr) is an optional upgrade**

Status: dated estimate, not current pricing or spend authorization. R6 owns approvals.

> **Data prep runs LOCALLY (CPU), free.** Cleaning + dataset assembly need no GPU and no cloud.

> Only the training step needs Colab.

Status: offline cleaning/assembly remains current. Generation APIs and optional cloud serving are separate external operations.

> The dataset-*generation* step (rewriting into Hemingway voice) calls a strong LLM ~1,000×

Status: original estimate, not exact implemented call count.

## Evaluation and business proof

> **Evaluation (mandatory — "looks good to me" is not eval):** (a) **stylometrics** vs a real-Hemingway reference (sentence-length mean/variance, -ly adverb rate, passive-voice rate, parataxis, dialogue density) using spaCy + textstat; (b) **blind LLM-judge** doing randomized pairwise comparison on held-out questions ("more Hemingway AND still a good answer?"), target **>70% win** vs the prompted baseline; (c) a **coherence gate** so choppy gibberish or merely-shorter text can't "win."

Status: implementation uses the custom stylometry splitter, population standard deviation, suffix and conjunction proxies and quote-containing sentence rate. spaCy/textstat and passive-voice measurement are not implemented. Blind/coherence-gated scoring and the >70% real-text target remain active.

> Hemingway is the **conservative case for "fine-tuning beats prompting."** His style is unusually prompt-imitable, so the middle-vs-right gap may look *small*.

> a real client whose voice is in NO model's pretraining and is NOT reducible to a few rules.

> "the demo is the floor, not the ceiling."

Status: historical hypotheses and positioning. They are not established claims about unseen clients or pretraining membership.

> Hemingway's unique value = shared evaluability: anyone can judge "does this sound like Hemingway?"; only a client can judge "does this sound like me." Ideal for a public demo.

Status: demo-selection rationale.

> The business proof is a SEPARATE test (M4): a real client = little data (a few thousand words of email), unknown voice, not in pretraining. Before staking the service on this, run the SAME pipeline on an obscure, thin-data writer with blind scoring. If voice-capture fails on thin data, the service doesn't exist yet.

Status: uncompleted business acceptance test. Obscurity and likely lack of pretraining exposure are test-selection assumptions to document.

## Preparation boundaries

> Code chews the bulk data; the model only sees small summaries. Cleaning/parsing novels is done by scripts running outside the model's context — it costs ~zero tokens. Reach for a model only when the job needs understanding (e.g., rewriting into Hemingway's voice).

> The training run does NOT clean, OCR, or fix your data; it just learns patterns from whatever examples you feed it. So data prep is the most important part of the project; the training run itself is the comparatively easy, mechanical part.

> **No OCR/extraction needed for Hemingway** — the files are already clean digital text. (OCR/extraction/markdown models like Docling/Marker are for messy documents.)

> real clients will hand over messy PDFs, Word docs, scanned letters, email exports — that's exactly where small extraction/markdown tools (Docling, Marker, etc.) become a real module of the service, converting client junk into clean text before the pipeline.

Status: mechanical/semantic boundary remains current. Messy-document ingestion is deferred.

## Original generation alternatives

> free Gemini API (Google AI Studio free tier — $0, strong enough)

> a paid API (OpenAI/Anthropic/OpenRouter — a few dollars, highest quality)

> run a bigger open model on Colab to generate ($0, fiddlier)

Status: historical options and estimates, not quality benchmarks or current budgets. Gemini was selected in the implemented generators. The obsolete local CLI tooling option is accounted for in the migration ledger and is not a verification command.

## Additional historical record

These excerpts resolve M01–M10 in the migration ledger. Source line numbers refer to the original 90-line record. Status notes distinguish current requirements, obsolete decisions and unproved hypotheses. The original kickoff record is the source for the verdicts below; this preservation adds no independent evidence.

### M01: local handoff role

Original lines 3, 82 and 90:

> Project memory. Read this first, then read `HANDOFF.md` for the live state and the next action.

> `CLAUDE.md` (this file), `HANDOFF.md` (live state + next action).

> **Next action is in `HANDOFF.md`.**

Status: current handoff role. After the current instruction load order, read the private, ignored `HANDOFF.md` when it is locally present for live state and the next action. Keep its private operational content out of public documents. The original CLAUDE-first wording is obsolete; `AGENTS.md` and `AGENTS.project.md` own the current load order.

### M02: comparison layout

Original lines 36–39; also referenced in lines 13 and 69:

> 3-column compare UI:
> 1. **Left** — user types a question.
> 2. **Middle** — the **fine-tuned** model answers in Hemingway's voice.
> 3. **Right** — the **same base model**, given an **honest "write like Hemingway" prompt** — a FAIR fight, never a handicapped no-prompt baseline. A rigged win is worthless and a skeptical client sees through it instantly.

Status: current comparison design. D5 owns model lineage and baseline fairness. This excerpt preserves the question, fine-tuned answer and prompted-baseline column arrangement; it reports no measured win.

### M03: premise review and synthesis

Original lines 28–29:

> Pressure-test every premise, correct misconceptions directly, name risks early.

> On any substantive/ambiguous call, convene a multi-agent debate (per global rules) and synthesize back.

Status: current obligations are in R8. It requires premise challenge, misconception correction, early risk disclosure, recorded assumptions and reported synthesis. Independent agent review or debate is the current sanctioned path for substantive ambiguous decisions. The original debate-only wording is obsolete.

### M04: recorded kickoff verdict

Original line 33:

> **Green light.** As a way to *learn fine-tuning*: near-perfect first project (small model, distinctive style, $0, real-world pipeline).

Status: historical verdict attributed to the original kickoff record. The small model, distinctive voice, free starting path and practical pipeline were its learning rationale. "Near-perfect" is the record's judgment, unproved as a comparison with other learning projects. The cost estimate is obsolete as a guarantee. This excerpt establishes neither client performance nor a new independent review.

### M05: easy-case hypotheses

Original line 33:

> Hemingway is the EASY case (saturated in pretraining, near-formulaic style)

Status: unproved historical hypotheses. The record supplies no model-specific pretraining evidence or comparative test of style difficulty. Prompt imitability does not establish either claim. R7 still requires a separate blind client-simulation test on an obscure writer with thin data before general service claims.

### M06: short-edition rationale

Original line 44:

> The 1924 vignettes are concentrated style but thin;

Status: historical editorial rationale, unproved as a predictor of training quality. The 1924 edition remains the current selected input. The optional 1925 expansion remains deferred for breadth; the other four works were the recorded reason it was nonblocking.

### M07: unseen-client forecast

Original line 55:

> That's fine — it means the demo **understates** what we'll do for a real client whose voice is in NO model's pretraining and is NOT reducible to a few rules.

Status: unproved historical performance forecast. The record provides no evidence that unseen-client results will exceed the demo, or that a client's voice is absent from all model pretraining. The separate blind, thin-data client simulation remains required under R7. The "floor, not the ceiling" positioning above cannot substitute for that test.

### M08: original generation recommendation

Original line 74:

> Recommend starting (a) free Gemini. Decide before M1 Step 3.

Status: obsolete open-decision recommendation. Gemini was later selected in the implemented generators. The original free-tier and quality estimates establish no current availability, budget or benchmark. R6 governs spending approval.

### M09: cleaner inventory

Original line 81:

> `pipeline/01_clean_corpus.py` — Step 1 cleaner: strips Gutenberg boilerplate from the 5 .txt, writes `clean/*_clean.txt`, prints per-file word counts.

Status: current script and output description, verified by `RAW_FILES`, `strip_gutenberg` and `main` in the cleaner. This excerpt excludes the original transient execution state. It does not report a new cleaner run.

### M10: recorded kickoff review

Original line 90:

> Kickoff debate run (AI Engineer + Reality Checker + advisor) — all converged on PROCEED-WITH-CHANGES, changes incorporated.

Status: historical event attributed to the original kickoff record. It records the review roles, conclusion and reported incorporation of changes. No independent review transcript or itemized change list is supplied here. M04 preserves the learning verdict; the earlier dataset, baseline, evaluation and client-proof sections preserve the technical approach recorded at kickoff. This excerpt is not fresh proof of their results.
