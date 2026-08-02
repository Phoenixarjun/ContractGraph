# OpenCode Benchmark — Study Plan

How to run the controlled baseline-vs-optimized comparison of the study-plan
workflow under OpenCode. This repository ships the procedure and the configs;
it publishes no benchmark numbers, because a number that has not been measured
on both sides is not a result. See
[benchmark-methodology.md](benchmark-methodology.md) for what must be held
identical for the comparison to be fair.

## Why the Study-Plan Bundle

`contracts/study-plan` is the public reference bundle — domain-neutral,
synthetic-context-safe, and small: a 1→4→1 diamond
(`baseline-assessment` → {`python`, `fastapi`, `databases`,
`distributed-systems`} → `evaluation-plan`). That makes it cheap to run
repeatedly and easy for anyone to reproduce. A different context tree can be
substituted at run time with `--context`; the compiled workflow hard-codes
neither.

## The Two Configs

`evals/benchmarks/study-plan/baseline.config.json` and `optimized.config.json` hold the contract, context, models, and concurrency (2) fixed. Only the token-efficiency mechanisms vary between them:

| | Baseline | Optimized |
|---|---|---|
| Format | JSON | JSON |
| Cache | cold | warm-allowed |
| Context slicing | on | on, via cache-aware node packets (`node-packets/<id>/packet.json`) |
| Dependency summaries | off (full sections read downstream) | on (`build_dependency_summary.py`) |
| Evidence dedup | off (embedded `sources[]`) | on (`source_registry.py` + `evidence: [{ref,claims}]`) |
| Verification | full | issue-only (`verifier-verdict.schema.json`) |
| TOON | disabled | selective — only `resources`/`milestones`/`checkpoints`/`sourceRegistry`, per `runtime/compiled/study-plan/toon-benchmark.json`'s measured decision |
| Concurrency | 2 | 2 (unchanged — isolates the *other* variables) |
| Repairs | blocking-only | blocking-only (unchanged) |

`evals/benchmarks/study-plan/input.json` supplies the synthetic learner's stated goal (`context/synthetic/study-plan/canonical/goals.md`) as the runtime input. Swap it, together with `--context`, to benchmark against a different context tree.

## Running the Baseline

```
opencode run "/contractgraph:run \
  --bundle contracts/study-plan \
  --context context/synthetic/study-plan \
  --input evals/benchmarks/study-plan/input.json \
  --config evals/benchmarks/study-plan/baseline.config.json \
  --run-id sp-baseline-01"
```

After the session completes, capture usage and normalize it:

```
opencode export --session <id> > runtime/runs/sp-baseline-01/telemetry/opencode.json
python scripts/telemetry_normalize.py --run runtime/runs/sp-baseline-01 \
    --opencode runtime/runs/sp-baseline-01/telemetry/opencode.json \
    --out runtime/runs/sp-baseline-01/final/cost.json
```

## Running the Optimized Config

Identical invocation, swapping the config and run id:

```
opencode run "/contractgraph:run \
  --bundle contracts/study-plan \
  --context context/synthetic/study-plan \
  --input evals/benchmarks/study-plan/input.json \
  --config evals/benchmarks/study-plan/optimized.config.json \
  --run-id sp-optimized-01"

opencode export --session <id> > runtime/runs/sp-optimized-01/telemetry/opencode.json
python scripts/telemetry_normalize.py --run runtime/runs/sp-optimized-01 \
    --opencode runtime/runs/sp-optimized-01/telemetry/opencode.json \
    --out runtime/runs/sp-optimized-01/final/cost.json
```

For per-node telemetry attribution, `scripts/build_opencode_session_slug.py` mints a deterministic session slug (`cg-<runId>-<nodeId>-<purpose>-<attempt>`) so each producer, verifier, and repair request maps to its own session and its usage can be attributed back to the node that caused it.

**Verify the exact OpenCode CLI flags (`run`, `export`, `--session`) against the installed OpenCode version before running these** — the `/contractgraph:run` prompt string is stable across runtimes, but OpenCode's own CLI surface may differ from what's shown here.

## Comparing the two runs

```
python scripts/benchmark_compare.py \
    --baseline runtime/runs/sp-baseline-01/final/cost.json \
    --optimized runtime/runs/sp-optimized-01/final/cost.json \
    --out evals/benchmarks/study-plan/comparison.json
```

Reports, per metric (input/output/cache-read/cache-creation tokens, estimated cost, duration, tool calls, web searches, web fetches, output bytes, request/success/failure counts): baseline value, optimized value, delta, and delta percent — never dividing by a null or zero baseline (that metric is reported `unavailable` instead of a fabricated ratio). See [benchmark-methodology.md](benchmark-methodology.md) for what must be held identical between the two runs for this comparison to be fair.

## What this benchmark can and cannot tell you

- **Can measure:** token/cost/duration deltas from the mechanisms in [token-optimization.md](token-optimization.md) — node packets, dependency summaries, evidence dedup, issue-only verification, selective TOON.
- **Cannot measure without actually running it:** whether TOON-encoded arrays change model **output quality** (not just size/losslessness) — `runtime/compiled/study-plan/toon-benchmark.json` explicitly marks that dimension `"pending"`. If the optimized run's validation/semantic-quality results (`validation-report.json`, verifier confidence scores) are materially worse than baseline's, that is the signal to disable TOON for this contract even though the size/round-trip numbers looked good in isolation.
- **Requires the runtime to actually expose usage data.** If OpenCode's export omits cache-token splits, those stay `null` in `cost.json` (never fabricated) and the comparison degrades gracefully to output-token and byte-count proxies for that metric.
