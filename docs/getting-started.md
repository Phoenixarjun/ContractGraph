# Getting Started

Nothing to install. ContractGraph runs entirely inside Claude Code — no server, no API key, no external model call outside Claude Code itself. If you can run `/contractgraph:init`, you have the whole runtime.

## The Five Commands, in Order

```text
/contractgraph:context    → scaffold context/ for your workflow (only if it doesn't exist yet)
/contractgraph:contract   → design or validate your contracts/<workflow>/ bundle
/contractgraph:init       → compile contracts + context into runtime/compiled/
/contractgraph:validate   → run deterministic structural checks, any time, on demand
/contractgraph:run        → execute the compiled graph against one runtime input
```

`validate` has no fixed position — run it whenever you want a fast pass/fail on a bundle, before or after `init`. The other four run in the order above the first time; after that, only `init` and `run` recur (see [graph-compilation.md](graph-compilation.md) for when `init` actually needs to rerun).

## Worked Example — Company Research (private)

This repository's first validated bundle:

```text
/contractgraph:validate contracts/company-research
/contractgraph:init contracts/company-research
/contractgraph:run --input "Acme Corp" --roles ai-engineer,backend-engineer
```

- `context/canonical/` holds your real profile, resume, skills, and experience.
- The run produces `runtime/runs/<run-id>/final/final.json` — a fully-verified report against `contract.schema.json` — plus a trace, a cost breakdown, and any new `context/derived/` entries.
- Nothing here is checked in publicly; this path is private by design (see [privacy.md](privacy.md)).

## Worked Example — Study Plan (public, synthetic)

The public demonstration of the same mechanism, using a fabricated learner profile instead of real personal data:

```text
/contractgraph:context contracts/study-plan       # scaffolds context/synthetic/ for a study-plan workflow
/contractgraph:contract contracts/study-plan      # designs the study-plan contract bundle
/contractgraph:init contracts/study-plan
/contractgraph:run --input "system-design-interview" --as-of 2026-07-27
```

Same commands, same compile sequence, same three validation layers, same node state machine — the only things that changed are the contract bundle and the context tree. That is the point: see [adding-a-workflow.md](adding-a-workflow.md) for how you'd do this for any workflow of your own, and [evaluation.md](evaluation.md) for how this fixture is used to regression-test genericity itself.

## Where Things Land

| You want | Look at |
|---|---|
| What got compiled | `runtime/compiled/compilation-report.md` |
| A specific run's evidence, sections, or trace | `runtime/runs/<run-id>/` |
| The final verified artifact | `runtime/runs/<run-id>/final/final.json` |
| Why a node failed | `runtime/runs/<run-id>/verification/<nodeId>.json` (see [validation.md](validation.md)) |

## Next

- Adding your own workflow: [adding-a-workflow.md](adding-a-workflow.md)
- How execution actually works: [execution.md](execution.md)
- How validation actually works: [validation.md](validation.md)
