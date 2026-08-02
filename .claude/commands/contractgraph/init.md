---
description: Compile a contract bundle plus canonical context into runtime/compiled/<bundleId>/ (verified graph, manifests, reused/generated skills and subagents). Run before /contractgraph:run.
argument-hint: [optional: bundle path, default contracts/study-plan] [--context <dir>]
allowed-tools: Read, Write, Glob, Grep, Bash, Task, AskUserQuestion
---

Invoke the `workflow-compiler` bootstrap skill (`.claude/skills/bootstrap/workflow-compiler/SKILL.md`) and follow its procedure exactly. Do not reimplement its delegated steps inline.

Bundle path from the user (may be empty): $ARGUMENTS
Default bundle: `contracts/study-plan`
Default context root: `context` — override with `--context <dir>` (the shipped study-plan example uses `--context context/synthetic/study-plan`).

Compiled output for a bundle always lands in `runtime/compiled/<bundleId>/`, never at the top of `runtime/compiled/`. One bundle never overwrites another's manifests.

**Approved-bundle rule:** `/contractgraph:init` never designs or edits contracts. If a bundle already exists on disk, treat it strictly as input to compile — use `/contractgraph:contract` to change a contract.

Steps:
1. Resolve the bundle path (argument, else default). If a different bundle is targeted and it has never been validated, run `/contractgraph:validate <bundle>` first and stop if it fails.
2. Validate the bundle structurally: `python scripts/validate_contract_bundle.py <bundle>`. Stop and report on failure — never compile a broken bundle.
3. Validate and index canonical context: `python scripts/validate_context.py <context-root>`, then `python scripts/build_context_manifest.py <context-root> --out runtime/compiled/<bundleId>/context-manifest.json`. Never read `context/private/`. Summarize large documents by reference; never copy their full content into the manifest.
4. Build `contract-manifest.json` from the bundle's nodes and their schemas: `python scripts/build_contract_manifest.py <bundle> --out-dir runtime/compiled/<bundleId>`.
5. Delegate capability detection to the **capability-detector** skill to produce `capability-manifest.json` from the contract manifest — one capability per distinct node requirement, not per node.
6. Delegate skill reconciliation to the **skill-registry-manager** skill: search `.claude/skills/reusable/` and `.claude/skills/generated/` for compatible verified skills first; invoke `skill-creator` only for capabilities with no match; then evaluate any newly created skill for triggering accuracy, output quality, token overhead, duplication, and privacy leakage before accepting it.
7. Delegate subagent generation to the **agent-definition-generator** skill, one call per node, writing each generated subagent under `.claude/agents/generated/`. Each subagent gets one bounded responsibility, explicit input/output contract, minimum necessary tools, an assigned model (per `policies.json` routing), token/search budget, retry policy, evidence requirements, and stop conditions. A generated subagent may complete its own node; it must never be given authority to declare the whole workflow complete.
8. Compile the runtime graph from the bundle's `nodes[]` plus each node contract's `x-contractgraph.dependsOn`, then cross-check those edges against the bundle's `graph.yaml` `dependencies`. A mismatch between the two sources is a blocking error to surface — never silently prefer one or copy either blindly. The compiled graph must be derived and verified from node contract metadata, not a copy of the source `graph.yaml`.
9. Validate the compiled graph: `python scripts/validate_compiled_graph.py runtime/compiled/<bundleId>/graph.json` — no cycles, no orphan nodes, every dependency resolvable, every node's assigned model/skills/tools present.
10. Compile per-node context packets: `python scripts/build_node_packets.py --bundle <bundle> --compiled runtime/compiled/<bundleId> --out-dir runtime/compiled/<bundleId>/node-packets`. Each packet contains ONLY that node's own contract, its declared `x-contractgraph.contextRefs` (path + SHA-256, never full canonical content), dependency-summary refs (hash placeholders — the real hash is filled in per-run once the dependency is actually accepted), an evidence-registry ref, required skills, and a token/search budget. A node contract with no `contextRefs` declared gets an empty list — never fall back to "all canonical" as a default.
11. Write everything under `runtime/compiled/<bundleId>/`: `graph.yaml` (+ canonical `graph.json`), `context-manifest.json`, `contract-manifest.json`, `capability-manifest.json`, `skill-manifest.json`, `agent-manifest.json`, `node-packets/<nodeId>/packet.json` (per node), and `compilation-report.md` (what was reused, what was created, what failed, open questions).

Any step failure halts the sequence at that step — report which step failed and why, and do not partially write `runtime/compiled/<bundleId>/`.

Skip the full sequence and report "up to date" only when no contract, canonical context, policy, or core/generated skill has changed since the last successful run recorded in `compilation-report.md`.

Compiled artifacts that reference a private context tree are git-ignored by default — never commit a `context-manifest.json` or `compilation-report.md` that embeds paths under `context/canonical/` or `context/private/`.
