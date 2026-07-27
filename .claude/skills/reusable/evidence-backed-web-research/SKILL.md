---
name: evidence-backed-web-research
description: Use when a subagent must research factual claims (company facts, role expectations, interview patterns, technical material, market data, etc.) from the live web and every claim in its output must trace to a reachable, credible source. Triggered by any research node (company-intelligence, role-intelligence, dsa, hld, lld, behavioral, and similar) during /contractgraph:run. Not for scoring or tiering sources already collected (source-quality-assessment) and not for checking whether a claim's source is stale (freshness-verification).
---

# Evidence-Backed Web Research

## Overview

Research is only as good as its citations. This skill's one job is to turn a research question into a set of claims where **every material claim carries at least one reachable, attributable source record** — never a claim asserted from the model's own training-data memory presented as current fact. It is invoked by an agent holding `WebSearch` and `WebFetch`; it does not decide source credibility tiers (that is `source-quality-assessment`) or check staleness (that is `freshness-verification`) — it only produces claims paired with evidence.

## When to Use

- A node's contract requires claims about a company, role, technology, market, or process that Claude cannot know are current without checking.
- Any `x-contractgraph.completionRules` mentioning source URLs, evidence, or citations.

**When NOT to use:** scoring or ranking sources already gathered, checking a date against a freshness threshold, or mapping claims to canonical candidate context — those are separate skills.

## Inputs

- The research question(s) / topics the node needs answered.
- Any prior-section context needed to scope the search (e.g. target roles, company name).

## Outputs

A list of claim → evidence pairs, each evidence entry shaped as:
`{ sourceRef, title, url, publisher, type, date, accessDate, supportedClaims: [...], confidence }`.

## Procedure

1. Decompose the research question into discrete, checkable claims before searching — do not search vaguely and free-associate claims afterward.
2. Search, preferring official/primary sources (official docs, company engineering blogs, regulatory filings, job postings) over secondary aggregation.
3. Fetch and read enough of each candidate source to confirm it actually supports the specific claim, not just a related topic.
4. Record every source used with `sourceRef, title, url, publisher, type, date, accessDate, supportedClaims, confidence` — never a bare URL with no `supportedClaims` linkage.
5. Label any single first-person account (forum post, review site, one interview report) as `candidate_report`/anecdotal — never let it stand in as a general or frequency claim.
6. Drop or explicitly flag any claim that no reachable source supports after a reasonable search effort — do not invent a citation to fill the gap.

## Failure Behavior

If a claim cannot be sourced after exhausting reasonable search effort, omit the claim or mark it `unsupported` with the search effort noted — never fabricate a URL or backfill from memory.

## Privacy Restrictions

Never search for or include private canonical context (`context/private/`) in a query or output; this skill produces public research only.

## Red Flags

- A claim with no `sourceRef`.
- A single anecdotal report generalized into "commonly reported" or similar frequency language.
- A URL that was never actually fetched/confirmed to support the claim it's attached to.
