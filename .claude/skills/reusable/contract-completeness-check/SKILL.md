---
name: contract-completeness-check
description: Use when a node's output must be checked for substantive completeness against its contract's required sections and claims — not merely schema validity, but whether the required content is actually present and non-trivial. Triggered by section-verifier and global-verifier during /contractgraph:run. Not for checking evidence quality (evidence-support-check) or ranking rationale (ranking-justification-check). Must be run by a subagent instance different from the one that produced the node.
---

# Contract Completeness Check

## Overview

Schema validation confirms shape; it does not confirm substance. This skill's one job is to check whether a node's output actually covers everything its contract's `completionRules` and required sections demand — catching thin, boilerplate, or partially-addressed content that would still pass a JSON Schema check. It produces repair **targets**, not fixes: the calling verifier reports what's missing, and the producing node (a different subagent instance) does the repair.

## When to Use

- `section-verifier` checking a single node's output against its own contract.
- `global-verifier` checking that every required subcontract in `contract.bundle.json.nodes[]` is substantively present in the merged artifact.

**When NOT to use:** judging whether present claims are evidenced (`evidence-support-check`) or whether rankings are justified (`ranking-justification-check`) — this skill only checks presence and depth of required content, not its quality.

## Inputs

- The node output (or merged artifact).
- The node's contract (`x-contractgraph.completionRules`, required fields, `minItems`/multiplicity constraints).
- For a global check: `contract.bundle.json.nodes[]` and the main `contract.schema.json`.

## Outputs

`{ status: "passed" | "failed", issues: [ { path, requirement, description } ], repairInstructions: [...], confidence }`.

## Procedure

1. Enumerate every required section/field/`completionRule` the contract demands, including `minItems`/multiplicity constraints (e.g. "one roleTrack per configured role").
2. For each requirement, confirm not just presence but substance — a field meeting `minItems` with near-duplicate or vacuous entries is incomplete, not merely low-quality.
3. Check multiplicity requirements resolve against the actual configured set (e.g. a `map` node's per-role output count matches the configured role list, not a fixed guess).
4. Record each gap as a concrete `issue` with the exact contract requirement it fails and a `repairInstruction` naming exactly what's missing — never a vague "add more detail."
5. Return `"failed"` if any required section is absent, thin, or under the multiplicity floor; `"passed"` only when every required item is substantively present.

## Failure Behavior

If a requirement's completeness threshold is itself ambiguous in the contract, flag the ambiguity in `issues` rather than silently picking a lenient or strict reading.

## Privacy Restrictions

Never read `context/private/`; this check operates on the node's own output and its contract only.

## Red Flags

- Passing a section because it is schema-valid without checking substance.
- A `repairInstruction` too vague for the producing node to act on.
- The same subagent instance that produced the node also running this check.
