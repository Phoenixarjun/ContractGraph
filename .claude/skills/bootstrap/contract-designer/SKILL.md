---
name: contract-designer
description: Use whenever a ContractGraph user needs to create, revise, or reason about a contract — turning a desired final output, an intent, an example, or a legacy JSON export into a contract bundle. Trigger this before /contractgraph:init, when populating contracts/, when the user says things like "design the contract", "here's my old output, derive the structure", "what nodes do I need", or when unsure how to split a deliverable into validatable pieces. Domain-agnostic: it must never treat HLD, LLD, DSA, Python, Databases, or any other domain term as a built-in framework concept.
---

# Contract Designer

## Overview

A contract describes the **required final output** and how a machine and a verifier decide it is correct. The ContractGraph framework is deliberately generic: it understands only four things — **a main contract, its subcontracts, the dependencies between them, and the rules for validating and aggregating them.** Everything domain-specific ("HLD", "Python", "DSA", "Company intelligence") is just a *node name and schema inside one particular contract*. It is never framework code.

This matters because the same designer has to produce a company-research contract and a study-plan contract with zero domain logic in the core. If a design only works for one domain, it has leaked domain knowledge into the wrong layer and is wrong.

This skill takes a deliverable and decomposes it into a main contract plus machine-validatable node subcontracts, infers the dependencies between nodes from their data needs, and writes the bundle **only after the user approves the proposed tree.**

## When to Use

- The user wants to create or revise `contracts/<workflow>/`.
- The user has an intent, an example output, or a legacy JSON export to derive contracts from.
- The user is unsure how to split a deliverable into nodes, or how to make a node machine-checkable.

Do not use this for setting up *input* context — that is `context-advisor`. Do not use it to execute or validate an already-compiled graph — that is `/contractgraph:run` and `/contractgraph:validate`.

## Three Modes — default to Hybrid

Pick the mode from what the user actually supplied; only ask if it is genuinely unclear.

| Mode | User supplies | You do |
|------|---------------|--------|
| **Explicit** | Complete, finished contracts | Validate structure, point out gaps, confirm. Add nothing they didn't ask for. |
| **Assisted** | An intent only | Propose the whole contract tree from first principles. |
| **Hybrid** *(default)* | Intent **plus** an example or legacy JSON output | Mine the example for structure, propose the tree, get approval. |

Hybrid is the default because a real legacy output tells you far more about the true required shape than an intent alone, and most users arrive with one.

## Deriving Contracts From a Legacy JSON Output (Hybrid)

A large legacy export (for example a prior Salesforce dump) is a **source of evidence, not a contract.** Treat it as three things at once:

- a list of **candidate subcontracts** — its recurring top-level sections are your node candidates;
- a source of **field structures** — each section's shape becomes that node's output schema;
- a source of **validation requirements** — its required fields, types, enums, and nesting tell you what "valid" means.

The failure mode to avoid: pasting the whole blob into one giant `contract.schema.json`. That produces something no node can own and no verifier can check. Decompose it into per-node schemas, each small enough for one subagent to satisfy and one validator to check.

## Procedure

1. **Identify the mode** from what was supplied.
2. **Name the final output.** State the single artifact the workflow must produce and what "correct" means for it. If you cannot state this, you do not understand the contract yet.
3. **Decompose into nodes.** Each independently-verifiable section of the output becomes one node subcontract. When a section repeats over a set — one analysis per role, one module per topic — model it as *one* node contract applied per item, with the per-item contracts living in a subfolder (e.g. `roles/`). This keeps the design generic instead of hand-listing every item.
4. **Give each node a machine-checkable output schema** (JSON Schema): required fields, types, enums, nesting, and whether unexpected extra fields are allowed. This is what the deterministic validator enforces.
5. **Give each node verification requirements** (the semantic layer): what evidence and provenance a claim needs, the source-quality bar, any freshness window, and the acceptance criteria. A node that only has a schema is incomplete — schema-match alone never means "true".
6. **Infer dependencies from data, not from tree shape.** Node B depends on Node A only when B's inputs require A's *verified* output. Sibling nodes with no data link stay independent so they can run in parallel. The contract's nesting is for human readability; it does not dictate execution order.
7. **Define aggregation and global rules in the main contract:** which subcontracts are required, how accepted node outputs merge into the final artifact, and the cross-section consistency checks that global verification will run.
8. **Present the proposed tree and stop for approval.** Show the tree, a one-line purpose per node, the dependency edges, what you mined from any example, and any open questions. Create nothing yet — the user needs to see the shape before files exist.
9. **After approval, write the bundle** in the layout below, then run structural validation (see `scripts/validate_contract_bundle.py`) and report exactly what passed and what did not.

## Why Every Node Carries Two Rule Sets

A node is accepted only after passing both layers:

```text
node output → deterministic schema validation → semantic / evidence verification → passed?
                                                         ├─ no  → repair or retry THIS node only
                                                         └─ yes → node ACCEPTED
```

The schema catches wrong *shape*; the verifier catches wrong, unsupported, stale, or self-contradictory *content*. A contract that specifies only the schema will happily accept confident nonsense, so every node contract defines both an `outputSchema` and a `verification` block.

## Contract Bundle Layout

This is the layout `scripts/validate_contract_bundle.py` enforces. Use these exact filenames — a bundle with different names fails validation.

```text
contracts/<workflow>/
├── contract.bundle.json          # wiring: main contract + nodes[] + aggregation + globalValidation
├── contract.schema.json          # main contract: final output schema + required aggregation paths
├── common/common.schema.json     # optional: shared $defs reused across node contracts
├── node-contracts/
│   └── <node>.contract.json      # per node: output schema + x-contractgraph block
├── roles/  (or any set dir)      # optional: per-item contracts when one node maps over a set
│   └── <item>.role.json
├── graph.yaml                    # declared dependency edges, cross-checked at compile time
└── policies.json                 # optional: budgets, retries, model routing, concurrency
```

`contract.bundle.json` connects everything:
```json
{
  "bundleId": "study-plan",
  "bundleVersion": "1.0.0",
  "documentType": "ContractGraphContractBundle",
  "mainContract": "contract.schema.json",
  "commonSchema": "common/common.schema.json",
  "runtimeInputs": { "required": ["learnerGoal"], "optional": ["targetDate"], "defaults": {} },
  "nodes": [
    {
      "nodeId": "baseline-assessment",
      "contract": "node-contracts/baseline-assessment.contract.json",
      "required": true,
      "aggregationPath": "baselineAssessment"
    }
  ],
  "aggregation": { "mode": "deterministic", "acceptOnlyVerifiedNodes": true },
  "globalValidation": ["Every required node must be accepted."]
}
```

A **node contract** is a JSON Schema for that node's section, plus an `x-contractgraph` block carrying `aggregationPath`, `dependsOn` (array of node ids — empty if independent), `contextRefs`, and its `verification` requirements (evidence, sources, freshness, acceptance). Its `properties.nodeId.const` must equal the bundle's `nodeId`, and its `x-contractgraph.aggregationPath` must equal the bundle's `aggregationPath` — the validator rejects a mismatch. The **main contract** (`contract.schema.json`) requires every required node's `aggregationPath` at its top level.

## Examples — same method, different domains

**Company research** decomposes into `company-intelligence`, `company-initiatives`, `dsa`, `hld`, `lld`, `behavioral`, and a `resume-analysis` node applied per role (`roles/ai-engineer`, `roles/backend-engineer`, …). `resume-analysis` depends on nothing external; `behavioral` may depend on `company-intelligence` for values to probe — a *data* dependency, not a nesting one.

**Study plan** decomposes into `baseline-assessment`, then `python`, `fastapi`, `databases`, `distributed-systems` (each a topic node), then `evaluation-plan`. The topic nodes depend on `baseline-assessment`'s verified output; `evaluation-plan` depends on the topic nodes. Notice "HLD" and "Python" are just node ids here — the framework code is identical for both workflows.

## Common Mistakes

- **Baking a domain term into the framework.** "HLD" is a node in one contract, not a feature. If your core logic mentions it, move the knowledge into the contract file.
- **Copying a legacy JSON as one contract.** Decompose into per-node schemas instead.
- **Schema-only nodes.** Without a `verification` block a node accepts unsupported claims.
- **Dependencies drawn from tree nesting.** Derive them from which node needs which node's output.
- **Circular dependencies.** Two nodes needing each other means the decomposition is wrong — re-split.
- **Writing files before approval,** or putting private personal facts into a contract (contracts define shape and rules, never the user's data).

## Red Flags — stop and rethink

- You are about to add framework logic named after a domain concept.
- A node's schema has no required fields or no types — it is not machine-validatable.
- The legacy example is collapsing back into one enormous `contract.schema.json`.
- You are creating contract files before the user has approved the tree.
