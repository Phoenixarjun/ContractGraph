# ContractGraph — Token-Efficiency Optimization Plan (Opus, principal architect)

**Status:** APPROVED FOR IMPLEMENTATION by Opus. Implement with Sonnet. Do **not** use Opus for routine coding.
**Scope guard:** Do not run any company-research workflow. Do not execute either study-plan benchmark. Implement, validate deterministically, document, and prepare the benchmark only.
**Prime directive from spec:** TOON is *supported* but stays **disabled in normal runtime**; it may be enabled **only** by the optimized benchmark config, only for eligible uniform arrays, and only when the benchmark proves lossless savings.

This document is the build spec. Every section names exact files to create/modify, the data shapes, and the deterministic test that proves it. All new scripts are **stdlib-first, offline, no model/network/API-key calls** (one exception: `pypdf`/optional OCR for PDF, see §8). JSON stays canonical everywhere.

---

## 0. Grounded current state (from repository inspection)

- **No usage telemetry exists.** A real completed company-research run records only `totalOutputBytes`, per-node byte sizes, `attempts`, `cache HIT/MISS`, and **day-granularity** dates. `final/cost.json` is referenced by `run.md`/`dry_run.py` as an output slot but **no script produces it**. Any efficiency claim must add instrumentation first.
- **Handoffs are heavy.** 2.7 MB run, 1.2 MB final artifact. Sections embed full `sources[]` objects — **462 verbose source objects, 1048 refs**, same real URL re-described under per-node ids (`SRC_HLD_*`, `SRC_LLD_*`). The **final** artifact already fixes this (shared compact `sourceRegistry`, 172 entries; sections drop inline `sources`). The waste is entirely intermediate.
- **Verification is already issue-only** and compact (read-only `section-verifier`, `{status, issues, repairInstructions, unsupportedClaims, staleClaims, conflicts, confidence}`, no rewrites). Producer≠verifier is enforced. Keep it; only formalize + test.
- **No per-node context packets.** `init` writes manifests + references; `run.md` says "pass compact structured outputs between nodes" but never defines *which* canonical files / upstream sections a producer loads. `scripts/dry_run.py:plan()` already joins graph.json + agent-manifest + context-manifest + skill-manifest + policies per node — reuse it.
- **Concurrency is a flat integer cap** per mode (`default 4 / timeBounded 8 / tokenEfficient 2`), no class weighting. **Doc/config bug:** `docs/execution.md` says `maxParallelNodes: 5`, `policies.json` says `4` → policies is source of truth; fix the doc.
- **`scripts/toon_codec.py` exists**: `encode/decode(obj, enable_toon=False)` (compact-JSON passthrough when off; `python-toon` backend when on, `ImportError` if missing — fail loud), `toon_available()`, `benchmark(obj)` (char savings + `roundTripLossless`). Gated `toonMode: "benchmark_before_enable"`. Not referenced by any command.
- **`scripts/cache_key.py`** already folds bundle version, node-contract hash, runtime input, roles, freshness policy, **all canonical context hashes**, skill versions, agent version — but `nodeImplVersion` is a hardcoded constant. Must also fold **dependency-summary hashes** and **node-packet hash** (§3, §2).
- **`run_evals.py`** is a deterministic offline subprocess runner; tests are hardcoded `t_*()` functions added to a tuple in `main()`. The `evals/*-cases/*.json` files are documentation only (not wired). New deterministic tests plug in trivially.
- **Privacy:** `context/canonical/` and `context/private/*` are git-ignored; `hook_guard.py` blocks email/phone PII in writes under `.claude/skills` and `.claude/agents`. Only `t_privacy()` (email/phone regex) + `t_genericity()` (concept leakage) test this today.
- **Study-plan:** domain-neutral 1→4→1 diamond — `baseline-assessment` → {`python`,`fastapi`,`databases`,`distributed-systems`} (heavy web-research) → `evaluation-plan` (light synthesis, Read/Write only). Compiled dir is a hand-built fixture (`generatedBy:"fixture"`) **missing** `skill-manifest.json`, `capability-manifest.json`, `compilation-report.md`.

---

## 1. Architecture decisions (resolved conflicts — do not re-litigate)

1. **Source of truth for concurrency = `policies.json`** (`maxParallelNodes: 4`). Fix `docs/execution.md` (5→4) and document `concurrencyModes` + new weights.
2. **Evidence dedup is a contract change.** Sections move from embedded `sources[]` to `evidence: [{ref, claims[]}]` + a run-level `evidence/source-registry.json`. **Apply to study-plan (the benchmark target) fully. Mirror the same schema shape into company-research contracts for consistency but do NOT execute it** (user-confirmed). JSON stays canonical.
3. **Deterministic handoff summaries need a contract field.** Add optional `handoffSummary` object to node **output** contracts (small, bounded, producer-filled). The summary script only *extracts + hashes* it — no model. Where absent, derive a minimal ref-only summary deterministically.
4. **Per-node context selection is declared, not inferred at runtime.** Add optional `x-contractgraph.contextRefs: [path...]` to node contracts. Study-plan node contracts already carry `canonicalContextRequirements` — map those. Packet builder falls back to a conservative explicit mapping (never "all canonical").
5. **TOON token numbers are estimated** (no model available). The benchmark harness reports char savings + a documented char→token approximation, flagged `estimated:true`. True token counts come only from the actual benchmark run's `cost.json`.
6. **PDF requires one offline third-party lib** (`pypdf`; optional OCR `pytesseract`+`Pillow`) — **user-confirmed**. This is the single dependency addition, offline, no API keys — consistent with CLAUDE.md's "document extraction / OCR fallback" allowance. Pin it in `scripts/requirements.txt` marked optional/local; **guard imports** so the rest of the suite runs without OCR deps.
7. **`cache_key.py` must fold** `depSummaryHashes` and `nodePacketHash` so summary/packet changes bust the key correctly. Replace the constant `nodeImplVersion` fold with these.
8. **Never fabricate telemetry.** Unavailable metrics are `null` + `available.<metric>=false`; aggregates skip nulls and report `coverage`.

---

## 2. Node-specific context packets

**New script:** `scripts/build_node_packets.py` (deterministic; seed from `dry_run.plan()`).
**Emits:** `runtime/compiled/<workflow?>/node-packets/<node-id>/packet.json` (+ optional `packet.md` human view).

**Packet schema** (`scripts/schemas/node-packet.schema.json`, validated by `jsonschema_lite`):
```jsonc
{
  "nodeId": "python",
  "packetHash": "<sha256 of canonical packet minus this field>",
  "contractRef": "contracts/study-plan/node-contracts/python.contract.json",
  "contractHash": "<sha256>",
  "policySummary": { "model": "sonnet", "freshnessDaysRelevant": {...}, "evidenceRules": [...],
                     "retry": {"max":2,"failedOnly":true}, "concurrencyClass": "heavyResearch" },
  "contextRefs": [ { "sourcePath": "context/synthetic/study-plan/canonical/goals.md",
                     "sha256": "...", "loadWhen": "summary", "summaryRef": null } ],
  "dependencySummaryRefs": [ { "depNode": "baseline-assessment", "summaryHash": "<sha256>" } ],
  "evidenceRegistryRef": "runtime/runs/<run-id>/evidence/source-registry.json",
  "skills": [ "evidence-backed-web-research" ],
  "budget": { "tokenBudget": 25000, "searchBudget": 8 },
  "outputInstructions": { "outputPath": "sections/python.json", "schemaRef": "<contractRef>",
                          "requiredEvidence": "claim-level", "stopConditions": [...] }
}
```

**Hard constraints (tested):**
- Contains **only this node's** contract ref (never the whole bundle, never other nodes' contracts).
- Contains **only the canonical files this node declares** (`x-contractgraph.contextRefs` / `canonicalContextRequirements`), by **path + hash + optional public summary** — **never private file contents**.
- Dependencies appear as **summary refs + hashes**, never full sections.
- Evidence appears as a **registry ref**, never inline source objects.

**Wiring:** `init.md` gains a step "compile node packets" after manifests. `run.md` producers load `node-packets/<node>/packet.json` and resolve refs instead of loading full contract + all canonical + all sections.

---

## 3. Compact handoffs + cacheable dependency summaries

**New script:** `scripts/build_dependency_summary.py`.
**Emits:** `runtime/runs/<run-id>/summaries/<node>.summary.json` with a content `summaryHash`.

**Summary schema** (`scripts/schemas/dependency-summary.schema.json`):
```jsonc
{
  "nodeId": "baseline-assessment", "contractVersion": "...", "aggregationPath": "baselineAssessment",
  "summaryHash": "<sha256 of canonical content excluding this field>",
  "handoff": { /* the producer-authored bounded `handoffSummary` block, or a derived ref-only minimum */ },
  "evidenceRefs": [ "SRC_ab12…" ], "confidence": 0.86,
  "fullSectionRef": "sections/baseline-assessment.json", "producedAt": null
}
```
- Deterministic: extracts the contract's `handoffSummary` block (decision 3) and hashes it. No prose, no full source objects.
- **Cache tie-in:** downstream packets reference `{depNode, summaryHash}`. `cache_key.py` folds `depSummaryHashes`. Unchanged upstream ⇒ identical hash ⇒ downstream cache key unchanged ⇒ skip. Changed upstream ⇒ new hash ⇒ downstream re-runs. This is the **summary-cache-invalidation** contract.

**Wiring:** `run.md` — on node accept, build its dependency summary; downstream nodes read summaries, not sections. Reinforce existing "never full transcripts between nodes" with the concrete artifact path.

---

## 4. Evidence deduplication (upstream registry)

**New script:** `scripts/source_registry.py` (or extend `merge_verified_sections.py`).
**Emits/maintains:** `runtime/runs/<run-id>/evidence/source-registry.json`, built **incrementally as nodes are accepted** (not only at final merge).

- Dedup by **normalized canonical URL** (deterministic: lowercase host, strip fragment + `utm_*`, normalize trailing slash) → single `SRC_<hash>` id. Full metadata (`title,url,publisher,sourceType,publicationDate,accessDate,reliability`) stored **once**.
- **Section contract change:** replace inline `sources[]` with `evidence: [{ "ref": "SRC_…", "claims": [...] }]`. Claim-level evidence is preserved (policy requires it) but title/url/publisher are **not** duplicated per section.
- Kills the "462 per-node source objects, same URL under different ids" waste; makes handoffs ref-only.
- Apply fully to **study-plan** node contracts; land the same schema shape in company-research contracts without running them.

---

## 5. Issue-only verification (formalize + guard)

Behavior is already correct. Actions only:
- **New schema** `scripts/schemas/verifier-verdict.schema.json`:
  `{ status, issues:[{path, issueType, claim?, staleClaim?, repairInstruction}], conflicts:[...], confidence }`,
  `additionalProperties:false`, and **forbid** any content/rewrite field (no `content`, `section`, `rewrite`, `output`).
- Align `run.md` verifier return field names to the schema (require `path` per issue).
- Keep producer≠verifier (already enforced). Add one line to `docs/token-optimization.md`.
- **Test** `t_verifier_issue_only()`: a valid verdict passes; a verdict carrying a `content`/`rewrite` field **fails** validation.

---

## 6. Quota-aware (weighted) concurrency

**Policy change** — add to `policies.json.execution`:
```jsonc
"concurrency": {
  "classing": { "heavyResearch": "hasWebTools", "lightSynthesis": "noWebTools",
                "verifier": "role=section-verifier", "globalVerifier": "role=global-verifier" },
  "modes": {
    "default":        { "heavyResearch": 2, "lightSynthesis": 3, "verifier": 2, "globalVerifier": 1 },
    "tokenEfficient": { "heavyResearch": 1, "lightSynthesis": 2, "verifier": 1, "globalVerifier": 1 },
    "timeBounded":    { "heavyResearch": 2, "lightSynthesis": 3, "verifier": 2, "globalVerifier": 1 }
  }
}
```
**Safety rule (spec):** `heavyResearch` cap **stays ≤ 2 in every mode** — time-bounded raises only light/verifier caps, never research, to prevent unsafe research bursts.
**Class determination (deterministic):** web tools in agent-manifest ⇒ `heavyResearch`; Read/Write-only ⇒ `lightSynthesis`; verifier/global roles by name.
**New/extended planner:** extend `scripts/dry_run.py` (or `scripts/schedule_plan.py`) to compute the admissible concurrent set per tick without exceeding any per-class cap.
**Wiring:** `run.md` replaces "flat cap per mode" with per-class weighted admission. Keep the legacy `concurrencyModes` integers as an aggregate ceiling for backward-compat.
**Test** `t_weighted_concurrency()`: never admits > class cap; `timeBounded` never admits > 2 heavy.

---

## 7. Selective TOON benchmarking (supported, runtime-disabled)

`toon_codec.py` stays as-is. Add:
- **Benchmark harness** `scripts/toon_benchmark.py`: for a JSON array payload → `{jsonBytes, toonBytes, charSavingsPct, estTokenSavingsPct (estimated:true), roundTripLossless (decode(encode)==x), schemaValid (both against item schema via jsonschema_lite)}`.
- **Policy** — add `policies.json.tokenEfficiency.toon`:
  ```jsonc
  { "mode": "benchmark_before_enable", "enabledForRuntime": false, "enabledForBenchmarkOnly": true,
    "eligibleArrays": ["resources","milestones","checkpoints","sourceRegistry"],
    "minCharSavingsPct": 15, "requireRoundTripLossless": true, "requireSchemaValid": true }
  ```
  ⇒ **TOON never touches a normal runtime artifact.** Only the optimized benchmark config may enable it, only for eligible uniform arrays, only when savings ≥ threshold AND lossless AND schema-valid.
- **Decision artifact** `runtime/compiled/study-plan/toon-benchmark.json` — per eligible array: measured numbers + `enable:true|false`. Sonnet fills this from the **static study-plan fixture arrays** (deterministic, no model). Model-output-quality dimension is marked `pending` (only knowable during the real benchmark run).
- **Tests:** `t_toon_roundtrip()` (lossless on eligible shapes), `t_toon_token_compare()` (JSON vs TOON size + decision-flag threshold logic).

---

## 8. PDF-to-Markdown extraction (deterministic, offline, Windows-safe)

**New script:** `scripts/pdf_extract.py`. Local `pypdf` for embedded text; optional `pytesseract`+`Pillow` (or `ocrmypdf`) OCR fallback. **No model / no network / no API key.**

Behavior:
- Input: a PDF path or a directory to scan (e.g. `context/canonical/resume/`).
- Compute **SHA-256** of the PDF.
- Extract embedded text **page by page**, preserving page provenance (`## Page N` headers + structured page map).
- Write Markdown **beside** the PDF using the **same basename** (handles filenames with spaces, e.g. `resume.pdf` → `resume.md`).
- Write `extraction.json`: `{ sourcePdf, sha256, pageCount, extractor, extractorVersion, ocrUsed, pages:[{page, chars, method:"embedded"|"ocr"|"ocr_unavailable"}], notes }`.
- **Skip unchanged:** if `extraction.json` exists with matching sha256 → no-op.
- **OCR only when a page has no usable embedded text.** If OCR deps absent → mark page `method:"ocr_unavailable"`, **never invent text**.
- **Privacy:** outputs land under `context/canonical/resume/` (already git-ignored) → both `.pdf` and `.md` stay private. `hook_guard.py` does not touch these paths.
- CLI: `python scripts/pdf_extract.py <pdf-or-dir> [--force] [--ocr auto|never|only]`.
- **Test** `t_pdf_extract()`: use a **tiny synthetic public PDF fixture** (checked into `evals/fixtures/`, never the private resume) → asserts `.md` + `extraction.json` with page provenance + sha256; re-run asserts skip; blank page asserts no invented text.
- **Implementation run:** Sonnet runs the extractor once on the user's real private resume locally; report `pageCount` + `sha256` + method only (content and filename stay private).

---

## 9. Study-plan benchmark preparation (do not execute)

- **Complete the compiled fixture:** generate the missing `skill-manifest.json`, `capability-manifest.json`, `compilation-report.md` under `runtime/compiled/study-plan/` so it is a full init output.
- **Two configs** under `evals/benchmarks/study-plan/`:
  - `baseline.config.json`: `{ "format":"json", "cache":"cold", "contextSlicing":true, "toon":false, "concurrency":2, "repairs":"blocking-only" }`
  - `optimized.config.json`: `{ "format":"json", "toon":"selective", "dependencySummaries":true, "evidenceDedup":true, "verification":"issue-only", "contextPackets":"cache-aware", "concurrency":2, "cache":"warm-allowed" }`
  Same contract, context, models, concurrency (2) — controlled comparison. Both use context slicing; optimized adds compact-handoff + dedup + TOON + cache-aware packets.
- **`input.json`** fixture: `{ "learnerGoal": "..." }` (+ optional `targetDate`,`hoursPerWeek`) from the synthetic "Sam" context.
- **Metrics:** each run emits `final/cost.json` (§1) + `benchmark-result.json` (tokens by category, est cost, requests, retries, duration, output size, validation results, semantic quality results). `scripts/benchmark_compare.py` diffs baseline vs optimized → `comparison.json` + markdown table.
- **Do NOT run** either benchmark in this task.

---

## 10. Telemetry normalization (`scripts/telemetry_normalize.py`) — §1 detail

Adapters: `--claude-code FILE` (OTEL/usage JSON with `input_tokens,output_tokens,cache_read_input_tokens,cache_creation_input_tokens`), `--opencode FILE` (session export / stats / message usage), `--local DIR` (per-call records the run drops in `runtime/runs/<id>/telemetry/raw/`).
Canonical `RequestRecord`: `{runtime, model, agent, skill, purpose(producer|verifier|repair|global-verifier), node, attempt, inputTokens, outputTokens, cacheReadTokens, cacheCreationTokens, estimatedCostUsd, durationMs, toolCalls, searches, fetches, outputBytes, finalStatus, available:{...}}`.
Cost from version-pinned `scripts/model_prices.json`; `estimated:true`; null when tokens unavailable.
Aggregates: `byNode, byModel, byPurpose, byAttempt, run` + `coverage`. Output validated against `scripts/schemas/cost.schema.json`. CLI: `--run <dir> [--claude-code] [--opencode] [--local] [--prices] --out <run>/final/cost.json`.

---

## Test matrix (all new `t_*()` in `evals/run_evals.py`)

| Test fn | Category | Asserts |
|---|---|---|
| `t_telemetry_normalize` | token-efficiency | multi-source raw → valid `cost.json`; node/model/purpose/attempt/run rollups correct |
| `t_telemetry_missing_fields` | token-efficiency | missing token source → nulls + `available=false`; no fabrication; `coverage` reported |
| `t_node_cost_aggregation` | token-efficiency | byNode/byModel/byPurpose sums == sum of requests |
| `t_context_packet_relevance` | token-efficiency | packet has only own contract + declared context refs + dep summary refs; not other nodes/canonical |
| `t_packet_privacy_leak` | privacy-leakage | packets carry refs/hashes/public summaries only; no private file *contents* |
| `t_summary_cache_invalidation` | cache-correctness | changed upstream ⇒ new summaryHash ⇒ downstream key changes; unchanged ⇒ identical |
| `t_toon_roundtrip` | token-efficiency | lossless on eligible arrays |
| `t_toon_token_compare` | token-efficiency | JSON vs TOON size; enable flag only when threshold+lossless+schema-valid |
| `t_pdf_extract` | (new) doc-extraction | md+extraction.json w/ provenance+sha256; unchanged-skip; no invented text |
| `t_verifier_issue_only` | (new) verification | verdict schema valid; rewrite field ⇒ fail |
| `t_weighted_concurrency` | retry-targeting/exec | per-class caps respected; timeBounded ≤2 heavy |
| `t_study_plan_compilation` | global-consistency | study-plan compiles full manifest set; domain-neutral (extends `t_genericity`) |

Extend `t_privacy()` to also scan node-packets + summaries for PII.

---

## Docs (cross-reference `token-efficiency.md`, do not duplicate)

- `docs/token-telemetry.md` — sources, `RequestRecord`, `cost.json` aggregation, "never fabricate / mark unavailable", feeding Claude Code OTEL + OpenCode export.
- `docs/token-optimization.md` — the levers (packets, compact handoffs+dep summaries, evidence dedup, issue-only verify, weighted concurrency, caching). Fixes the 4-vs-5 discrepancy; documents `concurrencyModes` + weights.
- `docs/pdf-context.md` — extractor behavior, provenance, OCR policy, privacy/ignored paths, Windows notes, optional local deps.
- `docs/opencode-benchmark.md` — baseline vs optimized configs, metrics, exact OpenCode commands, TOON decision policy.
- Fix `docs/execution.md` (5→4) and update `docs/token-efficiency.md` TOON section to point at the harness + decision file.

---

## Build order for Sonnet (dependency-respecting)

1. `hash`/schemas scaffolding: add `scripts/schemas/*.json` + `scripts/model_prices.json`.
2. `pdf_extract.py` (+ test, + run once on real resume). Independent — do first for a quick win.
3. `telemetry_normalize.py` (+ `cost.schema.json`, + tests). Foundational for benchmark.
4. `build_node_packets.py` (+ schema, + tests) reusing `dry_run.plan()`.
5. `build_dependency_summary.py` + `source_registry.py` (+ schemas, + tests); update `cache_key.py` to fold dep-summary/packet hashes.
6. Contract edits: add `handoffSummary` + `x-contractgraph.contextRefs` + `evidence[]` to **study-plan** node contracts; mirror schema in company-research (no run).
7. Verifier schema + `t_verifier_issue_only`.
8. `policies.json` weighted concurrency + planner + `t_weighted_concurrency`.
9. `toon_benchmark.py` + policy + decision artifact + tests.
10. Complete study-plan compiled fixture + benchmark configs + `benchmark_compare.py`.
11. Command edits (`init.md`, `run.md`) to emit/consume packets, summaries, registry, weighted concurrency, telemetry.
12. Docs. Then `python evals/run_evals.py` green.

---

## Exact OpenCode commands (do NOT run now)

ContractGraph is Claude-Code-native; under OpenCode the workflow is driven by the same `/contractgraph:run` prompt against the study-plan bundle + synthetic context + a config. **Verify OpenCode CLI flags against the installed version** — the prompt string is stable; capture usage via OpenCode session export → `telemetry_normalize --opencode`.

**Baseline:**
```
opencode run "/contractgraph:run \
  --bundle contracts/study-plan \
  --context context/synthetic/study-plan \
  --input evals/benchmarks/study-plan/input.json \
  --config evals/benchmarks/study-plan/baseline.config.json \
  --run-id sp-baseline-01"
# then, after the session:
opencode export --session <id> > runtime/runs/sp-baseline-01/telemetry/opencode.json
python scripts/telemetry_normalize.py --run runtime/runs/sp-baseline-01 \
  --opencode runtime/runs/sp-baseline-01/telemetry/opencode.json \
  --out runtime/runs/sp-baseline-01/final/cost.json
```

**Optimized:** identical, swapping the config and run id:
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
python scripts/benchmark_compare.py \
  --baseline runtime/runs/sp-baseline-01/final/cost.json \
  --optimized runtime/runs/sp-optimized-01/final/cost.json \
  --out evals/benchmarks/study-plan/comparison.json
```

---

## Risks / watch-items

- **Telemetry coverage depends on the runtime exposing usage.** If OpenCode export omits cache-token splits, those stay `null` (never fabricated); the comparison degrades to output-token + bytes proxies. Document this.
- **Evidence-dedup contract change** touches node output schemas → re-validate every study-plan node contract against sample outputs.
- **PDF `pypdf`/OCR deps** are the only third-party additions; keep optional + offline + pinned; guard imports so the rest of the suite runs without them.
- **TOON token savings are char-estimated** until a real benchmark run produces true token counts.
- **`cache_key.py` change** must not break existing keys silently — bump a documented key-schema version.

## Definition of READY (Opus review gate)

- All 12+ new `t_*()` tests present and `python evals/run_evals.py` exits 0 (evidence pasted).
- `cost.json`, node-packet, dependency-summary, verifier-verdict, TOON-decision schemas validate.
- PDF extractor run once on the real resume; provenance + sha256 reported; `.md` confirmed git-ignored.
- TOON confirmed disabled in runtime; enabled only via optimized benchmark config; decision artifact present.
- Weighted concurrency proven to cap heavy research ≤2 in all modes.
- Four docs written + `execution.md` 4-vs-5 fixed.
- Both benchmark configs present; neither benchmark executed.
