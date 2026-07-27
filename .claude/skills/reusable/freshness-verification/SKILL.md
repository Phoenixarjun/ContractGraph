---
name: freshness-verification
description: Use when a claim is time-sensitive (active job postings, hiring signals, compensation, interview process, recent developments, company structure, foundational engineering material) and its supporting source's date must be checked against policies.json.freshnessDays before the claim can be trusted. Triggered by research nodes before writing output and by section-verifier/global-verifier during /contractgraph:run. Not for tiering source credibility (source-quality-assessment) and not for finding sources (evidence-backed-web-research).
---

# Freshness Verification

## Overview

A credible source can still be too old to support a claim about the present. This skill's one job is to compare each time-sensitive claim's source date against the relevant `freshnessDays` threshold and report which claims are stale — it does not judge source credibility or find new sources.

## When to Use

- A section makes any claim in a time-sensitive category before it's written or verified.
- A verifier needs to check whether an accepted section's claims still meet freshness policy.

**When NOT to use:** assessing whether a source is credible (`source-quality-assessment`), or discovering sources (`evidence-backed-web-research`).

## Inputs

- Claims with their supporting source(s) and each source's `date`.
- `policies.json.freshnessDays`: `activeJobPosting: 30, hiringSignals: 90, compensation: 180, interviewProcess: 540, recentDevelopments: 180, companyStructure: 365, foundationalEngineeringMaterial: 1825`.
- The current run date, to compute source age.

## Outputs

A stale-claim list: `{ claimRef, sourceRef, category, sourceDate, ageDays, thresholdDays, status: "fresh" | "stale" }`.

## Procedure

1. Classify each time-sensitive claim into exactly one `freshnessDays` category based on its subject matter (a claim about current openings is `activeJobPosting`, not `recentDevelopments`).
2. Compute `ageDays` as run date minus source `date`.
3. Compare `ageDays` against the category's threshold; mark `stale` if it exceeds it.
4. For a claim supported by multiple sources of different ages, use the freshest source that actually supports the claim's specific assertion — do not average dates or let one fresh but tangential source rescue a stale core claim.
5. Return the full stale-claim list, including claims that pass, so the caller has a complete freshness picture rather than only failures.
6. Do not rewrite or drop stale claims yourself — flag them for the producing node or verifier to act on.

## Failure Behavior

If a claim's category is ambiguous, classify it under the stricter (shorter) applicable threshold rather than the more lenient one, and note the ambiguity.

## Privacy Restrictions

Not applicable — this skill only compares dates on public source records, never canonical or private context.

## Red Flags

- A current-hiring or compensation claim resting on a source older than its threshold.
- Foundational engineering material forced into a short-threshold category (or vice versa) to avoid a stale flag.
- Silently dropping a stale claim instead of reporting it.
