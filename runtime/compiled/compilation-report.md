# Compilation Report — company-research

- **Workflow / bundle:** `company-research` (`contracts/company-research`)
- **Bundle version:** 1.0.0
- **Compiled at:** 2026-07-27
- **Compiler:** `/contractgraph:init` → `workflow-compiler`
- **Status:** ✅ compiled and validated
- **contextManifestHash:** `193d70b738acbf6d33d8e16bd99d31247bdec207b9990b7c56f286ef53046507`
- **contractManifestHash:** `ca1a1ab25db5fa09689a4a8854ca937546818782d9ef6af47281fc5b7ef96454`

## Validation results

| Step | Check | Result |
|------|-------|--------|
| 2 | Bundle structural + reference integrity (`validate_contract_bundle.py`) | ✅ 17 nodes, 5 roles, 0 errors |
| 3 | Canonical context readable + indexed (`validate_context.py`, `build_context_manifest.py`) | ✅ 6 indexed entries |
| 4 | Contract manifest built (`build_contract_manifest.py`) | ✅ |
| 8 | Graph compiled from node `x-contractgraph.dependsOn`, cross-checked vs `graph.yaml` | ✅ **0 dependency conflicts** |
| 9 | Compiled graph integrity (`validate_compiled_graph.py`) | ✅ 17 nodes, 8 layers, no cycles/orphans |

## Artifacts written (`runtime/compiled/`)

| File | Purpose |
|------|---------|
| `context-manifest.json` | Canonical context indexed by source path + SHA-256; `resume/Naresh B A.pdf` flagged `needsSummary`. Private context excluded. |
| `contract-manifest.json` | Node/role inventory with per-contract hashes, aggregation paths, dependencies, multiplicity. |
| `graph.json` | **Canonical** compiled graph: nodes, dependencies, 8 layers, source-verification block. |
| `graph.yaml` | Human rendering of `graph.json` (yaml_lite-parseable). |
| `capability-manifest.json` | 6 domain-neutral capabilities detected across nodes. |
| `skill-manifest.json` | Registry state: 7 bootstrap skills; reusable/generated empty; 6 capability bindings pending. |
| `agent-manifest.json` | 17 node agents + 2 verifiers, with model routing, tools, deps, output paths. |

## Capabilities detected (capability-detector)

`evidence-backed-web-research`, `source-quality-assessment`, `freshness-verification`, `profile-alignment`, `resume-evidence-mapping`, `cross-section-contradiction-detection`.

## Skills — reused vs created (skill-registry-manager)

- **Present (bootstrap):** 7 — context-advisor, contract-designer, workflow-compiler, capability-detector, skill-registry-manager, agent-definition-generator, graph-plan-reviewer.
- **Reused (reusable/generated execution skills):** 0 — the reusable/ and generated/ registries are empty.
- **Created this run:** 0.
- **Pending bindings:** 6 — every detected capability currently has no compatible execution skill. Creation is **intentionally deferred** (project scope: bootstrap first, execution skills later). `/contractgraph:run` will need these bound before nodes can execute.

## Agents generated (agent-definition-generator)

- 17 node agents (one per bundle node) + `section-verifier` (sonnet, Read) + `global-verifier` (opus, Read).
- **Model routing** (per `policies.json`): 16 producers → sonnet; `resources` → haiku (dedup/triage tier); section-verifier → sonnet; global-verifier → opus.
- Every node agent references its real node contract; verifiers reference the bundle/main contract.

## Open questions / known issues

1. **`resume-analysis` multiplicity.** Node contract is single-file (`roleAnalyses minItems 5`) while `graph.yaml` maps the node over roles. Resolved in the agent: run once per role → `runtime/sections/resume-analysis/<roleId>.json`, then a deterministic merge into one schema-valid section. `mapNodes` in `graph.json` is empty because the contract multiplicity reads `single`; `graph.yaml` is authoritative for the map layer.
2. **No deterministic JSON-merge utility yet.** The run plane's aggregation (and the resume-analysis merge above) needs one; the empty `merge_sections.py` placeholder was removed. Must be added before `/contractgraph:run`.
3. **Execution skills pending.** The 6 capability bindings are unresolved until `skill-creator` generates reusable skills.
4. **`evals/` cases not authored.** Directories scaffolded, empty.

## Reuse / regeneration

Re-running `/contractgraph:init` with no change to contracts, context, policies, or core skills reproduces identical `graph.json` and `contractManifestHash` (verified deterministic). Regenerate when any of those inputs change.

## Next command

```
/contractgraph:run companyName="<Target Company>"
```
Requires: the 6 execution skills created + bound, and a deterministic merge utility for aggregation.
