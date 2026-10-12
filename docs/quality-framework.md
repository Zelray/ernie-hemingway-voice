# Repository quality checks

Run `python scripts/gates.py` from the repository root. It runs the offline test suite, the lint and quality ratchet, syntax parsing, and mutation smoke. `make gates` invokes the same command when Make is installed.

Install the check dependencies with `python -m pip install -r requirements-dev.txt`. Python 3.13 is used locally and in CI. Training remains in Colab; repository checks need no GPU, API credentials, model downloads or inference service.

## What the checks measure

The instruction tests resolve each contract's files and symbols, check the portable core and word budget, require the named knowledge files, validate generic privacy patterns and cited commits, inspect shared helper use and the neutral training system turn, compare the 13 notebook cells with their builder, and check the corpus and browser request boundaries. The always-loaded word budget is 3,000, calculated from 1,704 final setup words plus half, rounded up to the next 500. Changing that budget needs a reason in the commit message.

The ratchet invokes Ruff once over maintained Python files. Existing findings are counted by rule; new files and previously clean files must have zero findings. It also counts files over 400 code lines, selected internal mocks, existence-only assertions, fixed end-to-end sleeps, and static controls missing associated labels. Code-line counts exclude comments, blank lines and standalone docstrings. These lexical quality counters catch their declared forms; they do not replace review of test usefulness or full accessibility.

`python scripts/ratchet.py --details` prints each unit with its file and line. `--update` lowers counts after an improvement. It rejects a rise or a removed counter. A deliberately raised baseline must be edited by hand and explained in its commit (C7).

Mutation smoke changes three isolated copies: span overlap detection, the near-duplicate threshold, and the coherence-loss outcome. It requires passing original controls and actual assertion verdicts after each change. Runtime exceptions, missing dependencies, skipped tests and expected failures cannot count as killed mutations. The real pipeline files are not modified.

`python scripts/prove_gates.py` exercises scratch violations and confirms restored controls. It checks the actual instruction and ratchet commands and uses temporary Git ranges to verify that a new test which already passes on old code is rejected. Missing test execution is a gate error, not proof.

## Commits and CI

Enable the versioned pre-commit hook once per clone:

```text
git config core.hooksPath .githooks
```

The hook runs the instruction tests and ratchet. It checks the working tree; run the relevant tests before committing (P3). Its executable Git mode and LF line endings are versioned. Scratch controls invoke it through Git and require it to reject a contract violation. CI repeats the full gates on Windows and Linux with full Git history.

The proven-red CI job compares the merge base with the submitted head. Changed application tests must pass at head and fail on the earlier code. Each new test is judged independently, so a passing test cannot hide beside a failing one. Missing application symbols produce an explicit warning. Infrastructure failures cannot satisfy proof.

A range with no application-source changes announces a skip. This applies to the initial framework: it tests existing behavior and proves gate rejection through scratch controls. A nonbehavior conventional title with no changed tests can also bypass proof, with a warning. Titles are unverified input; inspect those skips (M2).

The PR body job checks same-repository, non-bot PRs, including title and body edits. It requires content under `## Acceptance`, and under `## Spec` for a feat title. HTML comments do not count. Title and body arrive through environment variables, so their text is never shell code. Fork and bot exceptions remain explicit in the workflow.

CI is not active for these local commits until they are pushed. Discovery found no branch protection. Making the new checks required is a separate GitHub setting change; the local setup does not change it.

## Review boundaries

Contracts D1–D6 combine automated clauses with review clauses. Tests establish the declared data and prompt outcomes. Review establishes corpus rights, representative samples, full rewrite fidelity, answer usefulness, judge independence, model lineage, fair prompts, streaming recovery and valid training choices.

The out-of-scope ledger records existing application defects and the model-license correction. Setup does not repair or conceal those issues. Pick each fix separately, state its acceptance outcome, and lower any affected ratchet count after it passes.

The repository's P10 prose rule governs repository prose. Global assistant guidance is not copied into public instructions. The local private handoff remains ignored; the new CLAUDE.md contains only template imports.

After the first incident, or after a month, run `gap-trap refine` to review the rules against what happened.
