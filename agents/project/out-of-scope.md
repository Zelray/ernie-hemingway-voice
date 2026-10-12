# Out of scope

Check this ledger before proposing work (P1). Setup records existing defects without changing application behavior. A selected fix gets its own acceptance criteria, regression test and commit.

- The README calls Qwen2.5-3B-Instruct Apache-2.0. Upstream uses the Qwen Research License. Correct public licensing descriptions and assess commercial model use separately. No commercial clearance is established by this repo.
- The evaluator uses eligible or epoch_keys for recommendation. If every epoch fails retention, it still selects one. Fix the all-failed outcome before treating capability retention as a release veto.
- Bucket 4 promotion reports cadence failures but writes the kept rows anyway. Decide and test a blocking promotion policy separately.
- Assembly --dry returns before the PASS failure exit. Its zero exit alone is not acceptance evidence. Gates inspect pure functions and data outcomes instead.
- Evaluation cache identity omits judge model, input content and prompt version. Changed judging conditions can reuse stale verdicts.
- Demo input validation does not cover malformed JSON, non-string text or invalid seed values. Forwarded client IP headers rely on a trusted proxy deployment. Stream connection retries can run after partial tokens despite the stated intent. Review these before public serving.
- Fidelity garble checking depends on an external wordlist and silently disables without one. Dictionary-independent tests cover only the declared cardinal and entity fixtures.
- Three static controls lack associated labels. The accessibility_labels ratchet preserves this existing count; a UI fix should lower it. A full browser accessibility audit is not installed.
- Existing Python lint backlog is 35 findings across five rules. The passage miner has 413 code lines. Ratchet counts may hold or fall; setup does not reformat existing pipeline code.
- No end-to-end browser runner exists. UI behavior changes need one; current in-process API tests establish only server outcomes.
- Branch protection was absent at discovery. CI files alone do not require green checks before merge. Publishing and protection configuration are separate owner actions.
- Thin-data client simulation remains unproved. Also deferred: the 1925 In Our Time edition, optional 1B experiment, messy-document ingestion via Docling/Marker, and the separate visual-model project.
