# Contract Model

A contract describes the **required final output** and how a machine and a verifier decide it is correct. ContractGraph's core understands only four things: a main contract, its node subcontracts, the dependencies between them, and the rules for validating and aggregating them. Everything domain-specific — "baseline assessment", "fastapi", "databases", or any other concept — is just a node name and schema inside one particular contract, never framework logic.

## Main Contract + Node Subcontracts

A main contract may contain multiple subcontracts, one per independently-verifiable section of the output:

```text
Study Plan Contract
├── Baseline Assessment
├── Python Track
├── FastAPI Track
├── Databases Track
├── Distributed Systems Track
└── Evaluation Plan
```

- Each subcontract becomes one node, or one subtree when a section repeats over a set (e.g. per-track or per-role analysis applied via a `map` layer — not N hand-written nodes).
- Contract *tree* structure does not automatically define execution order. Dependencies are inferred from data needs, not nesting.
- Independent nodes may execute in parallel; dependent nodes wait for verified prerequisites.
- The final output must conform exactly to the main contract's `finalOutputSchema`.
- A node is complete only when its subcontract validates structurally **and** its verifier passes semantically.

## Bundle Wiring

A bundle on disk (e.g. `contracts/study-plan/`) contains:

```text
contracts/<workflow>/
├── contract.bundle.json          # wiring: main contract, roles/sets, node list, aggregation + global rules
├── contract.schema.json          # final output schema
├── common/common.schema.json     # shared $defs (RoleApplicability, EvidenceSource, NodeVerification, ...)
├── node-contracts/
│   └── <node>.contract.json      # per node: outputSchema + x-contractgraph block
├── roles/ (or any set dir)       # per-item contracts when a node applies over a set
├── graph.yaml                    # compiled layers + dependency edges (verified, not blindly trusted)
└── policies.json                 # model routing, evidence rules, freshness windows
```

`contract.bundle.json` names every node once, with its contract path and `aggregationPath` — the key under which the node's accepted output is merged into the final artifact (e.g. `baseline-assessment` → `baselineAssessment`).

## The `x-contractgraph` Block

Every node contract carries an `x-contractgraph` extension alongside its JSON Schema `properties`. From `node-contracts/baseline-assessment.contract.json`:

```json
"x-contractgraph": {
  "purpose": "Assess the learner's current level and gaps from canonical goals/knowledge.",
  "aggregationPath": "baselineAssessment",
  "contextRefs": [
    "canonical/goals.md",
    "canonical/knowledge.md",
    "canonical/preferences.md"
  ],
  "dependsOn": [],
  "parallelizableWhenReady": true,
  "multiplicity": "single",
  "completionRules": [
    "Output validates against this schema.",
    "status must be complete to accept.",
    "Every learning claim cites a resource.",
    "Producer cannot self-approve."
  ]
}
```

| Field | Meaning |
|---|---|
| `purpose` | The node's single bounded responsibility — copied verbatim into its generated subagent, never paraphrased broader. |
| `aggregationPath` | Where this node's accepted output lands in the merged final artifact. |
| `dependsOn` | Node IDs this node's inputs actually require (data dependency, not tree position). Empty means foundation-layer, parallelizable immediately. |
| `multiplicity` | `single` — one output per node — or `map` — one output per item in a set (e.g. per role), driven by a `map` layer in `graph.yaml`. |
| `completionRules` | The acceptance bar: schema validity, status, evidence resolution, self-approval prohibition, and the semantic-before-aggregation ordering. Copied verbatim into the agent definition — never softened. |

`dependsOn` here is the source of truth the compiler cross-checks against `graph.yaml`'s `dependencies` map — see [graph-compilation.md](graph-compilation.md).

## Explicit / Assisted / Hybrid Contract Creation

The `contract-designer` bootstrap skill supports three modes, chosen from what the user actually supplies:

| Mode | User supplies | Skill does |
|---|---|---|
| **Explicit** | Complete, finished contracts | Validate structure, point out gaps, confirm — add nothing unrequested |
| **Assisted** | An intent only | Propose the whole contract tree from first principles |
| **Hybrid** *(default)* | Intent **plus** an example or legacy JSON output | Mine the example for candidate subcontracts, field structures, and validation requirements; propose the tree |

In every mode, the skill **stops for approval** before writing any file — it presents the bundle layout, one-line purpose per node, dependency edges, and open questions first. A legacy JSON export is treated as evidence to decompose into per-node schemas, never copied wholesale into one giant contract.

## Common Mistakes

- Baking a domain term into framework logic instead of a contract file.
- Collapsing a legacy export back into one enormous main contract.
- A node schema with no `verification`/`completionRules` — schema-match alone can accept confident nonsense.
- Drawing dependencies from tree nesting instead of actual data needs.
- Circular dependencies — a signal the decomposition itself is wrong.
- Writing contract files before the user has approved the proposed tree.
