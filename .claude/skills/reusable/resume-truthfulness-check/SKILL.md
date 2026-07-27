---
name: resume-truthfulness-check
description: Use when a resume enhancement or resume-analysis output must be independently checked to ensure no claim asserts unproven experience — the final truth-boundary gate before a resume-related node is accepted. Triggered by section-verifier on resume-analysis output, and by global-verifier's no-invented-experience rule during /contractgraph:run. Not for producing the resume/canonical mapping itself (resume-evidence-mapping) — this skill only re-checks the result. Must be run by a subagent instance different from the one that produced the node.
---

# Resume Truthfulness Check

## Overview

Resume enhancement carries direct real-world consequence for the candidate — an overstated claim here can surface in an actual interview. This skill's one job is to independently re-verify that a resume-analysis or resume-enhancement output never asserts experience, scope, or outcomes beyond what canonical evidence supports, flagging any invented or overstated claim as a hard rejection, not a stylistic note.

## When to Use

- `section-verifier` checking `resume-analysis` output (any role) before acceptance.
- `global-verifier`'s `globalValidation[]` "no invented candidate experience" rule, specifically for resume-facing content.

**When NOT to use:** producing the initial resume-to-canonical mapping (`resume-evidence-mapping`'s job) — this is the independent truthfulness gate applied after that mapping exists.

## Inputs

- The resume-analysis output (enhancement suggestions, keyword guidance, project ordering, requirement mapping).
- Canonical context (`context/canonical/experience/`, `documents/`, `skills.md`; never `context/private/`).

## Outputs

`{ status: "passed" | "failed", unsupportedClaims: [ { claimPath, contextRef?, reason } ], issues: [...], repairInstructions: [...], confidence }`.

## Procedure

1. For each suggested enhancement or existing resume claim, re-locate the specific canonical fact it rests on — do not accept the producing node's `truthBoundary` classification at face value.
2. Flag any claim classified `supported` or `enhanceable` by the producing node that, on independent inspection, actually adds unproven scope, seniority, technology, or outcomes.
3. Check that reworded/enhanced language stays a rephrasing of the canonical fact and does not introduce quantified outcomes, leadership scope, or technologies the canonical evidence never states.
4. Confirm every requirement-mapping claim ("candidate meets X requirement because Y") traces to real canonical evidence, not aspirational framing.
5. Return every overstated or invented claim as a distinct `unsupportedClaims` entry with the exact path and reason; `"passed"` only when the entire output stays within canonical truth boundaries.

## Failure Behavior

If an enhancement's wording is ambiguous about whether it adds unproven substance, treat it as a violation and require tighter wording rather than giving the benefit of the doubt.

## Privacy Restrictions

Never read `context/private/`; never include more canonical detail in the report than needed to justify the finding.

## Red Flags

- An enhancement that adds a quantified outcome absent from canonical evidence.
- Accepting the producing node's own truth-boundary labels without independent re-verification.
- Vague wording that could plausibly be read as claiming more experience than canonical evidence supports.
