# Glossary

One name per concept in code, briefs and documentation. User-facing wording may use the established product aliases.

## Process

**Contract**: an architecture entry in AGENTS.project.md with Owns, Path, Never and Gate fields.

**Gate**: a command that fails a commit or CI run when a declared rule breaks.

**Brief**: the requirements given to an implementation or review agent.

**Spec**: the approved behavior description against which acceptance is judged.

**Seam**: the interface a test exercises to observe behavior.

**Proven red**: a changed test run against pre-change code and shown to fail.

**Ratchet**: stored counts that may hold or fall but cannot rise automatically.

## Voice training

**Ernie**: the Hemingway demo. Aliases: Ernifier and Ernestifier. The per-client naming proposal is [Client]-fier; it is provisional.

**Flatten-restore**: remove style from real source prose to build the input, then train against the original prose as the answer.

**Real-text slice**: description and rewrite tasks whose target answers are real source text.

**Imitation slice**: practical Q&A with generated Hemingway-style answers, discounted when interpreting transferable evidence.

**Cadence**: the measured distribution of sentence lengths and fragments in an answer.

**ChatML**: the Qwen conversation representation; the dataset stores system, user and assistant messages, and the tokenizer applies the actual chat template.

**QLoRA**: train small adapter weights while loading the underlying model in 4-bit form.

**Client simulation**: the separate test using an obscure writer with thin data. It establishes evidence the Hemingway demo cannot supply.
