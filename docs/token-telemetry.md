# Token Telemetry

Before this feature, no run recorded actual token usage anywhere. A real completed company-research run records only output byte counts, `attempts`, `cache HIT/MISS`, and day-granularity timestamps — no input/output tokens, no model-usage figures, no duration, no tool-call counts. `final/cost.json` was a reserved output path with no script producing it. `scripts/telemetry_normalize.py` fills that gap.

## Principle: never fabricate

If a source doesn't report a metric, that metric is `null` in the output — never `0`, never estimated from an unrelated proxy, never silently omitted. Every `RequestRecord` carries an `available` map (`{inputTokens: true, cacheReadTokens: false, ...}`) so a consumer can tell "zero usage" apart from "unmeasured usage" at a glance. `coverage` in the aggregate report says the same thing at the run level: how many of N requests actually reported each metric.

## Sources

`telemetry_normalize.py` accepts any combination of three sources, all optional:

| Source | Flag | What it captures | What it typically CANNOT tell you |
|---|---|---|---|
| Claude Code / OTEL usage export | `--claude-code FILE` | `model`, `usage.{input_tokens,output_tokens,cache_read_input_tokens,cache_creation_input_tokens}`, `duration_ms`, `tool_calls` | Which ContractGraph node/purpose/agent/skill the call belongs to — unless the caller attached that as `metadata` on the record |
| OpenCode session export/stats | `--opencode FILE` | Same shape, plus OpenAI-style `usage.{promptTokens,completionTokens}` aliases (OpenCode can proxy multiple providers) | Same caveat as above |
| Local per-call records | `--local DIR` | Whatever a run's own instrumentation wrote, already tagged `node`/`purpose`/`agent`/`skill`/`attempt` | Nothing missing by design — this is the one source that reliably knows ContractGraph's own semantics |

Field name aliases are resolved via dotted-path lookup (`usage.input_tokens` / `usage.inputTokens` / `usage.promptTokens`, ...) so a caller doesn't need to pre-normalize a raw export before handing it to this script — but if a genuinely different runtime uses field names not yet listed, extend the alias list in the script rather than guess at a value.

## The canonical `RequestRecord`

Every request produced by any source normalizes to the same shape (`scripts/schemas/cost.schema.json`):

```json
{
  "runtime": "claude-code",
  "model": "claude-sonnet-5",
  "agent": "python",
  "skill": "evidence-backed-web-research",
  "purpose": "producer",
  "node": "python",
  "attempt": 1,
  "inputTokens": 1200,
  "outputTokens": 340,
  "cacheReadTokens": 500,
  "cacheCreationTokens": 0,
  "estimatedCostUsd": 0.0087,
  "durationMs": 4200,
  "toolCalls": 3,
  "searches": null,
  "fetches": null,
  "outputBytes": null,
  "finalStatus": "accepted",
  "available": { "inputTokens": true, "searches": false, "...": "..." }
}
```

`purpose` is one of `producer | verifier | repair | global-verifier | unknown` — `unknown` (not a guessed default) when a source can't say which role a call played.

## Cost estimation

`estimatedCostUsd` is computed from `scripts/model_prices.json` — a **static, version-pinned reference table**, not a live price lookup (no network call). A model string is mapped to a tier by substring match (`"claude-sonnet-5"` → `sonnet`); if the tier isn't recognized, or either side of input/output tokens is missing, cost stays `null`. Treat every cost figure in `cost.json` as an estimate against list pricing at the time `model_prices.json` was last updated — update that file manually when pricing changes.

## Aggregation

`normalize()` groups requests four ways — `byNode`, `byModel`, `byPurpose`, `byAttempt` — plus one `run`-level total. Each group sums only the non-null values it saw; a group where every request lacked a metric reports that metric as `null`, not `0`. `requestCount` is the one field always present (counting requests needs no external data).

## Usage

```
python scripts/telemetry_normalize.py --run runtime/runs/<run-id> \
    [--claude-code <export.json>] [--opencode <export.json>] [--local runtime/runs/<run-id>/telemetry/raw] \
    [--prices scripts/model_prices.json] \
    --out runtime/runs/<run-id>/final/cost.json
```

See [opencode-benchmark.md](opencode-benchmark.md) for the exact commands used to capture an OpenCode export and feed it into this script for the baseline/optimized study-plan comparison.
