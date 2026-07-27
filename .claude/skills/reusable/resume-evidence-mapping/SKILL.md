---
name: resume-evidence-mapping
description: Use when a resume or similar candidate document's claims must be mapped against canonical evidence and target requirements, with any enhancement or rewording bounded by what canonical context actually supports. Triggered by resume-analysis and behavioral nodes during /contractgraph:run. Not for general fit/positioning against a role (profile-alignment) and not for verifying the final resume output never overstates experience (resume-truthfulness-check, a separate verifier skill).
---

# Resume Evidence Mapping

## Overview

A resume claim is only as good as the canonical fact behind it. This skill's one job is to map each resume-document claim (or proposed resume enhancement) to its supporting canonical evidence and to the target requirement it addresses, drawing an explicit truth boundary between what canonical context supports and what would be fabrication.

## When to Use

- A node analyzes or proposes enhancements to a resume or similar candidate document against role/company requirements.
- Any node whose contract includes a `truthBoundary` or "no invented experience" completion rule.

**When NOT to use:** general role/company fit assessment beyond a specific document (`profile-alignment`), or the final truthfulness gate on a resume output (`resume-truthfulness-check`, which is a verifier, not a producer).

## Inputs

- Resume/document text (or references to it).
- Canonical context (`context/canonical/experience/`, `documents/`, `skills.md`; never `context/private/`).
- Target requirements (role/company expectations) the resume is being evaluated or tuned against.

## Outputs

`{ requirement, resumeClaim, contextRef, truthBoundary: "supported" | "enhanceable" | "unsupported", suggestedWording? }` per mapped item, plus a flag list for any resume claim with no canonical backing found.

## Procedure

1. Extract discrete claims from the resume/document (each bullet or assertion, not the document as a whole).
2. For each claim, search canonical context for the specific supporting fact; record the exact `contextRef`.
3. Classify each claim's `truthBoundary`: `supported` (canonical evidence matches as-is), `enhanceable` (canonical evidence exists but wording could better match the target requirement without adding unproven substance), or `unsupported` (no canonical evidence found).
4. For `enhanceable` items, propose wording that stays within the canonical fact — reframing, not fabricating; never add scope, scale, or outcomes the canonical evidence doesn't state.
5. For `unsupported` items, flag them explicitly rather than silently letting them pass through to the output.
6. Do not resolve requirements that have no resume claim mapped to them — report them as unaddressed, for the calling node to decide how to handle.

## Failure Behavior

If canonical evidence is ambiguous about whether it supports a claim, classify conservatively as `unsupported` rather than `supported`.

## Privacy Restrictions

Never read `context/private/`; never copy verbatim personal identifiers beyond what the resume/document itself already required.

## Red Flags

- A resume claim marked `supported` with no `contextRef`.
- Enhanced wording that adds scale, outcomes, or responsibilities absent from canonical evidence.
- Silent omission of an `unsupported` claim instead of flagging it.
