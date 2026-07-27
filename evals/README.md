# ContractGraph evals

Deterministic, offline test + evaluation suite. Run: `python evals/run_evals.py`.
No model calls, no network, no live research. Categories map to docs/evaluation.md.

- `rubrics/` — human-judgment rubrics for the model-graded dimensions.
- `compilation-cases/` — bundles that must compile (company-research, study-plan).
- `skill-cases/` — skill-triggering expectations.
- `workflow-cases/` — dry-run expectations per bundle.

The study-plan case is the genericity proof: a non-company domain that compiles
its own nodes with the same scripts, proving nothing is hard-coded.
