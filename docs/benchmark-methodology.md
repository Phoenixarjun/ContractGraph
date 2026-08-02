# Benchmark Methodology: Claude Code vs. OpenCode

This defines what makes a runtime-vs-runtime comparison **fair** — what must be
held identical across two runs so that any measured difference in tokens, cost,
or duration is attributable to the runtime rather than to an uncontrolled
variable. See [opencode-benchmark.md](opencode-benchmark.md) for the capture
commands, and [runtime-telemetry.md](runtime-telemetry.md) for how usage is
normalized once captured.

This repository ships the methodology and the configs, not results. No
benchmark numbers are published here, because publishing a number you have not
measured on both sides is exactly the failure this document exists to prevent.

## What Must Be Held Identical

| Variable | How it's controlled |
|---|---|
| Contract | the same `contracts/study-plan` bundle (`bundleVersion` pinned) for both runs |
| Context | the same context tree for both runs — never one synthetic and one canonical |
| Cache condition | both cold, or both warm-allowed, per `evals/benchmarks/study-plan/{baseline,optimized}.config.json`'s `cache` field — never one cold and one warm |
| Concurrency | identical `concurrency` value in both configs (currently 2/2) — this isolates whatever the *other* variable under test is; concurrency itself is never the variable when comparing runtimes |
| Model class | the closest available equivalent tier on each runtime (e.g. Claude Sonnet 5 vs. whatever OpenCode's provider integration maps to an equivalent tier) — exact model parity across two different platforms is not always possible; when it isn't, name the substitution explicitly in the run's `cost.json`/report rather than silently comparing unlike models |
| Verification rules | the same `policies.json` (`maxRetriesPerNode`, `workerCannotSelfApprove`, evidence/freshness rules) for both runs |
| Source budget | the same `source_scoring.py --min/--max` bounds (default 5-10 per node) applied identically to both runs' output |
| Repair policy | the same retry/repair configuration (`retryFailedNodesOnly`, `maxRetriesPerNode`) — a runtime that repairs more or less aggressively is not directly comparable |

## Measured telemetry, not estimated

Each run's usage must be captured and normalized through
`scripts/telemetry_normalize.py` into that run's own
`runtime/runs/<run-id>/final/cost.json` + `telemetry/requests.jsonl` — see
[runtime-telemetry.md](runtime-telemetry.md) for the exact shape and the
never-fabricate rule. A metric one runtime's export doesn't expose stays
`null` in that run's `cost.json`; `scripts/benchmark_compare.py` reports that
metric `"available": false` for the comparison rather than fabricating a
delta against a missing baseline.

## Run count

At minimum, **one baseline run per runtime**. Preferably **three runs per
runtime**, taking the **median** of each metric — a single run cannot
distinguish a genuine runtime difference from ordinary run-to-run variance
(network latency on web-research nodes, provider-side load, retry jitter).
`benchmark_compare.py` currently diffs exactly two `cost.json` files; running
it three times (once per baseline/optimized pair) and taking the median
`delta`/`deltaPct` per metric is a manual step until/unless a
`--median-of <cost.json>...` mode is added.

## Running it

```
# Claude Code
/contractgraph:run --bundle contracts/study-plan --context context/synthetic/study-plan \
    --input evals/benchmarks/study-plan/input.json \
    --config evals/benchmarks/study-plan/baseline.config.json

# OpenCode -- see opencode-benchmark.md for the exact CLI invocation and export capture
opencode run "/contractgraph:run --bundle contracts/study-plan --context context/synthetic/study-plan \
    --input evals/benchmarks/study-plan/input.json \
    --config evals/benchmarks/study-plan/baseline.config.json --run-id sp-baseline-oc-01"
```

After each run: `python scripts/telemetry_normalize.py --run <run-dir> [--claude-code <export>] [--opencode <export>] --out <run-dir>/final/cost.json`,
then `python scripts/validate_timestamps.py --run <run-dir>` (treat any
violation as a run defect, not a benchmark result to report), then
`python scripts/benchmark_compare.py --baseline <cc-cost.json> --optimized <oc-cost.json> --out comparison.json`.

## What this benchmark can and cannot tell you

- **Can measure:** token/cost/duration/tool-call deltas between the two
  runtimes under held-identical everything-else, per
  [runtime-telemetry.md](runtime-telemetry.md)'s normalized fields.
- **Cannot measure:** output *quality* differences (whether one runtime's
  verified sections are more accurate, better sourced, or more useful) —
  that requires comparing `validation-report.json` and verifier confidence
  scores across the two runs' outputs, not just their `cost.json`s. A
  runtime that's cheaper and faster but produces worse-verified output is
  not a win.
- **Requires the runtime to actually expose usage data.** If either
  runtime's export omits a metric (e.g. cache-token splits), that metric
  stays `null` in `cost.json` and the comparison degrades gracefully to
  whatever both sides do report, per `coverage`.

## Do Not Claim Savings Before Both Runs Exist

No cost or token savings claim is valid until both runtimes' instrumented runs
are complete and normalized. A configuration difference — optimized vs. baseline
settings — measured on only one runtime says nothing about a cross-runtime
comparison, and reporting it as one is a fabrication.
