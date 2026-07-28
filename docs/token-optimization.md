# Token Optimization

[token-efficiency.md](token-efficiency.md) states the standing policy (model routing, caching inputs, "no full transcripts between nodes", format). This doc covers the mechanisms added to actually enforce those rules with measured artifacts, not just prose — node-specific context packets, compact cross-node handoffs, evidence deduplication, issue-only verification, and weighted concurrency. See [optimization-plan.md](optimization-plan.md) for the full architecture rationale these were built from.

## The waste this fixes (measured, not assumed)

A real completed company-research run was inspected before any of this was built:

- **462 fully-described source objects, 1048 references, across 17 sections** — the same real-world URL re-described under a different per-node ID in every section that cited it (e.g. two different `SRC_*` ids for the same page). The **final** artifact already proves the fix pattern: it consolidates into one 172-entry `sourceRegistry` and drops per-section `sources[]` entirely. The waste was entirely in the intermediate handoffs, upstream of that final merge.
- **No per-node context packet existed.** `init` wrote manifests and references; `run` said "pass compact structured outputs between nodes" but never defined *which* canonical files or *which* upstream sections a given producer should actually load.
- **Verification was already issue-only and compact** — nothing to fix there, only to formalize with a schema that structurally forbids a verifier from smuggling in a rewrite.
- **Concurrency was one flat integer per mode** — no distinction between a node burning through web searches and a node doing pure synthesis over already-verified data.

## 1. Node-specific context packets

`scripts/build_node_packets.py` (an init-time step, reusing `dry_run.py`'s plan-assembly logic) compiles `runtime/compiled/node-packets/<nodeId>/packet.json` per node containing **only**:

- that node's own contract reference + hash (never the whole bundle),
- its declared `x-contractgraph.contextRefs` — canonical file paths **by path + SHA-256**, never by content. A node contract with no `contextRefs` gets an empty list; there is no "load all canonical" fallback. A declared ref that isn't in the indexed context manifest (file missing, or `build_context_manifest.py` not yet re-run after adding it) blocks compilation with a clear per-node/per-path error instead of emitting an invalid packet with a null hash — `node-packet.schema.json` requires `sha256` as a non-null string, so this is a compile-time failure, not a silent gap. See `t_node_packet_missing_context_ref`.
- dependency-summary refs (a `{depNode, summaryHash}` pair — see §2), never a full upstream section,
- an evidence-registry reference (see §3), never inline source objects,
- required skills, a token/search budget, and output instructions.

For study-plan: `baseline-assessment` (the only node reading raw canonical facts directly) declares all 3 canonical files; the four topic nodes each declare only `canonical/preferences.md` (resource-selection preference — the learner's stated level/gaps are already digested into `baseline-assessment`'s handoff summary, so re-reading `goals.md`/`knowledge.md` downstream would be pure duplication); `evaluation-plan` declares `canonical/goals.md` to tie its final assessment back to the stated goal.

## 2. Compact handoffs via cacheable dependency summaries

`scripts/build_dependency_summary.py` runs immediately after a node is `ACCEPTED`, extracting its (optional, producer-authored, schema-bounded) `data.handoffSummary` — `{headline: <=280 chars, keyFacts: <=5 short strings}` — or deriving a minimal ref-only fallback when absent. It never copies full prose downstream.

`summaryHash` covers exactly `{handoff, evidenceRefs, confidence}`. This is the mechanism that makes caching actually work across a chain: `scripts/cache_key.py` folds `--dep-summaries` (each upstream `summaryHash`) into a downstream node's cache key. Re-running an upstream node that produces byte-different-but-semantically-identical output still yields the same `summaryHash` if its `handoffSummary` didn't change — so the downstream cache key stays stable and that node is correctly skipped. A genuine change busts it. Verified by `t_summary_cache_invalidation` in `evals/run_evals.py`.

## 3. Evidence deduplication

`scripts/source_registry.py` normalizes a URL (lowercase scheme/host, drop fragment, strip `utm_*` params, drop trailing slash) and mints a `SRC_<hash>` id from that normalized form — so the same real-world source gets the same id everywhere, incrementally, as the run progresses (not just at final merge). Node contracts move from an embedded `sources: [EvidenceSource]` array to `evidence: [{ref, claims}]` — full metadata lives once in `runtime/runs/<run-id>/evidence/source-registry.json`; a node cites a ref plus the specific claims it draws from that source.

This is applied **fully to study-plan** (the contracts, `merge_verified_sections.py`, and `validate_references.py` all understand the new shape — the latter via `--evidence-registry` for pre-merge sections that no longer embed anything inline). It is **mirrored, not executed, in company-research**: the shared `EvidenceRef`/`HandoffSummary` schema defs and `x-contractgraph.contextRefs` metadata were added to its contracts for vocabulary consistency, but its existing `sources[].claims[]` convention (a different, already-working evidence-linkage pattern) was deliberately left in place. Company-research is not run this task, and forcing an unverified breaking rename onto it would be pure risk with zero executed benefit — see `runtime/compiled/study-plan/compilation-report.md`'s open questions for the same call, in context.

## 4. Issue-only verification (formalized, not changed)

Verification was already issue-only in practice; `scripts/schemas/verifier-verdict.schema.json` makes it structural: `{nodeId, verifier, status, issues:[{path, issueType, claim?, repairInstruction}], conflicts, confidence}` with `additionalProperties: false`. A verdict that tries to add `content`, `section`, `rewrite`, or `output` fails schema validation outright — the producer/verifier separation is enforced by the schema, not just by convention. See `t_verifier_issue_only`.

## 5. Weighted, quota-aware concurrency

`policies.json.execution.concurrency.modes` replaces the single `maxParallelNodes` integer with per-class caps (`heavyResearch`/`lightSynthesis`/`verifier`/`globalVerifier`), computed by `scripts/schedule_plan.py`. The one rule that never bends across modes: **`heavyResearch` stays ≤2**, including `--time-bounded` — time-bounded raises `lightSynthesis`/`verifier` throughput for lower wall-clock, never the concurrent web-research burst size. `policies.json.execution.concurrencyModes` (the old flat integer) is kept only as a legacy aggregate ceiling. See `t_weighted_concurrency` for the safety-floor proof across all three modes.

*(Documentation fix, same area: [execution.md](execution.md) previously stated `maxParallelNodes` was "5 in the default company-research bundle" — `policies.json` has always said 4. `policies.json` is the source of truth; the doc was wrong, not the policy.)*

## 6. Selective TOON (disabled at runtime, benchmark-gated)

`scripts/toon_benchmark.py` measures, per uniform-array shape, JSON vs TOON byte size, round-trip losslessness, and post-round-trip schema validity, then gates an `enable` decision on `policies.json.tokenEfficiency.toon`'s thresholds (`minCharSavingsPct`, `requireRoundTripLossless`, `requireSchemaValid`). `runtime/compiled/study-plan/toon-benchmark.json` is the current measured report against representative fixtures (`evals/fixtures/toon-samples/`) — all 4 eligible arrays (`resources`, `milestones`, `checkpoints`, `sourceRegistry`) currently clear the threshold. **None of this enables TOON in normal runtime** — `scripts/toon_codec.py`'s `encode`/`decode` still default to JSON passthrough; only the optimized benchmark config (see [opencode-benchmark.md](opencode-benchmark.md)) may set `toon: "selective"`. Model-output-quality under TOON is explicitly `"pending"` in the decision report — that can only be measured from an actual benchmark run, not a deterministic script.

## Test coverage

Every mechanism above has a deterministic test in `evals/run_evals.py`: `t_context_packet_relevance`, `t_packet_privacy_leak`, `t_evidence_dedup`, `t_evidence_registry_end_to_end`, `t_summary_cache_invalidation`, `t_verifier_issue_only`, `t_weighted_concurrency`, `t_toon_roundtrip`, `t_toon_token_compare`. Run `python evals/run_evals.py`.
