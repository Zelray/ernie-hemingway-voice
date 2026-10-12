# Testing playbook

Read before tests, UI work or platform checks.

## Test design

- Exercise returned data, saved outcomes, errors and boundaries (C6).
- Mock only external model/network boundaries. Internal-module mocks are counted by the ratchet.
- Changed application tests run against fork-point code through python scripts/proven_red.py <base> <head> (P2). Every new test must go red individually; a failing sibling cannot carry a passing test.
- Framework tests of existing behavior are established by deliberate violations and mutation smoke. A framework-only range reports its historical proof skip; application-source changes remove that exemption.
- Static UI lint measures associated control labels. It does not establish keyboard navigation, focus handling, color contrast or a complete visitor journey. Those require browser tests or review.
- Use no fixed E2E sleeps. Outcome checks wait on the condition under test.

## Commands

```text
python -m pytest -q
python scripts/gates.py
python scripts/mutation_smoke.py
python scripts/prove_gates.py
python scripts/ratchet.py --details
```

Offline commands need no GPU, API key or model service. requirements-dev.txt supplies the runner and demo API dependencies. Use Python 3.13. The CI runs the same commands on Windows and Linux.

## Pipeline traps

The notebook builder writes at import. Several generators read credentials at import. Inspect them through AST, and test pure helpers with synthetic data. Never run dataset generators, notebook training, cloud launchers or the evaluator's --dry mode as a gate. Historical source prose and scorecards remain untouched by setup.

Mutation smoke uses temporary copies of the public Git inventory. Its unmodified controls must pass; a mutation must trigger an assertion verdict in the named test. Syntax errors, runtime exceptions, missing dependencies and empty collection are infrastructure errors, not caught mutations. The report parser reads runner diagnostics rather than echoed source lines. Standard-library XML parsing consumes only reports produced by the local pytest subprocess in temporary directories; gates accept no supplied XML files.

AST contract checks verify declared helper imports, calls and forbidden replacement definitions. They do not prove that every execution path uses the helper correctly; representative outcomes and consumer control flow still need review.

No browser runner is currently configured. A future UI behavior change must supply its journey test rather than counting an API or markup test as end-to-end coverage.
