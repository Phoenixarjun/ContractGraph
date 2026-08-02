# Compilation Report — study-plan

- **Workflow / bundle:** `study-plan` (`contracts/study-plan`)
- **Bundle version:** 1.0.0
- **Compiled at:** 2026-07-28
- **Compiler:** `/contractgraph:init` → `workflow-compiler`
- **Status:** ✅ compiled and validated
- **contextManifestHash:** `4ab3d6ff0ed3d0f5610e2fa9d3660b883387ea004be5374a280a73f51945c60d`
- **contractManifestHash:** `3336d3089697bb2c6b9e4a7e00afcc4707d794757bb0bbb682f3ca9c1e860602`

## Validation results

| Step | Check | Result |
|------|-------|--------|
| 2 | Bundle structural + reference integrity (`validate_contract_bundle.py`) | ✅ 6 nodes, 0 roles, 0 errors |
| 3 | Canonical context readable + indexed (`validate_context.py`, `build_context_manifest.py`) | ✅ 3 indexed entries (`context/synthetic/study-plan`) |
| 4 | Contract manifest built (`build_contract_manifest.py`) | ✅ |
| 8 | Graph compiled from node `x-contractgraph.dependsOn`, cross-checked vs `graph.yaml` | ✅ **0 dependency conflicts** |
| 9 | Compiled graph integrity (`validate_compiled_graph.py`) | ✅ 6 nodes, 3 layers (1 → 4 → 1 diamond), no cycles/orphans |
| — | Node-specific context packets (`build_node_packets.py`) | ✅ 6 packets — baseline-assessment carries 3 canonical refs, the 4 topic nodes carry 1 (`canonical/preferences.md`), evaluation-plan carries 1 (`canonical/goals.md`); never "all canonical". |
| — | TOON eligibility benchmark (`toon_benchmark.py`) | ✅ all 4 eligible arrays (`resources`, `milestones`, `checkpoints`, `sourceRegistry`) clear the threshold on representative fixtures — see `toon-benchmark.json`. TOON stays disabled for normal runtime regardless. |

## Artifacts written (`runtime/compiled/study-plan/`)

| File | Purpose |
|------|---------|
| `context-manifest.json` | Context indexed by source path + SHA-256, scoped to `context/synthetic/study-plan` (the synthetic learner profile — never a private context tree). |
| `contract-manifest.json` | Node inventory with per-contract hashes, aggregation paths, dependencies, multiplicity. |
| `graph.json` | **Canonical** compiled graph: 6 nodes, dependencies, 3 layers, source-verification block. |
| `capability-manifest.json` | 1 capability detected across nodes (`evidence-backed-web-research`). |
| `skill-manifest.json` | Registry state: 7 bootstrap skills; 1 reusable skill bound to the 5 research nodes; `evaluation-plan` correctly requires none (pure synthesis over already-verified topic tracks, no web tools). |
| `agent-manifest.json` | 6 node agents, model routing, tools, deps, output paths. |
| `node-packets/<nodeId>/packet.json` | Per-node execution packet (own contract only, declared context refs by path+hash, dependency-summary refs, evidence-registry ref, skills, budget) — `build_node_packets.py`. |
| `toon-benchmark.json` | TOON size/losslessness/schema-validity decision per eligible array, measured against `evals/fixtures/toon-samples/`. |

## Capabilities detected (capability-detector)

`evidence-backed-web-research` — required by `baseline-assessment`, `python`, `fastapi`, `databases`, `distributed-systems`.

## Skills — reused vs created (skill-registry-manager)

- **Present (bootstrap):** 7 — context-advisor, contract-designer, workflow-compiler, capability-detector, skill-registry-manager, agent-definition-generator, graph-plan-reviewer.
- **Reused (reusable):** 1 — `evidence-backed-web-research`, bound to the 5 web-research nodes.
- **Created this run:** 0.
- **Pending bindings:** 0.

## Agents generated (agent-definition-generator)

- 6 node agents (one per bundle node), all model `sonnet` per `policies.json.models.research.primary`.
- **Concurrency class** (per `policies.json.execution.concurrency`): `baseline-assessment`, `python`, `fastapi`, `databases`, `distributed-systems` → `heavyResearch` (WebSearch+WebFetch); `evaluation-plan` → `lightSynthesis` (Read/Write only).
- Every node agent references its real node contract.

## Token-efficiency properties of this compilation

1. **Node contracts now carry `evidence: [{ref, claims}]`** instead of embedded `sources: [EvidenceSource]` — full source metadata lives once in the run's `evidence/source-registry.json` (`source_registry.py`), not duplicated per node.
2. **`x-contractgraph.contextRefs`** declares exactly which canonical files each node needs (never "all canonical" as a fallback).
3. **`data.handoffSummary`** (optional, bounded: `headline` + up to 5 `keyFacts`) lets downstream nodes consume a compact summary (`build_dependency_summary.py`) instead of the full upstream section.
4. **Weighted concurrency** (`policies.json.execution.concurrency`) replaces the flat `maxParallelNodes` cap with per-class quotas; `heavyResearch` stays ≤2 in every mode, including `--time-bounded`.
5. **TOON stays disabled for runtime**; `toon-benchmark.json` documents which arrays the *optimized benchmark config only* may encode as TOON.

## Open questions / known issues

1. **Skill fit for `evaluation-plan`.** No existing reusable skill targets "tie N verified topic tracks to checkpoints plus a final assessment" specifically, so the node runs on its node contract and policies alone (`requiredSkills: []`). This is the expected shape for a pure-synthesis node with no web tools.
2. **`toon-benchmark.json` measures representative fixtures, not a live run's actual arrays.** Model-output quality under TOON is explicitly marked `pending` — it is only knowable from an executed benchmark run, not from a deterministic script.

## Reuse / regeneration

Re-running `/contractgraph:init` with no change to contracts, context, policies, or core skills reproduces identical `graph.json` and `contractManifestHash`. Regenerate when any of those inputs change.

## Next command

```
/contractgraph:run contracts/study-plan --context context/synthetic/study-plan \
  --input "backend engineering within 6 months, Python web services"
```

For the controlled baseline vs. optimized benchmark invocation, see
`docs/opencode-benchmark.md`.
