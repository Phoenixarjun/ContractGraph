# Agent Generation

`agent-definition-generator` turns each compiled node — plus two fixed verifier roles — into one subagent definition under `.claude/agents/generated/`. A subagent's job is bounded to exactly one node; it is never handed the shape of the whole workflow.

## Inputs per Node

For node `<nodeId>`, the generator reads:

- `node-contracts/<nodeId>.contract.json`'s `x-contractgraph` block (`purpose`, `aggregationPath`, `dependsOn`, `multiplicity`, `completionRules`) — see [contract-model.md](contract-model.md).
- `policies.json.models` for its model tier (research/repair/verification routing).
- `capability-manifest.json` + `skill-manifest.json` for its bound skill set.
- The minimum tool set its bound skills actually require — never a broader grant "to be safe."

## Generated File Shape

Every file under `.claude/agents/generated/` follows the same structure (see `.claude/agents/generated/<nodeId>.md` and `section-verifier.md` for worked examples):

```markdown
---
name: <nodeId>
description: <purpose, copied verbatim from x-contractgraph.purpose>
tools: <minimum tools its skills require>
model: <policies.json routing>
---

# <Node> Agent

## Responsibility     — one bounded sentence, never broadened
## Node Contract       — path to its contract; output MUST validate against it exactly
## Inputs               — runtime input fields it needs, canonical context by path (read-only), upstream sections its dependsOn resolves
## Output               — exact write path under runtime/sections/ (or runtime/sections/<nodeId>/<itemId>.json for a map node)
## Required Skills      — bound skill list, nothing added
## Budget                — search/read budget, "comprehensive not exhaustive"
## Retry Policy          — maxRetriesPerNode, triggered only by verifier rejection, addresses repairInstructions
## Evidence Requirements — the completionRules' evidence bar, restated concretely for this node's fields
## Completion Conditions — status == complete, schema valid, verifier passes
## Prohibitions          — cannot self-approve, cannot read context/private/, cannot declare anything beyond its own node complete
```

`purpose` and `completionRules` are copied verbatim from the contract, never paraphrased broader or softer — a generated agent's responsibility can only be as wide as its contract says.

## Map Nodes

A node with `multiplicity: "map"` (e.g. `resume-analysis` over `configuredRoles`) still gets one agent definition, invoked once per set item; its `Output` section names the per-item path pattern (`runtime/sections/resume-analysis/<roleId>.json`), and a downstream deterministic merge — not the agent itself — assembles the per-item outputs into one schema-valid section. See `graph-compilation.md`'s open-question note on this for why `graph.yaml`, not the contract's `mapNodes` field, is authoritative for the map layer.

## The Two Verifier Agents

`section-verifier` (sonnet) and `global-verifier` (opus) are generated once per bundle, not once per node — every node in the bundle is verified by the same `section-verifier` instance definition, parameterized per invocation by which node/section it's given. Their `nodeContract` is `null` in `agent-manifest.json` because they verify against whichever node contract is handed to them at dispatch time, not one fixed contract. See [validation.md](validation.md) for their shared output contract.

## What a Generated Agent Can Never Do

- Approve its own output (`workerCannotSelfApprove` — enforced by construction: no node agent is ever also assigned the verifier role for its own section).
- Read `context/private/`.
- Declare the overall workflow, another node, aggregation, or global verification complete — only `global-verifier` renders that verdict, and only after aggregation.
- Represent a research claim as canonical user truth, or invent candidate experience not present in canonical context.

`graph-plan-reviewer` checks every one of these constraints mechanically before compilation is reported complete (see [graph-compilation.md](graph-compilation.md)) — a subagent definition that grants itself broader authority than its node contract allows is a compile-time blocker, not a runtime surprise.
