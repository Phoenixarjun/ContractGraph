---
description: Execute a compiled workflow graph against a runtime input — resolve dependencies, run ready nodes, validate and verify each output, retry only failures, aggregate accepted nodes, run global verification, and write final outputs and traces.
argument-hint: [runtime input, e.g. companyName="Acme" targetRoles=ai-engineer,backend-engineer]
allowed-tools: Read, Write, Glob, Grep, Bash, Task
---

Requires a prior successful `/contractgraph:init`. If `runtime/compiled/graph.json` does not exist, or `compilation-report.md` shows the last compilation failed, stop and tell the user to run `/contractgraph:init` first.

Runtime input from the user: $ARGUMENTS

Steps:
1. Load `runtime/compiled/graph.json`, `context-manifest.json`, `contract-manifest.json`, `agent-manifest.json`, and the bundle's `policies.json`.
2. Resolve runtime input against the bundle's `runtimeInputs`: required fields (e.g. `companyName`) must be present — ask if missing; optional fields fall back to the bundle's declared defaults (e.g. `targetRoles`).
3. Compute a cache key per node from contract version, context hash, runtime input, node version, and skill version. Skip only nodes with a valid cache entry; report what was skipped and why.
4. Walk the graph layer by layer as compiled (mirroring `graph.yaml`'s `layers`/`dependencies`): a node is ready only when every node in its `dependsOn` is ACCEPTED. Within a ready layer, run independent nodes in parallel, capped at `policies.execution.maxParallelNodes`.
5. Dispatch each ready node to its generated subagent (`.claude/agents/generated/`). A subagent may complete and report its own node only — it must never declare the overall workflow complete or approve its own output (`workerCannotSelfApprove`).
6. Validate every node output in two layers before acceptance:
   - **Structural**: JSON Schema check against the node's `outputSchema` via the deterministic validator.
   - **Semantic**: dispatch to a verifier subagent — evidence supports claims, sources are credible, freshness requirements are met, profile alignment cites canonical context, contradictions are flagged, unsupported claims are rejected.
   A node is ACCEPTED only when both layers pass.
7. On failure, retry only that node (repair, not full restart), up to `policies.execution.maxRetriesPerNode`. Never retry nodes that already passed.
8. Preserve raw evidence and per-node traces under `runtime/traces/` and `runtime/sections/` as they are produced, regardless of final acceptance.
9. Once all required nodes for a layer are ACCEPTED, run deterministic aggregation (`scripts/merge_sections.py`) — merge only ACCEPTED node outputs per the bundle's `aggregation` rules (dedupe sources, preserve canonical keys, respect `stateOwnership`).
10. After all required nodes are ACCEPTED and merged, run global verification (Opus): every required subcontract present, cross-section claims consistent, references resolve, rankings justified, final artifact validates against the main contract's `finalOutputSchema`. On failure, route back to repair only the implicated node(s) — do not restart the whole run.
11. On global verification pass, write final output(s) under `runtime/outputs/`, the run trace, and — only from verified results — any new derived context under `context/derived/` with source run ID, generating node, creation time, evidence references, confidence, freshness, and contract version. Never overwrite canonical context.

Report exactly which nodes ran, which were cached, which retried, and the final verification result. If global verification fails after exhausting retries, report the run as incomplete with the specific failing node(s) and reason — do not report completion.
