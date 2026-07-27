---
name: ranking-justification-check
description: Use when a node's output contains any ranked, prioritized, or scored list (top patterns, priority roles, fit rankings, recommendation order) and each ranked item must cite the rationale behind its position. Triggered by section-verifier and global-verifier during /contractgraph:run, especially for dsa, hld, lld, company-initiatives, profile-alignment, and application-strategy outputs. Not for checking whether the underlying evidence itself is supported (evidence-support-check). Must be run by a subagent instance different from the one that produced the node.
---

# Ranking Justification Check

## Overview

A ranking without a stated rationale is an unfalsifiable opinion. This skill's one job is to verify that every ranked or prioritized item in a node's output cites the concrete basis for its position — frequency of evidence, requirement weight, risk level, or similar explicit criteria — and that the stated rationale is internally consistent with the ranking order itself.

## When to Use

- A node's contract requires a ranked/ordered/scored list (`topPatterns`, `roleTracks` priority, `priorityRecommendations`, fit rankings, application priority order).
- `global-verifier`'s `globalValidation[]` rule requiring ranked recommendations to cite scoring rationale.

**When NOT to use:** checking whether the evidence underlying a ranked item's claims is itself supported (`evidence-support-check`) — this skill only checks that the ranking has a stated, consistent rationale, not the evidence quality behind each claim.

## Inputs

- The node output's ranked/ordered/scored list(s).
- Each item's stated rationale or scoring criteria, if present.

## Outputs

`{ status: "passed" | "failed", issues: [ { itemPath, description } ], repairInstructions: [...], confidence }`.

## Procedure

1. Locate every ranked/ordered/scored collection in the output (explicit `rank`/`priority`/`score` fields, or implicit ordering presented as meaningful).
2. For each item, confirm a rationale field or inline justification exists — flag any ranked item with no stated basis for its position.
3. Check that the stated rationale is directionally consistent with the actual rank (e.g. an item ranked #1 whose rationale describes it as lower-frequency than item #2 is an inconsistency, not just a missing field).
4. Where rationale relies on evidence strength (e.g. "explicitly reported" vs. "general foundation"), confirm the ranking doesn't rank a foundation-only item above an explicitly-reported item without explanation.
5. Return every unjustified or inconsistent ranked item as a distinct issue with its exact path — do not average or generalize across the whole list.

## Failure Behavior

If a list's ordering appears to be simple alphabetical/input order rather than a meaningful ranking, flag it as `ambiguous_ranking_intent` rather than assuming justification isn't required.

## Privacy Restrictions

Not applicable beyond the standard rule: never read `context/private/`.

## Red Flags

- A ranked list with no rationale field anywhere.
- A rationale that contradicts the stated rank.
- Treating "the list exists" as sufficient without checking each item's justification.
