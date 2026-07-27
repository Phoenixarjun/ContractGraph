# Graph Compilation

`/contractgraph:init` invokes the `workflow-compiler` bootstrap skill, which owns the full compile sequence below. Any step failure halts compilation at that step — the sequence never partially writes `runtime/compiled/`.

## Compile Sequence

1. Resolve the bundle path (argument, or default `contracts/company-research`). If it targets `contracts/company-research`, treat it as an **approved bootstrap exception** — never redesign or regenerate its contracts, only compile from it. A never-validated non-default bundle must pass `/contractgraph:validate` first.
2. Structurally validate the bundle (`scripts/validate_contract_bundle.py`) — stop on failure.
3. Validate and index canonical context (`scripts/validate_context.py`, then `scripts/build_context_manifest.py`) → `context-manifest.json`. Never read `context/private/`; summarize large documents by reference.
4. Build `contract-manifest.json` from the bundle's nodes and schemas (`scripts/build_contract_manifest.py`).
5. Delegate to `capability-detector` → `capability-manifest.json`, one entry per distinct capability (a `map` node contributes one entry, not one per item).
6. Delegate to `skill-registry-manager` → search `.claude/skills/reusable/` and `.claude/skills/generated/` for a compatible verified skill first; call `skill-creator` only for unmatched capabilities; evaluate every new/regenerated skill (triggering, false triggering, output quality, token overhead, duplication, privacy leakage) before acceptance.
7. Delegate to `agent-definition-generator`, once per node → `.claude/agents/generated/<nodeId>.md`. Each subagent gets: one bounded responsibility, explicit input/output contract, minimum necessary tools, an assigned model (`policies.json` routing), token/search budget, retry policy, evidence requirements, and stop conditions. A subagent may complete its own node; it may never declare the whole workflow complete.
8. Compile the runtime graph from the bundle's `nodes[]` plus each node contract's `x-contractgraph.dependsOn` — then **cross-check** those edges against the bundle's own `graph.yaml` `dependencies`. A mismatch is a blocking error to surface, not silently resolved by preferring one source or copying either blindly.
9. Validate the compiled graph (`scripts/validate_compiled_graph.py`) — no cycles, no orphan nodes, every dependency resolvable, every node's assigned model/skills/tools present.
10. Write `graph.yaml` (+ canonical `graph.json`), `context-manifest.json`, `contract-manifest.json`, `capability-manifest.json`, `skill-manifest.json`, `agent-manifest.json`, and `compilation-report.md`.

`graph-plan-reviewer` runs as the last adversarial gate before compilation is reported complete: it walks dependency edges for cycles, checks every agent's granted tools against what its assigned skills actually require, flags Opus routing without justification, catches unresolved duplication in `skill-manifest.json`, scans for privacy leaks, and confirms every node has both a structural and a semantic verification path. It never fixes issues itself — it reports blockers/warnings back for repair, and a `fail` verdict stands regardless of warning count.

Init reruns fully only when a contract, canonical context file, policy, or core/generated skill has changed since the last successful `compilation-report.md`; otherwise it reports "up to date."

## Layers and Parallelism

`graph.yaml` expresses the compiled plan as ordered layers. From `contracts/company-research/graph.yaml`:

```yaml
layers:
  - id: foundation
    parallel: [company-intelligence, role-intelligence]
  - id: company-and-process
    parallel: [company-initiatives, interview-process, compensation-location]
  - id: preparation-and-alignment
    parallel: [dsa, cs-fundamentals, domain-knowledge, hld, lld, behavioral, profile-alignment]
  - id: candidate-evidence
    parallel: [project-deep-dive, networking-referral]
  - id: resume-map
    map: { node: resume-analysis, over: configuredRoles }
  - id: strategy
    parallel: [application-strategy, resources]
  - id: completion
    sequence: [deterministic-merge, main-schema-validation, global-verification]
```

A node is ready only when every node in its `dependsOn` is **ACCEPTED** (not merely produced). Within a ready layer, independent nodes run in parallel, capped by `policies.json`'s `execution.maxParallelNodes`. A `map` entry applies one node contract over a runtime-resolved set (e.g. `configuredRoles`) rather than requiring N hand-authored nodes.

## Node Completion Model

```text
node output → structural validation → semantic verification → accept?
                                              │
                                    ├─ no  → repair/retry THIS node only (up to maxRetriesPerNode)
                                    └─ yes → ACCEPTED
```

- **Structural validation** — deterministic JSON Schema check against the node's `outputSchema`.
- **Semantic verification** — a verifier subagent confirms evidence supports claims, sources are credible, freshness requirements are met, profile alignment cites canonical context, contradictions are flagged, and unsupported claims are rejected. The producing subagent can never approve its own output (`workerCannotSelfApprove`).
- A node is **ACCEPTED** only when both layers pass. Retries target only the failed node — never a full restart — and never re-run a node that already passed.

## Deterministic Aggregation

Once all required nodes in a layer are ACCEPTED, `scripts/merge_sections.py` merges only accepted outputs per the bundle's `aggregation` rules: dedupe sources by `canonicalUrl`/`sourceRef`, preserve canonical keys, reject duplicate ownership, build a global source registry, and respect `stateOwnership` (e.g. never let a research refresh overwrite non-empty user-owned fields like `masteryStatus` or `userNotes`).

## Global Verification

After merge, an Opus-routed global verification pass checks:

- every required subcontract is present and accepted,
- every `evidenceRef` resolves to the global source registry,
- every `contextRef` resolves to the canonical context manifest,
- every `roleId` resolves to a configured role file,
- cross-section claims are consistent and rankings are justified,
- no candidate experience is invented and no research claim is represented as canonical user truth,
- the final artifact validates against the main contract's `finalOutputSchema`.

On failure, verification routes back to repair only the implicated node(s) — never a full workflow restart. The workflow is complete only when global verification passes; a run that exhausts retries without passing is reported incomplete, with the specific failing node(s) named.

## Deterministic Scripts Involved

`validate_contract_bundle.py`, `validate_context.py`, `build_context_manifest.py`, `build_contract_manifest.py`, `validate_compiled_graph.py`, `merge_sections.py`, `hash_content.py`. None of these call a model API, implement agent reasoning, or choose research conclusions — they enforce shape, compute hashes/cache keys, and merge already-accepted JSON.
