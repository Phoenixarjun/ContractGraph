# Evaluation

`evals/` holds the regression suite for the framework itself — not for any one workflow's research output. It exists to catch a compiler or executor regression before it silently corrupts a real run, and to prove the same mechanism produces correct results for two structurally different workflows.

```text
evals/
├── run_evals.py         # the suite itself — deterministic, offline, no model calls
├── compilation-cases/   # /contractgraph:init behavior
├── skill-cases/         # skill trigger / false-trigger / duplication behavior
├── workflow-cases/      # full /contractgraph:run scenarios
├── benchmarks/          # baseline vs optimized run configs for token comparison
├── fixtures/            # synthetic sample data (TOON samples, etc.)
└── rubrics/             # scoring rubrics used by the semantic checks below
```

Run it with:

```bash
python evals/run_evals.py
```

It exercises the real script CLIs through `subprocess` — no model calls, no
network, no live research — and exits non-zero if any case fails. Cases that
need a local-only artifact (a private bundle, or a completed run under the
git-ignored `runtime/runs/`) report **SKIP** with the reason rather than
failing or silently disappearing, so a fresh clone is green and honest about
what it did not cover.

## The 12 Categories

**Compile plane**

1. **Bundle structural validation** — malformed and valid bundles both produce the exact expected `validate_contract_bundle.py` verdict.
2. **Context indexing & privacy exclusion** — `context/private/` never appears in `context-manifest.json` under any input shape.
3. **Capability detection accuracy** — the right capability set, no over- or under-detection, one entry per capability regardless of how many nodes/map-items need it.
4. **Skill reuse / create / regenerate decisions** — `skill-registry-manager` picks the correct action for each of: compatible+clean, stale-triggered, quality-failed, privacy-flagged, and missing.
5. **Skill quality evaluation** — triggering, false triggering, duplication, token overhead, and privacy leakage are each independently detectable in a planted-defect fixture.
6. **Agent generation fidelity** — every generated subagent's tools/model/skills/budget/retry trace back to its node contract and `policies.json`, with no scope creep.
7. **Graph dependency compilation & cross-check** — a deliberate mismatch between a node's `x-contractgraph.dependsOn` and `graph.yaml`'s `dependencies` is caught as a blocking error, not silently resolved.
8. **Compiled graph structural integrity** — cycles and orphan nodes are rejected by `validate_compiled_graph.py`.

**Run plane**

9. **Node state-machine correctness** — every transition in [execution.md](execution.md)'s state diagram, including the self-approval prohibition and retry-attempt bookkeeping.
10. **Structural + semantic + evidence + freshness validation accuracy** — planted unsupported claims, stale claims, and cross-section contradictions are each independently caught, per [validation.md](validation.md)'s verifier contract.
11. **Deterministic aggregation & caching correctness** — merge respects `stateOwnership` (a refresh never overwrites a non-empty user-owned field), and a cache key is stable across reruns with identical inputs and changes with any one of its declared inputs.
12. **Global verification & cross-workflow genericity** — the full init → run → verify path produces a contract-valid, provenance-complete final artifact on **both** fixtures below, with zero framework-code differences between them.

## The Two Fixtures

| Fixture | Contracts | Context | Proves |
|---|---|---|---|
| **study-plan** (public) | `contracts/study-plan/` | `context/synthetic/study-plan/` (fabricated learner profile, no real personal data) | The full compile → run → verify → finalize path on a bundle anyone can clone and inspect. This is the reference bundle every default points at. |
| **your own bundle** (local) | `contracts/<workflow>/` | your `context/canonical/` | **Genericity** — the identical `/contractgraph:{context,contract,init,validate,run,finalize}` mechanism, the identical skill- and agent-generation procedure, and the identical three-layer validation model produce a correct, differently-shaped workflow from nothing but a different contract bundle and different context. No core script, skill, or command is edited to support it. |

The genericity cases are the framework's proof of its own central claim: contracts and context define the workflow, Claude Code designs the execution, and nothing domain-specific is hard-coded into the runtime. If a new bundle ever required a core-code change to pass, that would be a genericity regression, not a feature.

`evals/rubrics/` holds the scoring criteria the semantic categories (5, 10) use, so a planted-defect fixture has a machine-checkable pass/fail bar rather than relying on a reviewer's judgment call each time.
