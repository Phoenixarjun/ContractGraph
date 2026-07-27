---
name: profile-alignment
description: Use when a subject's (candidate's) canonical evidence must be mapped against a target's (role, company, program) expectations to produce fit, gaps, and positioning. Triggered by profile-alignment, application-strategy, company-initiatives, networking-referral, and project-deep-dive nodes during /contractgraph:run. Not for mapping resume document claims specifically (resume-evidence-mapping) and not for detecting contradictions across already-accepted sections (cross-section-contradiction-detection).
---

# Profile Alignment

## Overview

Fit assessment must never outrun evidence. This skill's one job is to map canonical ground truth (the subject's real background, from `context/canonical/`) against a target's stated or researched expectations, producing a fit assessment where every claim of alignment or gap traces to a canonical context reference — never an inferred or invented qualification.

## When to Use

- A node must produce fit scores, green/red flags, gaps, or positioning language for a subject against a target (role, company, program).
- Any node whose contract requires a `contextEvidence[].contextRef` field pointing into canonical context.

**When NOT to use:** mapping resume-document-specific claims to requirements (use `resume-evidence-mapping`), or checking consistency across already-accepted sections (use `cross-section-contradiction-detection`).

## Inputs

- Canonical context (`context/canonical/` — profile, experience, skills, preferences; never `context/private/`).
- Target expectations (researched role/company requirements, or program requirements).

## Outputs

Fit assessment: `{ requirement, status: "met" | "partial" | "gap", contextRef, evidenceSummary, confidence }`, plus an overall positioning summary and green/red flag list.

## Procedure

1. Enumerate the target's discrete expectations (skills, experience levels, domains) from the researched or provided requirements.
2. For each expectation, search canonical context for direct supporting evidence — not adjacent or generously-interpreted evidence.
3. Record every match with its exact `contextRef` (file path); if no canonical evidence exists, mark the requirement a `gap` — never infer that the subject "probably" has it.
4. Distinguish `met` (direct canonical evidence) from `partial` (adjacent but not exact evidence) explicitly; do not round partial up to met.
5. Compose green/red flags and positioning language strictly from the requirement-by-requirement mapping — no claim in the summary may lack a corresponding `contextRef` entry.
6. Surface gaps plainly; a fit assessment that hides gaps to look favorable is a failed output, not a diplomatic one.

## Failure Behavior

If canonical context is too sparse to assess a requirement, mark it `unknown` rather than guessing `met` or `gap`.

## Privacy Restrictions

Never read or reference `context/private/`; never copy raw canonical text verbatim into a public-facing output beyond what's needed to support the `contextRef`.

## Red Flags

- A `met` status with no `contextRef`.
- Positioning language stronger than the underlying evidence supports.
- Gaps omitted or softened beyond what the evidence shows.
