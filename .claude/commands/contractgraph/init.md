---
description: Compile a contract bundle plus canonical context into runtime/compiled/ (verified graph, manifests, reused/generated skills and subagents). Run before /contractgraph:run.
argument-hint: [optional: bundle path, default contracts/company-research]
allowed-tools: Read, Write, Glob, Grep, Bash, Task, AskUserQuestion
---

Invoke the `workflow-compiler` bootstrap skill (`.claude/skills/bootstrap/workflow-compiler/SKILL.md`) and follow its procedure exactly. Do not reimplement its delegated steps inline.

Bundle path from the user (may be empty): $ARGUMENTS
Default bundle: `contracts/company-research`

**Approved-bundle exception:** `contracts/company-research` is an already-approved bootstrap bundle. If the resolved bundle path is (or resolves to) `contracts/company-research`, do NOT redesign, regenerate, or otherwise modify its contracts — treat it strictly as input to compile.

Steps:
1. Resolve the bundle path (argument, else default). If a different bundle is targeted and it has never been validated, run `/contractgraph:validate <bundle>` first and stop if it fails.
2. Validate the bundle structurally: `python scripts/validate_contract_bundle.py <bundle>`. Stop and report on failure — never compile a broken bundle.
3. Validate and index canonical context: `python scripts/validate_context.py context`, then `python scripts/build_context_manifest.py context` to produce `context-manifest.json`. Never read `context/private/`. Summarize large documents by reference; never copy their full content into the manifest.
4. Build `contract-manifest.json` from the bundle's nodes and their schemas: `python scripts/build_contract_manifest.py <bundle>`.
5. Delegate capability detection to the **capability-detector** skill to produce `capability-manifest.json` from the contract manifest — one capability per distinct node requirement, not per node.
6. Delegate skill reconciliation to the **skill-registry-manager** skill: search `.claude/skills/reusable/` and `.claude/skills/generated/` for compatible verified skills first; invoke `skill-creator` only for capabilities with no match; then evaluate any newly created skill for triggering accuracy, output quality, token overhead, duplication, and privacy leakage before accepting it.
7. Delegate subagent generation to the **agent-definition-generator** skill, one call per node, writing each generated subagent under `.claude/agents/generated/`. Each subagent gets one bounded responsibility, explicit input/output contract, minimum necessary tools, an assigned model (per `policies.json` routing), token/search budget, retry policy, evidence requirements, and stop conditions. A generated subagent may complete its own node; it must never be given authority to declare the whole workflow complete.
8. Compile the runtime graph from the bundle's `nodes[]` plus each node contract's `x-contractgraph.dependsOn`, then cross-check those edges against the bundle's `graph.yaml` `dependencies`. A mismatch between the two sources is a blocking error to surface — never silently prefer one or copy either blindly. The compiled graph must be derived and verified from node contract metadata, not a copy of the source `graph.yaml`.
9. Validate the compiled graph: `python scripts/validate_compiled_graph.py runtime/compiled/graph.json` — no cycles, no orphan nodes, every dependency resolvable, every node's assigned model/skills/tools present.
10. Write `runtime/compiled/graph.yaml` (+ canonical `graph.json`), `context-manifest.json`, `contract-manifest.json`, `capability-manifest.json`, `skill-manifest.json`, `agent-manifest.json`, and `compilation-report.md` (what was reused, what was created, what failed, open questions).

Any step failure halts the sequence at that step — report which step failed and why, and do not partially write `runtime/compiled/`.

Skip the full sequence and report "up to date" only when no contract, canonical context, policy, or core/generated skill has changed since the last successful run recorded in `compilation-report.md`.
