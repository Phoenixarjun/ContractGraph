# OpenCode Benchmark — Study Plan

This documents how to run the controlled baseline-vs-optimized comparison of the study-plan workflow under OpenCode, using the private canonical context. **Neither benchmark has been executed as part of this task** — this doc, the two configs, and `input.json` are preparation only, per explicit scope: implement, validate deterministically, document, and prepare the benchmark; do not run it.

## Why study-plan, not company-research

Company-research is the private validation workflow and is explicitly out of scope for execution this task. Study-plan is the public demonstration workflow — domain-neutral, synthetic-context-safe, and small (a 1→4→1 diamond: `baseline-assessment` → {`python`,`fastapi`,`databases`,`distributed-systems`} → `evaluation-plan`) — making it the right target for a reproducible, low-cost benchmark run. The user's **real** canonical context can still be substituted for the synthetic one at run time (the compiled workflow doesn't hard-code either).

## The two configs

`evals/benchmarks/study-plan/baseline.config.json` and `optimized.config.json` hold the contract, context, models, and concurrency (2) fixed — only the optimizations this task added vary:

| | Baseline | Optimized |
|---|---|---|
| Format | JSON | JSON |
| Cache | cold | warm-allowed |
| Context slicing | on (pre-existing behavior) | on, via cache-aware node packets (`node-packets/<id>/packet.json`) |
| Dependency summaries | off (full sections read downstream) | on (`build_dependency_summary.py`) |
| Evidence dedup | off (embedded `sources[]`) | on (`source_registry.py` + `evidence: [{ref,claims}]`) |
| Verification | full | issue-only (`verifier-verdict.schema.json`) |
| TOON | disabled | selective — only `resources`/`milestones`/`checkpoints`/`sourceRegistry`, per `runtime/compiled/study-plan/toon-benchmark.json`'s measured decision |
| Concurrency | 2 | 2 (unchanged — isolates the *other* variables) |
| Repairs | blocking-only | blocking-only (unchanged) |

`evals/benchmarks/study-plan/input.json` supplies the synthetic learner "Sam"'s stated goal (`context/synthetic/study-plan/canonical/goals.md`) as the runtime input — swap this for the user's real goal/preferences to run the benchmark against real private context instead.

## Running the baseline (do not execute yet)

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

## Running the optimized config (do not execute yet)

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

**Verify the exact OpenCode CLI flags (`run`, `export`, `--session`) against the installed OpenCode version before running these** — the `/contractgraph:run` prompt string is stable across runtimes, but OpenCode's own CLI surface may differ from what's shown here.

## Comparing the two runs

```
python scripts/benchmark_compare.py \
    --baseline runtime/runs/sp-baseline-01/final/cost.json \
    --optimized runtime/runs/sp-optimized-01/final/cost.json \
    --out evals/benchmarks/study-plan/comparison.json
```

Reports, per metric (input/output/cache-read/cache-creation tokens, estimated cost, duration, tool calls, searches, fetches, output bytes, request count): baseline value, optimized value, delta, and delta percent — never dividing by a null or zero baseline (that metric is reported `unavailable` instead of a fabricated ratio).

## What this benchmark can and cannot tell you

- **Can measure:** token/cost/duration deltas from the mechanisms in [token-optimization.md](token-optimization.md) — node packets, dependency summaries, evidence dedup, issue-only verification, selective TOON.
- **Cannot measure without actually running it:** whether TOON-encoded arrays change model **output quality** (not just size/losslessness) — `runtime/compiled/study-plan/toon-benchmark.json` explicitly marks that dimension `"pending"`. If the optimized run's validation/semantic-quality results (`validation-report.json`, verifier confidence scores) are materially worse than baseline's, that is the signal to disable TOON for this contract even though the size/round-trip numbers looked good in isolation.
- **Requires the runtime to actually expose usage data.** If OpenCode's export omits cache-token splits, those stay `null` in `cost.json` (never fabricated) and the comparison degrades gracefully to output-token and byte-count proxies for that metric.
