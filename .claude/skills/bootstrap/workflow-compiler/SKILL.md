---
name: workflow-compiler
description: Use when running /contractgraph:init end to end — compiling a selected contract bundle plus canonical context into runtime/compiled/. Trigger on "compile the workflow", "run init", "rebuild the compiled graph", or whenever contracts, canonical context, policies, or core skills changed since the last compilation. Not for executing an already-compiled graph (that is /contractgraph:run) and not for designing contracts or context themselves (contract-designer, context-advisor).
---

# Workflow Compiler

## Overview

This is the top-level orchestrator for `/contractgraph:init`. It does not design contracts, scaffold context, write skills, or generate agents itself — it sequences the other bootstrap skills and deterministic scripts so the compiled artifacts in `runtime/compiled/` are internally consistent and traceable back to their sources.

## When to Use

- The user invokes `/contractgraph:init` or asks to (re)compile a workflow.
- Any of: the contract bundle, `context/`, `policies.json`, or a core/generated skill changed since the last compilation.

**When NOT to use:** executing a compiled graph (`/contractgraph:run`), or any single sub-step in isolation — delegate those to the specialist skill instead of reimplementing them here.

## Inputs

- A contract bundle path (e.g. `contracts/<workflow>/contract.bundle.json`), its `graph.yaml`, and node contracts.
- `context/` (canonical only — never `context/private/`).
- An optional `policies.json`.

## Outputs

`runtime/compiled/<bundleId>/`: `graph.yaml` (+ canonical `graph.json`), `context-manifest.json`, `contract-manifest.json`, `capability-manifest.json`, `skill-manifest.json`, `agent-manifest.json`, `node-packets/<nodeId>/packet.json`, `compilation-report.md`.

One bundle compiles into exactly one directory named after its `bundleId`. Never write compiled artifacts to the top of `runtime/compiled/` — that layout lets two bundles overwrite each other.

## Procedure

1. Validate the bundle structurally (`scripts/validate_contract_bundle.py`). Stop and report on failure — do not compile a broken bundle.
2. Validate and index canonical context (`scripts/validate_context.py`, `scripts/build_context_manifest.py`).
3. Build `contract-manifest.json` (`scripts/build_contract_manifest.py`) from the bundle's nodes and their schemas.
4. Delegate capability detection to **capability-detector** to produce `capability-manifest.json`.
5. Delegate skill reconciliation to **skill-registry-manager**; it invokes `skill-creator` only for capabilities with no compatible existing skill.
6. Delegate subagent generation, one call per node, to **agent-definition-generator**.
7. Compile the runtime graph from the bundle's `nodes[]` plus each node's `x-contractgraph.dependsOn`, but **verify** those edges against `graph.yaml`'s `dependencies` — do not copy either source blindly; a mismatch is a blocking error to surface, not silently resolve.
8. Validate the compiled graph (`scripts/validate_compiled_graph.py`): no cycles, no orphan nodes, every dependency resolvable.
9. Compile per-node context packets (`scripts/build_node_packets.py`) — one packet per node, carrying only that node's contract, its declared `contextRefs`, dependency-summary refs, skills, and budget.
10. Write all manifests and `compilation-report.md` (what was reused, what was created, what failed, open questions).

## Failure Behavior

Any step failure halts the sequence at that step — do not proceed to compile downstream artifacts from an unvalidated upstream one. Report which step failed and why; do not partially write `runtime/compiled/<bundleId>/`.

## Privacy Restrictions

Never read `context/private/`. Never copy canonical context content verbatim into manifests beyond references and short summaries.

## Reuse Conditions

Skip recompilation when no contract, context, policy, or core skill changed since the last successful run recorded in `compilation-report.md`.

## Regeneration Conditions

Rerun the full sequence when contracts, canonical context, policies, or core skill definitions change.

## Red Flags

- Writing `runtime/compiled/<bundleId>/*` before the corresponding validation step passed.
- Reimplementing capability detection, skill creation, or agent generation inline instead of delegating.
- Trusting `x-contractgraph.dependsOn` or `graph.yaml` alone without cross-checking the other.
