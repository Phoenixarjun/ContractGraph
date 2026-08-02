# Runtime Telemetry

This extends [token-telemetry.md](token-telemetry.md) — read that first for the
never-fabricate principle, the three capture sources, and cost estimation. This
document covers what makes telemetry trustworthy enough to compare two runtimes
against each other: a raw per-request layer, richer per-request identity, and
duplicate-safe aggregation.

Normalization is not automatic. A run only has telemetry if something captured
it and invoked `telemetry_normalize.py`; finalization wires this in, and a run
with no captured usage reports every metric as `null` with `coverage` saying so,
rather than pretending to a measurement it never made.

## Two Output Layers

```
runtime/runs/<run-id>/telemetry/requests.jsonl   # one RequestRecord per line, raw
runtime/runs/<run-id>/final/cost.json            # the same records + aggregates
```

`requests.jsonl` is the audit trail — every normalized request, unaggregated,
one JSON object per line, in the order the sources were merged. `cost.json`
is `requests.jsonl`'s content plus the `byNode`/`byModel`/`byPurpose`/
`byAttempt`/`run`/`coverage` rollups token-telemetry.md already describes.

## RequestRecord Identity Fields

| Field | Purpose |
|---|---|
| `requestId` | deterministic content hash (runtime+model+node+purpose+attempt+agent+skill+every numeric metric+status) — see dedup below |
| `runId` | from the run's `run.json`, so a request record is traceable without external context |
| `sessionId` | passthrough from the source, when it reports one |
| `telemetrySource` | which capture mechanism produced this record: `claude-code-otel-export` \| `opencode-session-export` \| `local-instrumentation` — distinct from `runtime` (which *ran* the call); `telemetrySource` says *how the data was obtained* |
| `unavailableFields` | the field names in `available` that are `false`, listed explicitly (not just discoverable by scanning the map) |
| `webSearches` / `webFetches` | counts of each tool call, named to match Claude Code's own tool vocabulary |
| `status` | terminal status of the request |
| `startedAt` / `completedAt` | passthrough from the source when it reports call-level timestamps; `null` otherwise, never estimated from `durationMs` |

`estimatedCostUsd` remains a **provider-list-price estimate** from the static
`scripts/model_prices.json` table — never a provider-reported actual charge,
and always labeled as such in `cost.json`'s aggregates.

## Duplicate-safe aggregation

The same underlying model call can appear twice in the merged input — e.g. a
parent transcript export that also embeds a subagent's own reported usage.
`requestId` is a content hash of the fields that identify a *specific* call
(not a sequence counter), so:

- re-running `telemetry_normalize.py` over the same inputs is idempotent
  (same records → same ids → same output), and
- an exact duplicate collapses to one record instead of double-counting.

`normalize()` dedupes on `requestId` after merging all sources; the dropped
count is reported as `dedupedCount` at the top of `cost.json`. `byNode` /
`byModel` / etc. are computed from the deduped list, so aggregates never
include a double-counted request. `t_telemetry_dedup` in
`evals/run_evals.py` exercises the exact parent/subagent double-capture
scenario this guards against.

Trade-off: two **genuinely distinct** calls that happen to share every
identifying field and every metric value would also collapse. This is
accepted as a rare, low-cost false-negative in exchange for a simple,
deterministic dedup rule with no external id dependency.

## Aggregate Fields

`run` and every `by*` group report `successCount` / `failureCount` alongside
the token, cost, and duration sums, computed from each request's `status`.

## Fixtures for Every Source

`evals/run_evals.py`'s `t_telemetry_normalize` builds one fixture per source
(`--claude-code`, `--opencode`, `--local`) and asserts they merge, group, and
validate against `scripts/schemas/cost.schema.json` together;
`t_telemetry_missing_fields` asserts a source that reports no token counts at
all still normalizes with `null` (never `0`) and a correct `unavailableFields`
list; `t_node_cost_aggregation` checks the arithmetic of the `by*` groupings
directly. See [benchmark-methodology.md](benchmark-methodology.md) for how
these feed the actual Claude Code vs. OpenCode comparison.
