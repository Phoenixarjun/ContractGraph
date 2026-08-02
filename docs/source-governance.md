# Source Governance

## The Problem

A research run accumulates sources fast. Without governance, a node's evidence
list becomes a mix of official documentation, respected books, and unreviewed
personal blogs — all presented with equal weight, none bounded in number.

`scripts/source_registry.py` deduplicates by normalized URL and assigns a
canonical id, so the same real-world source always gets the same `SRC_` id no
matter which node cites it first. That is all it does: it does not score
authority, freshness, uniqueness, accessibility, or actionability, and it does
not rank or bound how many sources survive per node. `scripts/source_scoring.py`
is the layer that does.

## `scripts/source_scoring.py`: six dimensions, one deterministic score

Every source is scored on:

| Dimension | Weight | How it's computed |
|---|---|---|
| Authority | 0.35 | tier rank against `AUTHORITY_TIERS` (below), from a `type`/`sourceType` field |
| Freshness | 0.20 | age of `publicationDate` vs. a reference window (default: `policies.json.freshnessDays.foundationalEngineeringMaterial`) |
| Uniqueness | 0.15 | 1.0 unless collapsed as a near-duplicate (below) |
| Accessibility | 0.15 | well-formed-URI check by default; a `--reachability-report` (e.g. from `validate_source_urls.py --check-network`) overrides with measured reachability |
| Actionability/relevance | 0.15 | passthrough from the source's own `relevanceScore`/`confidence`, since judging practical value is not something a deterministic script can invent |

**Authority tiers**, matching the stated preference order (highest to
lowest): `official_documentation` → `research_paper` →
`official_engineering` → `book` → `course` → `technical_publication` →
`community`. A `type`/`sourceType` value is mapped via `TYPE_ALIASES`; an
unrecognized value defaults to the **middle** tier (`technical_publication`),
never the best or the worst — absence of a signal is not evidence either way.

**Never fabricate:** any dimension the script can't actually measure
(missing `publicationDate`, no reachability report, no relevance score)
defaults to a flagged neutral `0.5`, and the entry's `unscoredDimensions`
names exactly which ones were defaulted — the total score is never presented
as fully measured when part of it isn't.

## Deduplication beyond exact URLs

Two sources on the **same host** whose titles have token-Jaccard similarity
`> 0.6` are treated as covering the same ground; the lower (pre-uniqueness)
weighted score of the pair is dropped from ranking entirely — a true
duplicate isn't "lower quality", it's redundant, so it doesn't even compete
for a kept slot. `duplicatesDropped` and the `duplicates` list report exactly
what was collapsed, and why, for auditability.

## Bounding: 5-10 per node, archive the rest

`rank(sources, policies, min_n, max_n, required_refs, ...)` sorts
deterministically (score descending, then URL ascending for stable
tie-breaking) and keeps up to `--max` (default 10). Sources beyond that are
**archived**, not deleted — `evidence/source-ranking.json`'s `archived` list
preserves them for anyone who wants the fuller picture. If fewer than
`--min` (default 5) genuinely exist, all of them are kept (the script never
invents sources to hit a target).

**A required ref is never archived.** `--required-refs` names sources that
are the sole support for some specific claim; they're kept regardless of
rank, and they're also exempted from the deduplication step (never dropped
as a "duplicate" either) — losing the only source behind a claim would be
worse than keeping a mediocre one.

## What this does NOT do to existing content

`resources[]` inside each node's accepted section (`sections/<id>.json`) is a
`researchOwnedField` per `contract.bundle.json`'s `stateOwnership` block —
migrating an existing run does not prune or reorder those arrays.
`scripts/migrate_run_metadata.py` instead writes a **separate** governance
artifact, `evidence/source-ranking.json`, alongside the untouched sections —
scored, ranked, and bounded, without touching accepted research content. A
future run's node producers are expected to call `source_scoring.py` before
finalizing their own `resources[]` (see `run.md` step 16), so newly generated
content is bounded at the source rather than pruned after the fact.

## Running It Directly

```bash
python scripts/source_scoring.py --sources <sources.json> \
    --policies contracts/study-plan/policies.json --min 5 --max 10
```

The output names `kept`, `archived`, `duplicates`, `duplicatesDropped`,
`totalConsidered`, and per-entry `unscoredDimensions`, so any ranking decision
can be traced back to the dimension that drove it.

## Tests

`evals/run_evals.py` covers official documentation outranking community
content, near-duplicate collapse on the same host (with an unrelated third
source surviving untouched), bounded keep-counts under both plain and
required-ref scenarios, and deterministic ordering across repeated runs on
identical input.
