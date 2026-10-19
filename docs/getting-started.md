# Getting Started

Nothing to install beyond Claude Code and Python 3.11+. ContractGraph runs entirely inside Claude Code — no server, no API key, no external model call outside Claude Code itself. The Python scripts under `scripts/` use only the standard library. If you can run `/contractgraph:init`, you have the whole runtime.

```bash
git clone https://github.com/Phoenixarjun/ContractGraph.git
cd ContractGraph
python evals/run_evals.py   # deterministic self-check, no network, no model calls
claude                      # then use the /contractgraph:* commands
```

## The Six Commands, in Order

```text
/contractgraph:context    → scaffold context/ for your workflow (only if it doesn't exist yet)
/contractgraph:contract   → design or validate your contracts/<workflow>/ bundle
/contractgraph:init       → compile contracts + context into runtime/compiled/<bundleId>/
/contractgraph:validate   → run deterministic structural checks, any time, on demand
/contractgraph:run        → execute the compiled graph against one runtime input
/contractgraph:finalize   → aggregate, verify, and close out a run (invoked by run; re-runnable)
```

`validate` has no fixed position — run it whenever you want a fast pass/fail on a bundle, before or after `init`. `finalize` is the terminal stage of `run`, and is safe to invoke again on its own if a run needs to be closed out after a repair. After the first pass, only `init` and `run` recur (see [graph-compilation.md](graph-compilation.md) for when `init` actually needs to rerun).

## Worked Example — Study Plan (public, synthetic)

The bundle shipped in this repository. It uses a fabricated learner profile, so you can run it end to end without supplying any personal data:

```text
/contractgraph:validate contracts/study-plan --context context/synthetic/study-plan
/contractgraph:init     contracts/study-plan --context context/synthetic/study-plan
/contractgraph:run      contracts/study-plan --input "backend and AI systems engineering" \
                        --context context/synthetic/study-plan
```

The run produces `runtime/runs/<run-id>/final/final.json` — verified against `contract.schema.json` — plus a trace, a cost breakdown, and a privacy-classified derived-context file.

## Worked Example — Your Own Workflow (private)

The same six commands, pointed at a bundle you design and your own ground truth:

```text
/contractgraph:context    "create a personalized distributed systems study plan"
/contractgraph:contract   "study plan; examples/sample-goals.json"
/contractgraph:validate   contracts/my-study-plan
/contractgraph:init       contracts/my-study-plan
/contractgraph:run        contracts/my-study-plan --input "distributed systems engineering"
```

- `context/canonical/` holds your real profile, resume, skills, and experience. It is git-ignored.
- Nothing about that path is checked in — it is private by design (see [privacy.md](privacy.md)).
- No core script, skill, or command changes to support it. That is the whole claim; see [adding-a-workflow.md](adding-a-workflow.md).

## Where Things Land

| You want | Look at |
|---|---|
| What got compiled | `runtime/compiled/<bundleId>/compilation-report.md` |
| A specific run's evidence, sections, or trace | `runtime/runs/<run-id>/` |
| The final verified artifact | `runtime/runs/<run-id>/final/final.json` |
| Whether the run actually completed | `runtime/runs/<run-id>/run.json` → `runStatus` |
| Why a node failed | `runtime/runs/<run-id>/verification/<nodeId>.json` (see [validation.md](validation.md)) |

## Next

- Adding your own workflow: [adding-a-workflow.md](adding-a-workflow.md)
- How execution actually works: [execution.md](execution.md)
- How validation actually works: [validation.md](validation.md)
