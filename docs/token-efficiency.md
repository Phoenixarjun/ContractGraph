# Token Efficiency

ContractGraph treats context and model tier as budgeted resources, not defaults to leave on the most capable setting everywhere. Every rule below traces to `policies.json.tokenEfficiency` or `policies.json.models`.

## Model Routing

| Tier | Used for |
|---|---|
| **Haiku** | URL/source triage and dedup, low-risk extraction, bounded structural repair. |
| **Sonnet** | Node research and execution, contract interpretation, profile alignment, semantic repair, per-section verification, graph-plan drafting. |
| **Opus** | Graph-plan supervision, difficult skill criticism, top-level adjudication, global contradiction checking, global verification. |

Opus is reserved for judgment that spans the whole workflow — a single node's research or repair never needs it. `policies.json.execution` routes retries the same way: `repair.structural → haiku`, `repair.semantic → sonnet`, so a bounded schema fix never escalates to a heavier model than the mistake warrants.

## Evidence Summaries to Opus

`global-verifier` never receives raw per-node transcripts or full search results — it receives each accepted section's structured JSON plus its evidence references. `policies.json.tokenEfficiency.passEvidenceSummariesToOpus` and `doNotPassFullTranscriptsBetweenNodes` make this an explicit constraint, not an incidental optimization: a full research transcript is exactly the kind of bulk context [architecture.md](architecture.md)'s Claude-Code-native design is meant to avoid pushing between nodes.

## Caching

A node's cache key (`scripts/cache_key.py`) is a hash over:

- bundle version,
- the node contract's hash,
- the hashes of the canonical context files that node actually depends on,
- the resolved runtime input,
- the configured role set,
- the bound skill version(s),
- the generated agent's version,
- the applicable freshness policy,
- the node's implementation version.

Any one of these changing invalidates only that node's cache entry — a profile.md edit does not invalidate `dsa`'s cache if `dsa` never reads `profile.md`. Only `ACCEPTED` outputs are ever cached; a partial, structurally-invalid, or unresolved-evidence result is never written to `runtime/cache/`, so a cache hit always means "this exact input already produced a verified result," never "this exact input was attempted."

The key also folds each upstream dependency's current `summaryHash` (`--dep-summaries`) and the node's own compiled packet hash (`--node-packet`) — see [token-optimization.md](token-optimization.md) for the full node-packet / dependency-summary design this protects.

`--force-refresh` bypasses cache lookup entirely for that run without deleting existing cache entries.

## No Full Transcripts Between Nodes

A downstream node reads its dependencies' accepted `sections/<nodeId>.json` — structured output, not conversation history. `policies.json.tokenEfficiency.doNotPassFullTranscriptsBetweenNodes` makes this explicit: state, not narrative, is what crosses a dependency edge.

## Format

JSON is the canonical interchange format everywhere (`canonicalFormat: "json"`). TOON is implemented (`scripts/toon_codec.py`) but gated behind `toonMode: "benchmark_before_enable"` — it is not used in any compiled or run artifact until a measured token-savings benchmark shows it doesn't cost correctness (e.g. via loss of type fidelity on round-trip). `scripts/toon_benchmark.py` runs that measurement per array shape; `runtime/compiled/study-plan/toon-benchmark.json` is the current decision report. TOON stays disabled for **normal runtime** regardless of that report's result — see [token-optimization.md](token-optimization.md) for the eligibility rules and [opencode-benchmark.md](opencode-benchmark.md) for the one config that may enable it.

## Other Standing Rules

- Reuse verified skills over regenerating (`reuseVerifiedSkills`) — see [skill-generation.md](skill-generation.md).
- Load context by relevance, not wholesale (`loadContextByRelevance`) — a node reads only the canonical files its contract actually needs.
- Cache context summaries for large canonical files rather than re-summarizing them per node (`cacheContextSummaries`).
- Retries target only the failed node (`retryFailedNodesOnly`) — never a full-run re-execution for one node's fix.
