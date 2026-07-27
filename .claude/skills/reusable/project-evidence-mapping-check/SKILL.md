---
name: project-evidence-mapping-check
description: Use when a node's output claims the candidate built or contributed to specific projects, and each claim must be independently re-verified against canonical evidence with truth boundaries respected. Triggered by section-verifier on project-deep-dive and resume-analysis outputs, and by global-verifier's no-invented-experience rule during /contractgraph:run. Not for producing the mapping itself (resume-evidence-mapping, profile-alignment) — this skill only re-checks it. Must be run by a subagent instance different from the one that produced the node.
---

# Project Evidence Mapping Check

## Overview

Project claims are the highest-stakes truth-boundary risk in the whole workflow — an invented project detail is fabricated experience. This skill's one job is to independently re-verify that every project-related claim in a node's output maps to real canonical evidence, and that no detail (scale, technology, outcome, role) exceeds what canonical context actually supports.

## When to Use

- `section-verifier` checking `project-deep-dive` or `resume-analysis` output for invented or exaggerated project claims.
- `global-verifier`'s `globalValidation[]` "no invented candidate experience" rule, applied across the merged artifact.

**When NOT to use:** producing the initial project-to-evidence mapping (that's `resume-evidence-mapping`/`profile-alignment`'s job) — this skill is the independent re-check afterward, not the first pass.

## Inputs

- The node output's project claims (name, description, technologies, scale, candidate's role, outcomes).
- Canonical context (`context/canonical/experience/`, `documents/`, `projects/`; never `context/private/`).

## Outputs

`{ status: "passed" | "failed", unsupportedClaims: [ { claimPath, contextRef?, reason } ], issues: [...], repairInstructions: [...], confidence }`.

## Procedure

1. For each project claim, re-locate the canonical evidence independently — do not simply trust the producing node's cited `contextRef` without opening it.
2. Compare every detail (scale, technology stack, candidate's specific role/contribution, outcome/impact) against what the canonical source states — flag any detail that goes beyond it, even if plausible-sounding.
3. Distinguish reasonable inference the canonical text directly supports from added specificity the candidate never stated (e.g. canonical text says "built a caching layer"; output claiming "reduced latency by 40%" with no canonical backing is unsupported).
4. Flag any project mentioned in the output with no canonical project/experience entry at all — this is the most severe finding and must be listed first.
5. Return every unsupported detail with its exact path and reason; `"passed"` only when every project claim's every detail traces to canonical evidence.

## Failure Behavior

If canonical evidence is vague about a detail (present but unspecific), classify conservatively as unsupported for that specific detail rather than assuming it's fine.

## Privacy Restrictions

Never read `context/private/`; never quote more canonical text in the report than needed to justify the finding.

## Red Flags

- A project claim in the output with zero canonical trace.
- An outcome/metric more specific than the canonical source states.
- Reusing the producing node's own `contextRef` citations without independently opening and confirming them.
