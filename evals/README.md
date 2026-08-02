# ContractGraph evals

Deterministic, offline test + evaluation suite. Run it with:

```bash
python evals/run_evals.py
```

No model calls, no network, no live research. Every case shells out to a real
script CLI. Categories map to [../docs/evaluation.md](../docs/evaluation.md).
Exit code is non-zero if any case fails.

- `compilation-cases/` — bundles that must compile.
- `skill-cases/` — skill-triggering expectations.
- `workflow-cases/` — dry-run expectations per bundle.
- `benchmarks/` — baseline vs. optimized run configs used by the token comparison.
- `fixtures/` — synthetic sample data (TOON samples and similar).
- `rubrics/` — human-judgment rubrics for the model-graded dimensions.

## SKIP vs. FAIL

Some cases need an artifact that is deliberately git-ignored — a local-only
private contract bundle, or a completed run under `runtime/runs/`. On a fresh
clone those cases print **SKIP** with the reason instead of failing, and the
final line reports how many were skipped. A skip is never counted as a pass.

`contracts/study-plan` is the public reference bundle: it is what every script
and command defaults to, and it is the one bundle guaranteed present in a clone.
