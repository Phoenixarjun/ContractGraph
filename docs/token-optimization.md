# Token Optimization

[token-efficiency.md](token-efficiency.md) states the standing policy — model routing, caching inputs, "no full transcripts between nodes", format. This doc covers the mechanisms that enforce those rules with artifacts rather than prose: node-specific context packets, compact cross-node handoffs, evidence deduplication, issue-only verification, and weighted concurrency.

## The Waste These Mechanisms Remove

Four distinct failure modes, each addressed below:

- **The same source, re-described everywhere.** Without a run-level registry, one real-world URL gets a different per-node id and a full metadata block in every section that cites it. The final merge consolidates it, but every intermediate handoff already paid for the duplication.
- **No per-node context packet.** `init` writes manifests; without a packet, nothing defines *which* canonical files or *which* upstream sections a given producer should actually load — so the safe-looking default becomes "load everything".
- **Verifiers that rewrite.** A verdict schema that permits a `content` field invites a verifier to hand back a rewritten section, collapsing the producer/verifier separation and paying for the content twice.
- **One flat concurrency integer.** No distinction between a node burning through web searches and a node doing pure synthesis over already-verified data.

## 1. Node-Specific Context Packets

`scripts/build_node_packets.py` (an init-time step, reusing `dry_run.py`'s plan-assembly logic) compiles `runtime/compiled/<bundleId>/node-packets/<nodeId>/packet.json` per node containing **only**:

- that node's own contract reference + hash (never the whole bundle),
- its declared `x-contractgraph.contextRefs` — canonical file paths **by path + SHA-256**, never by content. A node contract with no `contextRefs` gets an empty list; there is no "load all canonical" fallback. A declared ref that isn't in the indexed context manifest (file missing, or `build_context_manifest.py` not yet re-run after adding it) blocks compilation with a clear per-node/per-path error instead of emitting an invalid packet with a null hash — `node-packet.schema.json` requires `sha256` as a non-null string, so this is a compile-time failure, not a silent gap. See `t_node_packet_missing_context_ref`.
- dependency-summary refs (a `{depNode, summaryHash}` pair — see §2), never a full upstream section,
- an evidence-registry reference (see §3), never inline source objects,
- required skills, a token/search budget, and output instructions.

For study-plan: `baseline-assessment` (the only node reading raw canonical facts directly) declares all 3 canonical files; the four topic nodes each declare only `canonical/preferences.md` (resource-selection preference — the learner's stated level/gaps are already digested into `baseline-assessment`'s handoff summary, so re-reading `goals.md`/`knowledge.md` downstream would be pure duplication); `evaluation-plan` declares `canonical/goals.md` to tie its final assessment back to the stated goal.

## 2. Compact Handoffs via Cacheable Dependency Summaries

`scripts/build_dependency_summary.py` runs immediately after a node is `ACCEPTED`, extracting its (optional, producer-authored, schema-bounded) `data.handoffSummary` — `{headline: <=280 chars, keyFacts: <=5 short strings}` — or deriving a minimal ref-only fallback when absent. It never copies full prose downstream.

`summaryHash` covers exactly `{handoff, evidenceRefs, confidence}`. This is the mechanism that makes caching actually work across a chain: `scripts/cache_key.py` folds `--dep-summaries` (each upstream `summaryHash`) into a downstream node's cache key. Re-running an upstream node that produces byte-different-but-semantically-identical output still yields the same `summaryHash` if its `handoffSummary` didn't change — so the downstream cache key stays stable and that node is correctly skipped. A genuine change busts it. Verified by `t_summary_cache_invalidation` in `evals/run_evals.py`.

## 3. Evidence Deduplication

`scripts/source_registry.py` normalizes a URL (lowercase scheme/host, drop fragment, strip `utm_*` params, drop trailing slash) and mints a `SRC_<hash>` id from that normalized form — so the same real-world source gets the same id everywhere, incrementally, as the run progresses (not just at final merge). Node contracts move from an embedded `sources: [EvidenceSource]` array to `evidence: [{ref, claims}]` — full metadata lives once in `runtime/runs/<run-id>/evidence/source-registry.json`; a node cites a ref plus the specific claims it draws from that source.

The study-plan bundle uses this shape end to end: its contracts, `merge_verified_sections.py`, and `validate_references.py` all understand it — the latter via `--evidence-registry`, since pre-merge sections no longer embed source metadata inline. `merge_verified_sections.py` still accepts the older embedded `sources[]` shape, so a bundle that has not migrated keeps working.

## 4. Issue-Only Verification

Verification was already issue-only in practice; `scripts/schemas/verifier-verdict.schema.json` makes it structural: `{nodeId, verifier, status, issues:[{path, issueType, claim?, repairInstruction}], conflicts, confidence}` with `additionalProperties: false`. A verdict that tries to add `content`, `section`, `rewrite`, or `output` fails schema validation outright — the producer/verifier separation is enforced by the schema, not just by convention. See `t_verifier_issue_only`.

## 5. Weighted, Quota-Aware Concurrency

`policies.json.execution.concurrency.modes` replaces the single `maxParallelNodes` integer with per-class caps (`heavyResearch`/`lightSynthesis`/`verifier`/`globalVerifier`), computed by `scripts/schedule_plan.py`. The one rule that never bends across modes: **`heavyResearch` stays ≤2**, including `--time-bounded` — time-bounded raises `lightSynthesis`/`verifier` throughput for lower wall-clock, never the concurrent web-research burst size. `policies.json.execution.concurrencyModes` (the old flat integer) is kept only as a legacy aggregate ceiling. See `t_weighted_concurrency` for the safety-floor proof across all three modes.

A bundle's own `policies.json` is always the source of truth for its caps. If this document and a `policies.json` ever disagree, the policy file is right.

## 6. Selective TOON — Disabled at Runtime, Benchmark-Gated

`scripts/toon_benchmark.py` measures, per uniform-array shape, JSON vs TOON byte size, round-trip losslessness, and post-round-trip schema validity, then gates an `enable` decision on `policies.json.tokenEfficiency.toon`'s thresholds (`minCharSavingsPct`, `requireRoundTripLossless`, `requireSchemaValid`). `runtime/compiled/study-plan/toon-benchmark.json` is the current measured report against representative fixtures (`evals/fixtures/toon-samples/`) — all 4 eligible arrays (`resources`, `milestones`, `checkpoints`, `sourceRegistry`) currently clear the threshold. **None of this enables TOON in normal runtime** — `scripts/toon_codec.py`'s `encode`/`decode` still default to JSON passthrough; only the optimized benchmark config (see [opencode-benchmark.md](opencode-benchmark.md)) may set `toon: "selective"`. Model-output-quality under TOON is explicitly `"pending"` in the decision report — that can only be measured from an actual benchmark run, not a deterministic script.

## Test coverage

Every mechanism above has a deterministic test in `evals/run_evals.py`: `t_context_packet_relevance`, `t_packet_privacy_leak`, `t_evidence_dedup`, `t_evidence_registry_end_to_end`, `t_summary_cache_invalidation`, `t_verifier_issue_only`, `t_weighted_concurrency`, `t_toon_roundtrip`, `t_toon_token_compare`. Run `python evals/run_evals.py`.
