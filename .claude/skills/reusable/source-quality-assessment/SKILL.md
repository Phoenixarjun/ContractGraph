---
name: source-quality-assessment
description: Use when a set of already-collected sources (from evidence-backed-web-research or a prior node) needs to be tiered and scored for credibility before a claim can be trusted or a section accepted. Triggered by research nodes composing their own output and by section-verifier/global-verifier during /contractgraph:run. Not for finding new sources (evidence-backed-web-research) and not for checking whether a source's date is still fresh enough (freshness-verification).
---

# Source Quality Assessment

## Overview

Not all reachable sources are equally trustworthy. This skill's one job is to tier and score a set of already-gathered sources against a fixed priority order, and to flag when a claim leans on a lower tier than the claim's importance warrants. It operates over source records already produced — it does not search the web itself.

## When to Use

- A research node has gathered sources and needs to weight/rank them before writing its output.
- A verifier (section-verifier, global-verifier) needs to check whether a section over-relies on weak sources.

**When NOT to use:** discovering new sources from scratch, or checking a source's recency — use `evidence-backed-web-research` and `freshness-verification` respectively.

## Inputs

- A list of source records (`sourceRef, title, url, publisher, type, date, supportedClaims`).
- `policies.json.evidence.sourcePriority`: `official_regulatory > official > official_documentation > official_engineering > job_posting > research_paper > reputable_news > candidate_report > community`.

## Outputs

Per-source tier/score, plus a flags list: `{ sourceRef, tier, score, flag?: "anecdote_as_frequency" | "low_tier_for_material_claim" | "unqualified_candidate_report" }`.

## Procedure

1. Assign each source its tier by matching `type` against `sourcePriority`, highest tier first.
2. Score sources within a tier by specificity to the claim and recency where relevant (do not conflate this with freshness policy compliance — that is a separate check).
3. For each claim, compare its material weight (is it foundational, or a headline hiring/compensation/culture claim) against the tier of its supporting source(s); flag `low_tier_for_material_claim` when a high-stakes claim rests only on `candidate_report`/`community` sources and an `official`/`job_posting` source was plausibly available.
4. Flag `unqualified_candidate_report` when a `candidate_report` source is presented without hedging language (e.g. "one candidate reported" vs. bare assertion).
5. Flag `anecdote_as_frequency` when a single source is used to support language like "commonly", "usually", "most candidates" without a second corroborating source.
6. Return the per-source tier/score and the flags list — do not rewrite the claims yourself; that is the producing node's job.

## Failure Behavior

If a source's `type` doesn't map to any tier in `sourcePriority`, treat it as the lowest tier and flag `untiered_source` rather than guessing a placement.

## Privacy Restrictions

Never tier or reference `context/private/` material as a "source" — this skill operates only on public research sources.

## Red Flags

- A headline claim resting solely on `community`/`candidate_report` sources.
- Frequency language backed by exactly one source.
- Silent upgrading of a source's tier without justification.
