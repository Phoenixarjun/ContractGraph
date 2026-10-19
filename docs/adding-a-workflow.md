# Adding a New Workflow

The test of ContractGraph's core claim is this: adding a brand-new workflow — a study plan, an architecture review, or anything else — never requires touching `scripts/`, `.claude/skills/bootstrap/`, or any `/contractgraph:*` command. Only `contracts/<new-workflow>/` and `context/` change.

## The Path

```text
/contractgraph:context   → propose context/ shape for the new workflow, stop for approval
/contractgraph:contract  → design contract.bundle.json + node contracts, stop for approval
/contractgraph:init      → compile: capabilities, skills, agents, graph
/contractgraph:validate  → deterministic structural pass (safe to run any time in this sequence)
/contractgraph:run       → execute against a real runtime input
```

### 1. `/contractgraph:context`

`context-advisor` classifies every candidate fact for your workflow into ground truth (→ `context/canonical/`), researchable (→ excluded entirely, fetched fresh at run time instead), or sensitive (→ `context/private/`), then proposes the smallest folder set from a domain-neutral vocabulary. It stops and shows you the proposed tree before creating anything. See [context-model.md](context-model.md).

### 2. `/contractgraph:contract`

`contract-designer` runs in whichever mode matches what you bring:

| You have | Mode |
|---|---|
| Finished contracts already | **Explicit** — validates structure, points out gaps, adds nothing unrequested |
| Just an intent | **Assisted** — proposes the whole contract tree from first principles |
| Intent + an example/legacy output | **Hybrid** (default) — mines the example for candidate subcontracts and schemas |

Every mode stops for your approval before writing a single contract file. See [contract-model.md](contract-model.md) for the bundle wiring (`contract.bundle.json`, `node-contracts/`, `policies.json`) your new workflow needs.

### 3. `/contractgraph:init`

This is where genericity is actually exercised: `workflow-compiler` runs the identical 10-step compile sequence — structural validation, context indexing, capability detection, skill reuse/creation, agent generation, graph compilation, compiled-graph validation — against your new bundle, with zero branching on what domain it is. See [graph-compilation.md](graph-compilation.md), [skill-generation.md](skill-generation.md), and [agent-generation.md](agent-generation.md).

If your workflow needs a capability no existing skill satisfies (e.g. a domain-specific scoring method), `skill-creator` authors one — evaluated on the same seven dimensions as any other skill, with the same privacy bar. Nothing about your new domain is written into the skill's trigger or procedure beyond what the capability itself requires — a well-formed generated skill for your workflow should read no differently than one authored for any reference workflow.

### 4. `/contractgraph:validate`

Optional at any point in this sequence — a fast, non-mutating structural check. Useful right after step 2 (bundle valid before compiling) and again after step 3 (compiled graph has no cycles/orphans).

### 5. `/contractgraph:run`

Executes exactly the same 19-step lifecycle described in [execution.md](execution.md), against your new graph. Same node state machine, same three-layer validation, same caching model, same aggregation and global verification. The runtime input shape (`runtimeInputs.required`/`optional`/`defaults`) comes from your bundle, not from any hard-coded assumption about what a "run" needs.

## What You Should Never Do

- Hand-write `.claude/agents/generated/<nodeId>.md` yourself — it's a compile artifact; edit the node contract instead and re-run `init`.
- Copy an existing skill and tweak it for your domain instead of letting `capability-detector` + `skill-registry-manager` decide reuse vs. create — that's how duplicate, overlapping skills accumulate.
- Add a domain-specific `if workflow == "..."` branch anywhere in `scripts/` or a bootstrap skill. If you find yourself wanting one, the missing piece belongs in your contract (a new node, a new completion rule) or your context (a new canonical fact), not in the framework.

## Proof This Works

`evals/workflow-cases/` exercises this exact path against the synthetic study-plan fixture — a domain-specific workflow compiled and run through the identical mechanism. See [evaluation.md](evaluation.md).
