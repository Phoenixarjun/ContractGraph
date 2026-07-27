---
name: evidence-support-check
description: Use when every public claim in a node's output must be verified as resolving to an actual supporting source entry, and that source must be confirmed to genuinely support the specific claim (not merely exist). Triggered by section-verifier and global-verifier during /contractgraph:run. Not for checking whether the covered content is complete (contract-completeness-check) or whether sources are credible/fresh (source-quality-assessment, freshness-verification). Must be run by a subagent instance different from the one that produced the node.
---

# Evidence Support Check

## Overview

A claim can have a citation attached without the citation actually saying what the claim asserts. This skill's one job is to independently re-check that every public (non-canonical-context) claim in a node's output resolves to a `sources[]` entry, and that the cited source, on inspection, genuinely supports the specific assertion made — not just the general topic. It reports `unsupportedClaims`, not fixes.

## When to Use

- `section-verifier` re-checking a single node's claims against its own `sources[]`.
- `global-verifier` spot-checking evidence integrity across the merged artifact and the global source registry.

**When NOT to use:** checking whether required content is present (`contract-completeness-check`), or tiering/freshness of sources already confirmed to support their claims (`source-quality-assessment`, `freshness-verification`).

## Inputs

- The node output's claims and their attached `sources[]`/`sourceRef` entries.
- The full source records (`url`, `title`, `supportedClaims`) — fetch/read the source content when the claim-to-source match isn't obvious from metadata alone.

## Outputs

`{ status: "passed" | "failed", unsupportedClaims: [ { claimPath, sourceRef, reason } ], issues: [...], repairInstructions: [...], confidence }`.

## Procedure

1. For each public claim, locate its attached `sourceRef`; flag `unsupportedClaims` immediately for any claim with no `sourceRef` at all.
2. For each attached source, confirm it is reachable and re-derive whether its content actually asserts the specific claim (not an adjacent or broader statement) — do not accept the producing node's `supportedClaims` label at face value.
3. Flag a mismatch when a source is topically related but does not state the specific fact claimed (e.g. source discusses "the team" generally, claim asserts a specific headcount).
4. Cross-check that `contextEvidence[].contextRef` entries (canonical-context-backed claims) resolve to a real path under `context/canonical/`, not a public source misused as canonical, or vice versa.
5. Return `"failed"` with every unsupported claim listed if any exist; `"passed"` only when every public claim's source was independently re-verified to support it.

## Failure Behavior

If a source is unreachable at check time (previously reachable, now broken), flag it as `unsupportedClaims` with reason `now_unreachable` rather than assuming it still holds.

## Privacy Restrictions

Never read `context/private/`; canonical-context claims are checked for path resolution only, not by exposing private content in the report.

## Red Flags

- Accepting a `sourceRef` as sufficient without confirming the source content matches the claim.
- A `contextRef` that doesn't resolve to a real canonical path.
- The producing subagent performing this check on its own output.
