# Validation

A node — and eventually the whole run — is accepted only when three independent layers agree. No single layer is sufficient on its own: schema-match alone can accept confident nonsense, and a semantic pass without schema validation has nothing reliable to check claims against.

## Layer 1 — Structural (deterministic)

Pure JSON Schema checks, no model call, no judgment:

| Script | Checks |
|---|---|
| `scripts/validate_node_output.py` | A single node's output against its `node-contracts/<nodeId>.contract.json` `outputSchema` — required fields, types, enums, `additionalProperties: false`. |
| `scripts/validate_final_output.py` | The merged candidate artifact against the bundle's `contract.schema.json`. |
| `scripts/validate_references.py` | Every `evidenceRef` resolves into the global source registry, every `contextRef` resolves into `context-manifest.json`, every `roleId` resolves to a configured role file. |
| `scripts/validate_source_urls.py` | Source URL well-formedness and dedup by `canonicalUrl`; where `policies.json.evidence.requireReachableUrls` is set, flags unreachable URLs for the semantic layer to weigh — it does not judge whether a reachable source actually supports a claim. |

Structural failure triggers one bounded, mechanical repair (haiku tier) — not a semantic rewrite — and re-validates. Persistent failure is `STRUCTURAL_FAILED` (see [execution.md](execution.md) for the state machine).

## Layer 2 — Semantic (verifier subagent)

Structural validation cannot tell whether a claim is true, current, or actually grounded in evidence. That is `section-verifier`'s job, dispatched per accepted-structurally node, and it is never the producing subagent (`workerCannotSelfApprove`).

### Verifier output contract

Every verifier — section-level and global — returns this shape:

```json
{
  "status": "accept | reject",
  "issues": ["..."],
  "repairInstructions": ["..."],
  "unsupportedClaims": ["..."],
  "staleClaims": ["..."],
  "conflicts": ["..."],
  "confidence": { "...": "..." }
}
```

| Field | Meaning | Routes to |
|---|---|---|
| `status` | Overall verdict for this pass. | — |
| `issues` | Human-readable problems found, regardless of category. | `SEMANTIC_FAILED` if non-empty and not otherwise categorized |
| `repairInstructions` | Concrete, actionable fixes handed to the producing subagent's retry — never a bare rejection with no path forward. | drives the retry, not a new state |
| `unsupportedClaims` | Material claims with no resolvable, credible `sources[]` entry. | `EVIDENCE_FAILED` |
| `staleClaims` | Claims older than their `policies.json.freshnessDays` threshold. | `FRESHNESS_FAILED` |
| `conflicts` | Contradictions with an already-accepted dependency section. | `SEMANTIC_FAILED` |
| `confidence` | Per-claim or per-section confidence, carried through to the final artifact's metadata — not used to override a reject. | — |

A verifier never edits the section it reviews — verdict only. It never accepts its own or another node's output as a substitute for the producing subagent's work, and it never declares anything beyond its one node (or, for `global-verifier`, beyond the whole run) complete.

## Layer 3 — Global (Opus, after aggregation)

Once every required node is `ACCEPTED`/`SKIPPED_CACHE` and deterministically merged, `global-verifier` checks the candidate final artifact against `contract.bundle.json.globalValidation[]`:

- every required node is accepted,
- every `evidenceRef` resolves to the global source registry,
- every `contextRef` resolves to the canonical context manifest,
- every `roleId` resolves to a configured role file,
- every ranked recommendation cites its scoring rationale,
- no candidate experience is invented,
- no research claim is represented as canonical user truth,
- no stale source supports a current hiring, compensation, or organization-health claim,

plus the final artifact validating against `contract.schema.json`'s `finalOutputSchema`. Global-verifier uses the same output contract as `section-verifier`; a reject routes back to targeted repair of only the implicated node(s) via `repairInstructions` — never a full-run restart.

## Evidence Model

Governed by `policies.json.evidence`:

- `requireReachableUrls`, `requireClaimLevelEvidence` — every material claim needs its own resolvable source, not a single blanket citation for a whole section.
- `preferPrimarySources` and `sourcePriority` (`official_regulatory` > `official` > `official_documentation` > `official_engineering` > `job_posting` > `research_paper` > `reputable_news` > `candidate_report` > `community`) — the verifier flags heavy reliance on low-priority sources where a higher-priority one should exist.
- `candidateReportClaimsRequireQualification` — a claim sourced from an individual's report must be presented as one report, not an established fact.
- `singleAnecdoteCannotBecomeFrequencyClaim` — one anecdote cannot be generalized into "commonly" or "usually."

## Freshness Model

`policies.json.freshnessDays` sets a maximum claim age per category (`activeJobPosting: 30`, `hiringSignals: 90`, `compensation: 180`, `interviewProcess: 540`, `recentDevelopments: 180`, `companyStructure: 365`, `foundationalEngineeringMaterial: 1825`). A claim older than its category's window is a `staleClaim` and blocks acceptance regardless of how well-sourced it otherwise is — a well-cited stale claim is still stale.

See [graph-compilation.md](graph-compilation.md) for how these layers gate node acceptance at compile-plan level, and [execution.md](execution.md) for how they gate it at run time.
