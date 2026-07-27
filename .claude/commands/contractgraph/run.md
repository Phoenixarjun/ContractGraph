---
description: Execute a compiled workflow graph against a runtime input — run ready nodes per the graph, validate/verify each output, retry only failures, aggregate accepted sections, run global verification, and write final artifacts under a unique run directory.
argument-hint: contracts/<bundle> --input "<value>" [--roles a,b] [--resume-refs ...] [--job-urls ...] [--as-of YYYY-MM-DD] [--force-refresh] [--dry-run]
allowed-tools: Read, Write, Glob, Grep, Bash, Task
---

Requires a prior successful `/contractgraph:init`. If `runtime/compiled/graph.json` is missing or `runtime/compiled/compilation-report.md` shows the last compilation failed, stop and tell the user to run `/contractgraph:init` first.

Arguments from the user: $ARGUMENTS

Parse: the bundle path (default `contracts/company-research`); `--input` (required runtime value — for company-research this is the company name); optional `--roles`, `--resume-refs`, `--job-urls`, `--as-of`, `--force-refresh`, `--dry-run`.

## Dry run
If `--dry-run` is present, run `python scripts/dry_run.py --bundle <bundle> --compiled runtime/compiled --input <input.json>` and present its plan: selected graph + layer order, parallel groups, chosen models, loaded context references, selected skills, expected cache hits, estimated budget, and the files that would be written. **Write nothing else and stop.**

## Full run — the lifecycle
1. **Verify init is current.** Recompute context/contract/policy/skill/agent hashes and compare to the compiled manifests; if anything changed (or `--force-refresh`), tell the user to re-run `/contractgraph:init` (do not silently recompile here).
2. **Create the run dir** `runtime/runs/<run-id>/` with subdirs `manifests/ node-state/ evidence/ sections/ verification/ logs/ final/`. Write `run.json` (runId, bundleId, startedAt, input summary) and `input.json`. Snapshot the compiled graph to `graph.snapshot.yaml` and copy the compiled manifests into `manifests/`.
3. **Resolve runtime input** against `runtimeInputs`: required fields present (ask if missing); optional fall back to bundle defaults (e.g. `targetRoles`).
4. **Compute a cache key per node** with `python scripts/cache_key.py --bundle <bundle> --node <id> --input <input.json>`. A node with a valid, fresh cache entry becomes `SKIPPED_CACHE` (unless `--force-refresh`). Never cache invalid/partial/unverified/stale outputs.
5. **Walk the graph by layer.** A node is `READY` only when every `dependsOn` node is `ACCEPTED` or `SKIPPED_CACHE`. Run ready nodes in parallel, capped at `policies.execution.maxParallelNodes`. `resume-analysis` is a map node — run it once per configured role, writing `sections/resume-analysis/<roleId>.json`.
6. **Dispatch each node to its generated subagent** (`.claude/agents/generated/<id>`). Record state transitions in `node-state/<id>.json` (PENDING→READY→RUNNING→…). A worker may complete its own node only; it must never approve its own output or declare the whole workflow complete.
7. **Structural validation** of each raw output: `python scripts/validate_node_output.py sections/<id>.json --bundle <bundle> --node <id>`. Invalid JSON/shape → `STRUCTURAL_FAILED` → one bounded structural-repair attempt (haiku) → re-validate.
8. **Reference + URL checks:** `validate_references.py` (evidenceRefs/contextRefs/roleIds resolve) and, when policy requires reachable URLs, `validate_source_urls.py` (prefer Claude Code WebFetch for live reachability).
9. **Independent semantic verification** by a *different* subagent than the producer (`section-verifier`), using the reusable verifier skills. It returns `{status, issues, repairInstructions, unsupportedClaims, staleClaims, conflicts, confidence}` — it names repair targets, it does not rewrite the node. Map failures to `SEMANTIC_FAILED` / `EVIDENCE_FAILED` / `FRESHNESS_FAILED`.
10. **Targeted repair, this node only,** up to `policies.execution.maxRetriesPerNode`: semantic → targeted repair; evidence → source repair (not full regeneration); freshness → refresh only stale claims. Every retry increments attempt metadata. A required node that exhausts retries becomes `EXHAUSTED` and blocks final completion.
11. **Accept** a node (`ACCEPTED`) only when structural + semantic + evidence + freshness all pass. Its `sections/<id>.json` is now immutable for this run.
12. On refresh of a previously-cached node, run `python scripts/preserve_user_state.py` so user-owned tracking fields are never overwritten by research.
13. **Deterministic aggregation** once all required nodes are terminal-OK: `python scripts/merge_verified_sections.py --bundle <bundle> --sections runtime/runs/<run-id>/sections --out runtime/runs/<run-id>/final/final.json --run-meta <run-meta.json>` (merges only accepted sections; builds the global source registry; rejects duplicate ownership).
14. **Validate the final artifact:** `python scripts/validate_final_output.py final/final.json --bundle <bundle>` and `validate_references.py` on the final.
15. **Global verification (Opus)** via the `global-verifier` agent against `contract.bundle.json.globalValidation[]` and the main contract. Pass compact evidence/conflict summaries, not raw full-node dumps. On failure, route repair to the implicated node(s) only — do not restart the run.
16. **Write final artifacts** to `final/`: `final.json`, `report.md`, `trace.json` (`python scripts/generate_trace.py --run runtime/runs/<run-id>`), `cost.json` (per-node model + estimated tokens), `validation-report.json`.
17. **Derived context** — only from verified outputs — to `final/derived-context.json` (and, if the user opts in, `context/derived/`) with originating runId, node, source contract version, contextRefs, evidenceRefs, confidence, creation date, freshness date, privacy classification. Never overwrite canonical; never convert research into user-owned truth.

Report which nodes ran, which were cached, which retried, and the final verification verdict. If any required node is `EXHAUSTED` or global verification fails after retries, report the run **incomplete** with the specific node(s) and reason — never report completion. Private outputs stay under `runtime/runs/` (git-ignored); never write them into public example directories.
