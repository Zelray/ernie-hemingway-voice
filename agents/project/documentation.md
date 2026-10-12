# Documentation playbook

Read before editing user or developer documentation.

## Scope

- User-visible behavior updates README.md and demo/README.md (P10).
- New pipeline APIs, gates and workflows update docs/quality-framework.md and the relevant playbook.
- A changed main user flow updates its call-flow explanation; do not add a trace for a journey already covered.
- Examples name real symbols or say they are simplified. Cite symbols instead of unstable line numbers.
- Developer docs cite rule IDs and contract names rather than duplicating portable rules.

## Style

Write and review human prose with slop-mop. Explain behavior to a colleague who knows engineering but not this pipeline. Define a code-specific term where it first affects understanding. Instruction files remain terse statements with gate names.

Reports identify observed counts, commands and limitations. Claim no historical incident or model result without its source. A stored scorecard is evidence from a prior evaluation, not a fresh live run. Historical kickoff decisions carry explicit current, superseded or unverified labels.
