---
description: Execute a compiled workflow graph against a runtime input — run ready nodes per the graph, validate/verify each output, retry only failures, aggregate accepted sections, run global verification, and write final artifacts under a unique run directory.
argument-hint: contracts/<bundle> --input "<value>" [--context <dir>] [--roles a,b] [--as-of YYYY-MM-DD] [--force-refresh] [--dry-run]
allowed-tools: Read, Write, Glob, Grep, Bash, Task
---

Requires a prior successful `/contractgraph:init`. Resolve `<bundleId>` from the bundle's `contract.bundle.json`; all compiled artifacts live in `runtime/compiled/<bundleId>/`. If `runtime/compiled/<bundleId>/graph.json` is missing or `runtime/compiled/<bundleId>/compilation-report.md` shows the last compilation failed, stop and tell the user to run `/contractgraph:init <bundle>` first.

Arguments from the user: $ARGUMENTS

Parse: the bundle path (default `contracts/study-plan`); `--input` (required runtime value — the bundle's primary `runtimeInputs.required` field); `--context <dir>` (context root, default `context`; the shipped study-plan example uses `context/synthetic/study-plan`); optional `--roles`, `--resume-refs`, `--job-urls`, `--as-of`, `--force-refresh`, `--dry-run`, `--time-bounded`, `--token-efficient`.

**Concurrency is weighted per class, not one flat cap** (from `policies.json.execution.concurrency.modes`). Every ready node is classified `heavyResearch` (has WebSearch/WebFetch) or `lightSynthesis` (Read/Write only); the reusable `section-verifier`/`global-verifier` subagents classify as `verifier`/`globalVerifier`. Compute admission with `python scripts/schedule_plan.py --bundle <bundle> --compiled runtime/compiled/<bundleId> --mode <mode> --ready <ready-node-ids.json>` — it admits up to each class's cap for the active mode and defers the rest (never silently drops them). `heavyResearch` stays **≤2 in every mode** by policy, including `--time-bounded`: time-bounded only raises `lightSynthesis`/`verifier` throughput, never the research-burst size, to avoid unsafe concurrent web-research spikes. `--token-efficient` lowers every class's cap and reuses agents to process nodes in batches. The legacy `policies.json.execution.concurrencyModes` integer is kept only as a backward-compatible aggregate ceiling — the per-class caps in `concurrency.modes` are authoritative.

## Dry run
If `--dry-run` is present, run `python scripts/dry_run.py --bundle <bundle> --compiled runtime/compiled/<bundleId> --input <input.json>` and present its plan: selected graph + layer order, parallel groups, chosen models, loaded context references, selected skills, expected cache hits, estimated budget, and the files that would be written. **Write nothing else and stop.**

## Full run — the lifecycle
1. **Verify init is current.** Recompute context/contract/policy/skill/agent hashes and compare to the compiled manifests; if anything changed (or `--force-refresh`), tell the user to re-run `/contractgraph:init` (do not silently recompile here).
2. **Create the run dir** `runtime/runs/<run-id>/` with subdirs `manifests/ node-state/ evidence/ summaries/ sections/ verification/ telemetry/raw/ logs/ final/`. Get the real current time with `python scripts/timestamp_now.py` (never estimate or round it by hand) and write it as `run.json`'s `runCreatedAt` (alongside runId, bundleId, `contextDir` — the resolved `--context` value this run actually used, e.g. `context` or `context/synthetic/study-plan` — and input summary) and `input.json`. Recording `contextDir` is what lets `build_derived_context.py` (step 18) tell synthetic demo data apart from real canonical data — the node contracts' own `contextRefs` are contract-relative literals like `canonical/goals.md` that look identical either way. Snapshot the compiled graph to `graph.snapshot.yaml` and copy the compiled manifests (including `node-packets/`) into `manifests/`.
3. **Resolve runtime input** against `runtimeInputs`: required fields present (ask if missing); optional fall back to bundle defaults (e.g. `targetRoles`).
4. **Compute a cache key per node** with `python scripts/cache_key.py --bundle <bundle> --node <id> --input <input.json> --dep-summaries <summaries-hash-map.json> --node-packet runtime/compiled/<bundleId>/node-packets/<id>/packet.json`. The `--dep-summaries` map folds in each upstream dependency's current `summaryHash` (from `summaries/<depNode>.summary.json`) so an unchanged upstream output keeps the key stable and a real change busts it. A node with a valid, fresh cache entry becomes `SKIPPED_CACHE` (unless `--force-refresh`). Never cache invalid/partial/unverified/stale outputs.
5. **Walk the graph by layer.** A node is `READY` only when every `dependsOn` node is `ACCEPTED` or `SKIPPED_CACHE`. Admit ready nodes per the weighted concurrency caps above (`schedule_plan.py`), never a single flat count. Each producer loads **only its compiled `runtime/compiled/<bundleId>/node-packets/<id>/packet.json`** — its own contract, its declared `contextRefs` (load the referenced canonical file only when `loadWhen` is `full-if-exact-evidence-required`; otherwise a summary is enough), its `dependencySummaryRefs` (resolved against `summaries/<depNode>.summary.json`, never the dependency's full section), and its `evidenceRegistryRef` — never the whole bundle, never all canonical context, never an upstream node's full output. Isolate node responsibilities — never assign one agent per tiny field; a node agent owns its whole subcontract. A node the bundle declares as a **map node** (one contract applied over a declared set, e.g. per role) runs once per set member, writing `sections/<nodeId>/<itemId>.json`.
6. **Dispatch each node to its generated subagent** (`.claude/agents/generated/<id>`). Record state transitions in `node-state/<id>.json` under the canonical field name **`state`** (PENDING→READY→RUNNING→STRUCTURAL_FAILED/SEMANTIC_FAILED/EVIDENCE_FAILED/FRESHNESS_FAILED→ACCEPTED/EXHAUSTED/SKIPPED_CACHE — see `generate_trace.py`'s `CANONICAL_STATES`) — never a different key name (`status` is accepted only as a read-time backward-compatible alias, not something new node-state files should use). Capture `nodeStartedAt` when the node transitions to RUNNING and `nodeCompletedAt` when it reaches a terminal state, both via `python scripts/timestamp_now.py` (never hand-estimated). A worker may complete its own node only; it must never approve its own output or declare the whole workflow complete. Node output cites evidence as `evidence: [{ref, claims}]` against the run's shared registry — never an embedded `sources[]` array of full metadata (see step 8).
7. **Structural validation** of each raw output: `python scripts/validate_node_output.py sections/<id>.json --bundle <bundle> --node <id>`. Invalid JSON/shape → `STRUCTURAL_FAILED` → one bounded structural-repair attempt (haiku) → re-validate.
8. **Evidence registration + reference/URL checks.** Fold any newly cited sources into the run's shared registry: `python scripts/source_registry.py --registry runtime/runs/<run-id>/evidence/source-registry.json --sources <node-sources.json> --out-refmap <refmap.json>` — dedups by normalized URL, so the same real-world source always gets the same `SRC_` id no matter which node cites it first, and remap the node's `evidence[].ref` values via the returned refmap before validating. Then `python scripts/validate_references.py sections/<id>.json --bundle <bundle> --evidence-registry runtime/runs/<run-id>/evidence/source-registry.json` (evidenceRefs/contextRefs/roleIds resolve against the EXTERNAL registry, since a section no longer embeds full source metadata) and, when policy requires reachable URLs, `validate_source_urls.py` (prefer Claude Code WebFetch for live reachability).
9. **Independent semantic verification** by a *different* subagent than the producer (`section-verifier`), using the reusable verifier skills. It returns exactly the shape in `scripts/schemas/verifier-verdict.schema.json`: `{nodeId, verifier, status, issues:[{path, issueType, claim?, repairInstruction}], conflicts, confidence}` — it names repair targets by JSON path, it never rewrites or reproduces the node's content (the schema's `additionalProperties:false` rejects any `content`/`section`/`rewrite` field a verifier might try to add). Map failures to `SEMANTIC_FAILED` / `EVIDENCE_FAILED` / `FRESHNESS_FAILED`.
10. **Targeted repair, this node only,** up to `policies.execution.maxRetriesPerNode`: semantic → targeted repair; evidence → source repair (not full regeneration); freshness → refresh only stale claims. Every retry increments attempt metadata. A required node that exhausts retries becomes `EXHAUSTED` and blocks final completion.
11. **Accept** a node (`ACCEPTED`) only when structural + semantic + evidence + freshness all pass. Its `sections/<id>.json` is now immutable for this run. Immediately build its handoff summary: `python scripts/build_dependency_summary.py --bundle <bundle> --node <id> --section sections/<id>.json --out runtime/runs/<run-id>/summaries/<id>.summary.json` — downstream nodes read this compact `{handoff, evidenceRefs, confidence}` summary, never the full section.
12. On refresh of a previously-cached node, run `python scripts/preserve_user_state.py` so user-owned tracking fields are never overwritten by research.
13. **Finalization** — once all required nodes are ACCEPTED and global verification has produced a verdict, automatically invoke finalization:
    ```
    python scripts/finalize_run.py --run runtime/runs/<run-id> --bundle contracts/<bundleId>
        [--compiled runtime/compiled/<bundleId>]
        [--context-root <the resolved --context value from step 2>]
        [--telemetry-source <type> <file>]
    ```
    `finalize_run.py` (see `/contractgraph:finalize` and `scripts/finalize_run.py`) runs ALL of the following deterministically with no model calls:
    - backs up the run to `.migrations/<NNN>-pre-finalize/` before any writes,
    - confirms every required node has a section file,
    - aggregates accepted sections into `final/final.json`,
    - validates `final.json` against the bundle schema and references,
    - confirms global verification exists (does not re-run it),
    - scores and buckets sources per node via `source_scoring.py`,
    - validates source metadata completeness (title, url, type; rejects placeholders),
    - checks domain leakage (flags out-of-contract references without labelled-comparison context),
    - builds derived context with privacy classification via `build_derived_context.py`,
    - normalizes telemetry into `final/cost.json` (never fabricates missing per-node values),
    - generates `trace.json` via `generate_trace.py`,
    - writes `final/verification-summary.json`,
    - writes `final/report.md`,
    - marks `run.json` with terminal state: `COMPLETED` or `FINALIZATION_FAILED`.
14. **Report the finalization result.** Print `finalize_run.py`'s output. If `COMPLETED`, all checks passed. If `FINALIZATION_FAILED`, list the failed check names. The run is not complete until `COMPLETED`.
15. **Optional TOON transport, benchmark-config-gated only.** If (and only if) the active run config sets `toon: "selective"` (never in normal/default execution), sections may encode the arrays listed in `policies.json.tokenEfficiency.toon.eligibleArrays` as TOON instead of JSON for the wire/storage transport, per the measured decision in `runtime/compiled/<bundleId>/toon-benchmark.json`. The node's OWN validated output (what `validate_node_output.py` checks) is still canonical JSON — TOON is a transport encoding around it, applied via `scripts/toon_codec.py` with `enable_toon=True`, never a schema change. TOON is applied after finalization; it does not block completion.

The run is complete only when:
- `run.json` shows `runStatus: COMPLETED`
- `final/final.json` exists and validates
- `final/verification-summary.json` exists
- `final/report.md` exists
- `final/cost.json` exists
- `final/derived-context.json` exists
- `evidence/source-governance.json` exists
- `trace/trace.json` exists

Report which nodes ran, which were cached, which retried, and the final verification verdict. If any required node is `EXHAUSTED` or finalization fails, report the run **incomplete** with the specific node(s) and reason — never report completion. Private outputs stay under `runtime/runs/` (git-ignored); never write them into public example directories.
