---
name: cross-section-contradiction-detection
description: Use when two or more accepted node sections must be checked against each other for contradictory claims before they are merged into the aggregated artifact. Triggered by application-strategy, profile-alignment, resume-analysis, section-verifier (against a node's direct dependencies), and global-verifier (across the full merged artifact) during /contractgraph:run. Not for checking a single section's internal evidence support (evidence-support-check) or a single claim's freshness (freshness-verification).
---

# Cross-Section Contradiction Detection

## Overview

Sections that each pass their own verification can still disagree with each other. This skill's one job is to compare claims across two or more accepted sections and surface exact conflicting pairs — it does not judge either section's internal quality, only their mutual consistency.

## When to Use

- A node's output extends or depends on prior accepted sections and must not contradict them.
- `section-verifier` checking a node against its direct dependency sections.
- `global-verifier` checking the fully merged artifact for conflicts no single node's verifier could see.

**When NOT to use:** checking whether a single section's claims are individually evidenced (`evidence-support-check`) or fresh (`freshness-verification`) — this skill only compares claims to each other.

## Inputs

- Two or more accepted section outputs (or the full merged artifact for a global check).
- Each section's claim-level structure (so specific fields, not whole documents, can be compared).

## Outputs

`conflicts[]`: `{ claimA: { sectionRef, path, value }, claimB: { sectionRef, path, value }, description }` — one entry per exact contradicting pair, empty if none found.

## Procedure

1. Identify claim fields likely to overlap across the sections under comparison (e.g. role titles, compensation ranges, interview-loop stages, technology claims, dates) — do not attempt exhaustive field-by-field diffing of unrelated content.
2. For each candidate overlap, compare the actual asserted values, not just topic overlap — two sections discussing the same topic without conflicting values is not a conflict.
3. Record a conflict only when values are substantively incompatible (not merely differently worded) — cite both sections' exact `sectionRef` and field `path`.
4. Distinguish a true contradiction from one section simply having more detail or scope than another; more detail is not conflict.
5. Return the full `conflicts[]` list with precise refs — do not resolve or merge the conflicting claims yourself; that is the aggregation/repair step's job.

## Failure Behavior

If a comparison is ambiguous (e.g. ranges that partially overlap), report it as a conflict with a note on the ambiguity rather than silently resolving it either way.

## Privacy Restrictions

Not applicable beyond standard rule: never introduce `context/private/` content into the comparison or the conflict report.

## Red Flags

- A conflict reported without both exact `sectionRef`/`path` values.
- Two sections' differing level of detail flagged as a contradiction.
- A real value conflict left unreported because the sections "seemed compatible" on a skim.
