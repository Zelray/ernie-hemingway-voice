# Instruction migration

Audit of the 90-line original CLAUDE source against the current migration. Source references below mean original lines, not the replacement CLAUDE.md. Descriptions omit private specifics. Historical excerpts establish preservation, not current correctness or authorization. The appended historical record resolves the ten reported omissions and attributes kickoff verdicts to the original record.

Counts: 153 source rows covering all 90 lines; 7 contract, 20 project rule, 70 playbook, 33 duplicate, 23 dropped. Framework inventory: 6 contracts and 13 project rules. Reported omissions: 10 resolved, 0 unresolved.

Destination keys: AP = `AGENTS.project.md`; CORE = `AGENTS.md`; DEC = `agents/project/project-decisions.md`; DOMAIN = `agents/project/domain-context.md`; DOC = `agents/project/documentation.md`; GLOSS = `agents/project/glossary.md`; OOS = `agents/project/out-of-scope.md`; WORK = `agents/generic/agent-workflows.md`. Numbers after keys are destination line numbers. DEC M01–M10 refer to the appended sections linked in the resolution table below. Gate keys: IG = `tests/test_instruction_gate.py`; PIPE = `tests/test_pipeline.py`; DEMO = `tests/test_demo.py`. `review` means human/agent judgment, not automated enforcement. `none (history)` means advisory preservation only.

| Original line | Safe rule/fact description | Disposition | Actual destination + gate |
|---|---|---|---|
| 1–2, 4–5, 7, 9, 11–12, 14–15, 17, 19–20, 25–26, 31–32, 34–35, 40–41, 53–54, 58–59, 64–65, 72–73, 77–78, 83–84, 88–89 | Headings, whitespace, dated section labels | dropped | No destination; none. Private heading context omitted. |
| 3 | Original startup order and live-state handoff pointer | playbook | DEC M01; current startup order CORE:3, CLAUDE.md:1. Read private ignored HANDOFF.md when locally present for live state and next action; privacy review under AP R12. Original startup order obsolete. |
| 6 | Private personal circumstances | dropped | No public destination; privacy, CORE M5 / AP R12; IG + review. |
| 6 | Private effort and prior budget context | dropped | No public destination; AP R6 requires explicit approval; review. No inherited spend authorization. |
| 6 | Finish a usable result with rigor | project rule | CORE P7:47, I3:24; review. Absolute success rhetoric dropped. |
| 8 | Private professional profile and venture context | dropped | No public destination; CORE M5 / AP R12; IG + review. |
| 8 | Unrelated production system is protected | project rule | AP R6:51; review. Private identifiers omitted. |
| 10 | Private wellbeing context and response preference | dropped | No public destination; CORE M5 / AP R12; IG + review. |
| 13 | Small open model, 1–3B scale | playbook | DEC:65; none (history). Scale also implicit in named model alternatives. |
| 13 | Public-domain Hemingway answers in the author's voice | playbook | DEC:27,49,59; none (history); corpus restriction AP R10 / IG + review. |
| 13 | Three-column comparison UI | playbook | DEC M02; question left, fine-tuned answer middle, prompted baseline right; AP D5 fairness review. |
| 13 | Demo supports a service trained on client-owned writing | playbook | DEC:7–9; DOMAIN:27; AP R7 / review. |
| 16 | Hemingway demo and intended client-writing service are distinct | duplicate | Original 13; DEC:7–9; AP R7 / review. |
| 16 | Technical choices must transfer to replacement client corpora | project rule | AP R7:52; DEC:11–13; review. |
| 16 | Flag choices that help only this demo | duplicate | Same line's transfer rule; AP R7:52; review. |
| 16 | Separate visual-model project is deferred | playbook | DEC:15–17; OOS:16; none (history/scope). |
| 18 | Demo name and established aliases | playbook | GLOSS:23; DEC:23; review of terminology. |
| 18 | Public showpiece sells the service concept | duplicate | Original 13,16; DEC:7–9; AP R7 / review. |
| 18 | Provisional per-client naming pattern | playbook | GLOSS:23; DEC:19–23; review of terminology. Private illustrative name omitted. |
| 21 | Private owner profile and learning/communication needs | dropped | No public destination; CORE M5 / AP R12; IG + review. |
| 21 | Plain explanation without dense code review dumps | playbook | DOC:15; CORE P10:51; review. Public colleague-facing style retained; owner-specific framing omitted. |
| 22 | Private owner/agent role allocation and prior-role contrast | dropped | No public destination; CORE M5 / AP R12; IG + review. |
| 23 | Owner-specific code-contribution and decision preferences | dropped | No public destination; CORE M5 / AP R12; IG + review. |
| 23 | Owner-specific teaching callout format | dropped | No public destination; CORE M5 / AP R12; review. |
| 23 | Define code-specific terms at first use | playbook | DOC:15; AP R2 / review. Exact one-sentence limit not retained. |
| 24 | Owner-specific pace and depth preference | dropped | No public destination; CORE M5 / AP R12; review. |
| 24 | Complete the thin-data client-simulation proof | duplicate | Original 16,33,57; AP R7:52; review. |
| 27 | Private quotation requesting pushback | dropped | No public destination; CORE M5 / AP R12; review. |
| 28 | Pressure-test premises and correct misconceptions | project rule | AP R8:53 explicitly requires both; DEC M03 retains original wording; review. |
| 28 | Surface material risks early | project rule | AP R8:53 explicitly includes early disclosure; DEC M03; review. |
| 29 | Debate substantive ambiguous decisions and report synthesis | project rule | AP R8:53 requires independent agent review or debate, recorded assumptions and reported synthesis; DEC M03 labels debate-only wording obsolete; review. |
| 30 | Owner-specific recommendation and choice-presentation preference | dropped | No public destination; CORE M5 / AP R12; review. |
| 30 | Make assumptions visible | project rule | AP R8:53; review. |
| 30 | Explicit approval before spending money | project rule | AP R6:51; review. |
| 30 | Explicit approval before changing live systems | project rule | AP R6:51; review. |
| 30 | Explicit approval before operations hard to undo | project rule | AP R6:51; review. |
| 33 | Kickoff proceed verdict and learning-project rationale | playbook | DEC M04; verdict attributed to original record, comparison unproved and cost guarantee obsolete; none (history). |
| 33 | Hemingway is unusually easy to imitate by prompting | playbook | DEC:99,105; none (historical hypothesis). |
| 33 | Pretraining saturation as an easy-case rationale | playbook | DEC M05; unproved historical hypothesis, no model-specific membership evidence; AP R7 client simulation required; none (history). |
| 33 | Near-formulaic style as an easy-case rationale | playbook | DEC M05; unproved historical hypothesis, no comparative difficulty test; AP R7 client simulation required; none (history). |
| 33 | Publicly judgeable sales-demo rationale | duplicate | Original 56; DEC:107–109; none (history). |
| 33 | Demo mechanics do not establish thin-data client success | project rule | AP R7:52; DOMAIN:27; review. |
| 33 | Validate clients separately before selling the general service | duplicate | Original 16; AP R7:52; DEC:111–113; review. |
| 36–38 | Left question column and middle fine-tuned answer column | duplicate | Original 13; DEC M02 preserves layout; AP D5 covers prompts/proxy. |
| 39 | Right column uses the same base model | contract | AP D5:32–36; model-lineage/baseline-fairness review. DEC M02 preserves right-column layout. |
| 39 | Honest explicit style prompt for baseline | contract | AP D5:35–36; DOMAIN:8; DEMO checks prompt disclosure; fairness review. |
| 39 | Do not handicap baseline with no style instruction | duplicate | Same line's prompt rule; AP D5:35–36; DEMO + review. |
| 41 | Settled technical decisions need new evidence to change | project rule | AP R8:53; review. Section label carries this rule. |
| 42 | Five approved titles, years and edition | project rule | AP R10:55; DEC:27; IG checks exact five-file allowlist; rights/provenance review. |
| 42 | US public-domain basis and dated term claim | playbook | DEC:27–29; DOMAIN:27; AP R10 / jurisdiction review. IG does not determine legal rights. |
| 42 | Gutenberg source and removable header/footer | playbook | DEC:27; none (history); AP R10 / provenance review. |
| 43 | Exclude copyrighted 1952 work | project rule | AP R10:55; DEC:31–33; IG checks exclusion; rights review. |
| 43 | Dated copyright-expiry claim | playbook | DEC:31; none (history); jurisdiction review under AP R10. |
| 43 | Extraction burden and sufficient existing corpus | playbook | DEC:31; none (history). |
| 44 | Short 1924 edition identified from title page | playbook | DEC:35–37; none (history). |
| 44 | Dated approximate line count | playbook | DEC:35–37; none (history); labeled superseded with raw/clean counts. |
| 44 | Distinction from fuller 1925 collection and example stories | playbook | DEC:35–37; none (history). |
| 44 | Both editions' US public-domain status | playbook | DEC:35–37; AP R10 / jurisdiction review. |
| 44 | Concentrated style but limited breadth of short vignettes | playbook | DEC M06; historical editorial rationale, training-quality prediction unproved; none (history). |
| 44 | Optional 1925 expansion is nonblocking; other four carry corpus | playbook | DEC:39–41; OOS:16; none (history/scope). |
| 45 | Raw prose teaches continuation rather than instruction answering | playbook | DEC:45–47; none (historical rationale). Illustrative failure is labeled hypothetical. |
| 45 | Original 800–1,500 instruction/voice-pair target | playbook | DEC:49,55; DOMAIN:7; none (history); four-bucket design supersedes original plan. |
| 46 | Strong model rewrites answers from standard instruction seeds | playbook | DEC:51,55; none (history); original primary-rewrite design superseded. |
| 46 | Alpaca/Dolly seed options | playbook | DEC:51,55; none (history); Dolly selected, Alpaca only an option. |
| 47 | Invent questions for real dialogue/first-person answers | playbook | DEC:53,55; none (history); source-answer approach preserved. |
| 47 | Original 60/40 rewrite/back-translation blend | playbook | DEC:53,55; none (history); explicitly superseded by four buckets. |
| 47 | Approximately 100 evaluation holdouts | contract | AP D1:8–12; DEC:53–55; DOMAIN:7; PIPE checks whole-group holdout, not fixed total; count review. |
| 47 | Use the model's chat template | playbook | DEC:53–55; GLOSS:33; review. AP D1 names chatml, but gates do not prove tokenizer-template equivalence. |
| 48 | Instruct model is required to preserve question answering | playbook | DEC:59,63; none (history); training validity review under AP D6. |
| 48 | Selected Qwen2.5-3B-Instruct model | playbook | DEC:61–63; none (history); AP R13 license review. |
| 48 | Incorrect Apache/resale claim | project rule | AP R13:58; DOMAIN:21–23; DEC:61–63; review. Exact historical quote retained with correction, never commercial clearance. |
| 48 | Alternate Llama instruct models | playbook | DEC:65–67; none (history); licenses explicitly unverified. |
| 48 | Start at 3B; optional 1B contrast later | playbook | DEC:65–67; OOS:16; none (history/scope). |
| 49 | QLoRA, 4-bit loading, Unsloth, no full fine-tune | playbook | DEC:69–71; DOMAIN:16; AP D6 / training-method review. IG checks notebook derivation, not training method. |
| 49 | Two to three epochs | playbook | DEC:69–71; DOMAIN:16; none (history); current three epochs stated. |
| 49 | Rank 16 and alpha 16 on linear layers | playbook | DEC:69; DOMAIN:16; training configuration review under AP D6. |
| 49 | Learning rate 2e-4 and sequence length 1024 | playbook | DEC:69; DOMAIN:16; training configuration review under AP D6. |
| 49 | Tiny-data overfitting risk, memorization and broken answers | playbook | DEC:69–71; none (historical risk rationale); AP R8 / review. |
| 50 | Free Colab T4 16GB training and local serving plan | playbook | DEC:73–77; none (history); free availability conditional; DOMAIN:19 allows cloud serving. |
| 50 | Private workstation capacity and platform context | dropped | No public destination; CORE M5 / AP R12; IG + review. |
| 50 | Dated local terminal problem and workaround | dropped | Transient private environment state; no public destination; none. |
| 50 | Dated 1B/3B training-time and cost estimates | playbook | DEC:75–77; none (history); not current guarantees. |
| 50 | Optional paid-compute budget and hardware/rate estimate | playbook | DEC:79–81; none (history); not current pricing or authorization. |
| 50 | Paid-compute upgrade needs approval | duplicate | Original 30; AP R6:51; review. |
| 51 | Local CPU cleaning/assembly needs no GPU or cloud | playbook | DEC:83–87; none (history); offline boundary retained. |
| 51 | Training is the Colab stage | playbook | DEC:85–87; none (history); external generation/serving distinguished. |
| 51 | Roughly 1,000 semantic generation calls | playbook | DEC:89–91; none (history); estimate, not implemented exact count. |
| 51 | Generation spending is the first approval checkpoint | duplicate | Original 30,50; AP R6:51; review. Chronological first-checkpoint wording is obsolete. |
| 52 | Evaluation is required before success claims | project rule | AP R11:56; review; scorecards are evidence, not release approval. |
| 52 | Stylometry compared with real-author reference | contract | AP D2:14–18; DEC:95–97; IG checks shared helpers, PIPE metric/cadence outcomes; measurement review. |
| 52 | Sentence-length mean/variance plan | playbook | DEC:95–97; DOMAIN:10; none (history); current population standard deviation correction retained. |
| 52 | Adverb, passive, parataxis and dialogue metric plan | playbook | DEC:95–97; none (history); proxy limitations and missing passive measurement explicit. |
| 52 | spaCy/textstat library plan | playbook | DEC:95–97; none (history); explicitly not implemented. |
| 52 | Blind randomized held-out pairwise judgment | contract | AP D4:26–30; DEC:95–97; PIPE checks tally; randomness, independence and cache identity require review. |
| 52 | More author-like while remaining a good answer | contract | AP D4:27–30; DEC:95; PIPE coherence outcomes; broader usefulness review. |
| 52 | Greater than 70% wins against prompted baseline | project rule | AP R11:56; DEC:95–97; review. Current target narrowed to decisive real-text comparisons. |
| 52 | Incoherence or degeneracy cannot win | contract | AP D4:29–30; PIPE tests both assignments and rejection cases; cadence also AP D2 / PIPE. |
| 55 | Prompt-imitable style may yield a small demo gap | duplicate | Original 33; DEC:99,105; none (historical hypothesis). |
| 55 | Unknown-client pretraining and rule-reducibility assumptions | playbook | DEC:101,105; none (history); explicitly not established. |
| 55 | Forecast that demo understates unseen-client performance | playbook | DEC M07; exact forecast retained as unproved, no unseen-client performance or pretraining evidence; AP R7 client simulation required; none (history). |
| 55 | Demo floor/ceiling positioning | playbook | DEC:103–105; none (historical positioning); AP R7 prevents general claim without proof. |
| 56 | Shared public evaluability motivates demo selection | playbook | DEC:107–109; none (history). Exact wording differs in Markdown emphasis only. |
| 57 | Thin-data, obscure-writer client simulation | project rule | AP R7:52; DEC:111–113; GLOSS:37; OOS:16; review. |
| 57 | Few-thousand-word scale and presumed no pretraining exposure | playbook | DEC:111–113; none (history); selection assumptions require documentation. |
| 57 | Same pipeline and blind scoring before service claims | duplicate | Original 16,33; AP R7:52; DEC:111–113; review. |
| 57 | Failed thin-data voice capture blocks business proof | playbook | DEC:111–113; AP R7 / review. |
| 60 | Bulk cleaning/parsing belongs in scripts, outside model context | project rule | AP R9:54; DEC:117,125; review. |
| 60 | Models handle small summaries and semantic understanding | playbook | DEC:117; AP R9:54; review. |
| 60 | Mechanical cleaning's near-zero token rationale | playbook | DEC:117; none (history). Closing metaphor dropped as rhetoric. |
| 61 | Training does not clean, OCR or repair supplied examples | playbook | DEC:119; none (historical rationale). Opening metaphor dropped as rhetoric. |
| 61 | Data preparation takes priority; training is mechanical | playbook | DEC:119; none (historical rationale). |
| 62 | Digital-text corpus needs no OCR/extraction | playbook | DEC:121; none (history). |
| 62 | Docling/Marker are options for messy documents | playbook | DEC:121,123; OOS:16; none (history/scope). |
| 63 | Future ingestion for PDFs, word-processing files, scans and email | playbook | DEC:123–125; OOS:16; none (history/scope). |
| 63 | Extraction converts client documents into clean pipeline text | playbook | DEC:123–125; none (history); deferred. |
| 66 | Setup/corpus/model/method/compute milestone completion | dropped | Obsolete status snapshot; no public destination; none. Durable decisions accounted above. |
| 66 | Historical local terminal check | dropped | Transient private environment action; no public destination; none. |
| 67 | Clean, design, generate, template-format and holdout sequence | duplicate | Original 42,45–47,51; DEC:27,49–55,83–87; current design supersedes roadmap status. |
| 67 | Approximate generation size | duplicate | Original 45,51; DEC:49,89–91; none (history). |
| 67 | Cleaner not yet run and data phase underway | dropped | Obsolete progress state; no public destination; none. |
| 68 | Colab QLoRA and style/blind evaluation milestone | duplicate | Original 49–52; DEC:69–77,95–97; AP R11 / review. |
| 68 | Iterate until greater than 70% wins | duplicate | Original 52; AP R11:56; review. |
| 69 | Three-column demo milestone | duplicate | Original 13,36–39; DEC M02 preserves layout; AP D5 prompt behavior / DEMO + review. |
| 69 | Local fine-tuned and prompted-base serving | duplicate | Original 39,50; DEC:73–77; AP D5 / review. |
| 70 | Thin-data unknown-writer business-proof milestone | duplicate | Original 57; AP R7:52; review. |
| 71 | Visual-model milestone deferred | duplicate | Original 16; DEC:15–17; OOS:16; none (scope). |
| 74 | Generation engine originally unresolved before generation stage | dropped | Obsolete open decision; DEC:135 records selected Gemini; none (history). |
| 74 | Free Gemini/AI Studio option and quality estimate | playbook | DEC:129,135; none (history); dated estimates, not benchmarks. |
| 74 | Private local CLI tooling option | dropped | DEC:135 acknowledges omitted obsolete option; no private tooling details preserved; none. |
| 74 | Paid API providers, cost and quality estimate | playbook | DEC:131,135; none (history); spending still AP R6 / review. |
| 74 | Larger open model on Colab, free/fiddly estimate | playbook | DEC:133–135; none (history). |
| 74 | Historical recommendation to start with free Gemini | playbook | DEC M08; exact original recommendation retained, open decision obsolete after selection; AP R6 governs spending; none (history). |
| 74 | Generation expense approval | duplicate | Original 30,51; AP R6:51; review. |
| 75 | Nonblocking choice of 1925 expansion | duplicate | Original 44; DEC:39–41; OOS:16; none (scope). |
| 76 | Initial 3B and optional later 1B experiment | duplicate | Original 48; DEC:65–67; OOS:16; none (history/scope). |
| 79 | Keep all five raw Gutenberg input files | project rule | AP R10:55; IG checks exact allowlist and existence; DEC:27; provenance review. |
| 80 | Dropped copyrighted input must not be used | duplicate | Original 43; AP R10:55; IG + rights review. |
| 81 | Cleaner path, boilerplate stripping, output files and word counts | playbook | DEC M09 preserves exact safe description; verified against cleaner RAW_FILES, strip_gutenberg and main; none (history), IG allowlist. |
| 81 | Cleaner written but not run during terminal failure | dropped | Obsolete private progress state; no public destination; none. |
| 82 | Instruction and live-state handoff file roles | duplicate | Original 3; instruction role CORE:103–107; DEC M01 preserves private ignored handoff role and local-read condition; AP R12 privacy review. |
| 85 | Owner-specific teaching and role agreement | duplicate | Original 22–23; privacy drop, CORE M5 / AP R12; review. |
| 86 | Money/live-system/irreversibility approval gates | duplicate | Original 30; AP R6:51; review. |
| 86 | Protected unrelated production restriction | duplicate | Original 8; AP R6:51; review; private details omitted. |
| 87 | Owner-specific context limits and compaction prohibition | dropped | No public destination; CORE M5 / AP R12; review. WORK:72–74 describes recovery, not equivalent thresholds or prohibition. |
| 87 | Delegate to conserve main-session context | playbook | WORK:43–48; advisory; review. No exact concurrency/threshold policy claimed. |
| 87 | Handoff before stopping | dropped | Owner-specific stop/handoff policy omitted; WORK:72–74 external ledger is a different practice; review. |
| 90 | Dated kickoff/progress/temporary-interruption snapshot | dropped | Obsolete status and private session context; no public destination; none. |
| 90 | Approved corpus and short-edition findings | duplicate | Original 42,44; DEC:27,35–41; AP R10 / IG + review. |
| 90 | Cleaner completion state | duplicate | Original 81; obsolete private status dropped; DEC M09 preserves safe file/output summary. |
| 90 | Selected model, QLoRA, instruction data and compute approach | duplicate | Original 45–51; DEC:49–91; corrected license AP R13 / review. |
| 90 | Fair baseline and style/blind evaluation | duplicate | Original 39,52; AP D4–D5, R11; PIPE + DEMO + review. |
| 90 | Multi-perspective kickoff debate, proceed-with-changes outcome | playbook | DEC M10 preserves exact event record with roles, outcome and reported changes; attributed to original, no independent transcript or proof; none (history). |
| 90 | Next action belongs in live-state handoff | duplicate | Original 3,82; DEC M01 preserves next-action pointer; read private ignored HANDOFF.md when locally present; AP R12 privacy review. |

## New framework inventory

These identifiers exist in AP. The original supplied related concerns, not every new invariant or gate. This table does not backdate the framework to the original source.

| ID | Actual destination | Original overlap / added scope | Declared gate |
|---|---|---|---|
| D1 | AP:8–12 | 47 holdout/template; shared hashing, span claims and deduplication are added implementation contracts | IG + PIPE; sampling/provenance review |
| D2 | AP:14–18 | 52 stylometry/coherence; shared rhythm path and mining exception are added | IG + PIPE; answer/pastiche review |
| D3 | AP:20–24 | No explicit original fidelity contract; new final-rewrite acceptance path | IG + PIPE; factual equivalence/dictionary review |
| D4 | AP:26–30 | 52 blind/coherent counting; task slicing and capability handling are added | PIPE; judge/cache/fallback review |
| D5 | AP:32–36 | 39 fair comparison; proxy credential boundary and neutral fine-tuned prompt are added | IG + DEMO; lineage/fairness/validation/recovery review |
| D6 | AP:38–42 | 49 training context; builder/notebook single source is added | IG generated-cell comparison; training/prompt review |
| R1 | AP:46 | New repo-root and hook setup rule | review; CI reruns gates |
| R2 | AP:47 | New prose skill requirement; 21,23 explain/define overlap | review |
| R3 | AP:48 | New UI outcome-test rule | review pending browser runner; scripts/ratchet.py labels |
| R4 | AP:49 | New feature-spec and PR acceptance rule | scripts/pr_body_check.py in pr-acceptance CI |
| R5 | AP:50 | New agent-comment attribution rule | review |
| R6 | AP:51 | 8,30,50–51,74,86 approvals/protection | review |
| R7 | AP:52 | 16,24,33,57,70 transfer and client proof | review |
| R8 | AP:53 | 28–30,41 premise challenge, misconception correction, early risks, independent review/debate, assumptions, synthesis and settled decisions | review |
| R9 | AP:54 | 60 mechanical/semantic boundary | review |
| R10 | AP:55 | 42–44,79–80 approved corpus/exclusion | IG; jurisdiction/provenance review |
| R11 | AP:56 | 52,68 measured success; real-text threshold refinement | review; scorecards are evidence only |
| R12 | AP:57 | Public/private migration boundary added; private original categories dropped | IG; private prose/releases review |
| R13 | AP:58 | 48 license claim corrected | review; corrected DOMAIN:21–23 |

## Missing preservation resolved

All ten omission IDs remain in this ledger. The linked sections append safe exact excerpts to DEC without moving its earlier line references. M03 also points to the repaired current R8. Private profile, business identifiers, machine locations, operational contents and transient execution state remain excluded.

| Missing ID | Original line(s) | Resolution and preserved content |
|---|---|---|
| M01 | 3,82,90 | Resolved: [local handoff role](../agents/project/project-decisions.md#m01-local-handoff-role). Current live-state and next-action role; read private ignored HANDOFF.md when locally present after the current instruction load order. No private operational contents copied. |
| M02 | 13,36–39,69 | Resolved: [comparison layout](../agents/project/project-decisions.md#m02-comparison-layout). Exact question-left, fine-tuned-middle, same-base prompted-right arrangement retained; D5 owns fairness. |
| M03 | 28–29 | Resolved: [premise review and synthesis](../agents/project/project-decisions.md#m03-premise-review-and-synthesis) and [R8](../AGENTS.project.md#project-rules). Current premise challenge, misconception correction, early risks, recorded assumptions and reported synthesis explicit; independent review/debate replaces debate-only wording. |
| M04 | 33 | Resolved: [recorded kickoff verdict](../agents/project/project-decisions.md#m04-recorded-kickoff-verdict). Exact verdict and learning rationale attributed to original record; comparison unproved and cost guarantee obsolete. No new independent proof. |
| M05 | 33 | Resolved: [easy-case hypotheses](../agents/project/project-decisions.md#m05-easy-case-hypotheses). Exact pretraining-saturation and near-formulaic-style claims retained as unproved hypotheses; R7 client simulation required. |
| M06 | 44 | Resolved: [short-edition rationale](../agents/project/project-decisions.md#m06-short-edition-rationale). Exact concentrated-style/limited-breadth rationale retained; training-quality inference unproved, current edition and deferred expansion identified. |
| M07 | 55 | Resolved: [unseen-client forecast](../agents/project/project-decisions.md#m07-unseen-client-forecast). Full safe forecast retained as unproved; no asserted pretraining membership or unseen-client performance evidence; R7 client simulation required. |
| M08 | 74 | Resolved: [original generation recommendation](../agents/project/project-decisions.md#m08-original-generation-recommendation). Exact free-Gemini starting recommendation retained as obsolete open decision; later selection and R6 spending gate distinguished. |
| M09 | 81 | Resolved: [cleaner inventory](../agents/project/project-decisions.md#m09-cleaner-inventory). Exact safe script, boilerplate stripping, clean/*_clean.txt output and per-file word-count description retained; current code verified, transient execution state excluded. |
| M10 | 90 | Resolved: [recorded kickoff review](../agents/project/project-decisions.md#m10-recorded-kickoff-review). Exact roles, proceed-with-changes conclusion and reported incorporation retained, attributed to original record. No independent transcript or itemized change list supplied. |
