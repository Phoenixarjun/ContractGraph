---
name: capability-detector
description: Use when compiling a contract bundle and the set of reusable capabilities each node needs must be derived from its contract — triggered by workflow-compiler during /contractgraph:init, or directly when asked "what capabilities does this bundle need" or "detect capabilities for these nodes". Not for creating or scoring skills (skill-registry-manager) and not for generating subagents (agent-definition-generator).
---

# Capability Detector

## Overview

A capability is a domain-neutral reusable ability (e.g. `evidence-backed-web-research`, `source-quality-assessment`, `freshness-verification`, `profile-alignment`, `schema-repair`, `cross-section-contradiction-detection`) — never a company, role, or run-specific fact. This skill's one job is to read each node contract's `x-contractgraph.purpose` and `completionRules`, plus role emphasis and `policies.json`'s `evidence` block, and derive the minimal capability set the compiled graph actually needs.

## When to Use

- Called by **workflow-compiler** during compilation, once per bundle.
- Directly, when asked to enumerate or re-derive capabilities for a bundle or a single node.

**When NOT to use:** deciding whether a matching skill already exists or must be created (that is skill-registry-manager's job) — this skill only names what is needed, not how it gets satisfied.

## Inputs

- Node contracts' `x-contractgraph` blocks (`purpose`, `completionRules`, `multiplicity`).
- `policies.json` `evidence` and `freshnessDays` blocks.
- `graph.yaml` role/map structure, where relevant (e.g. a `map` layer over roles implies a per-item capability, not N distinct ones).

## Outputs

`capability-manifest.json` entries:
```json
{ "capabilityId": "evidence-backed-web-research", "description": "...", "requiredByNodes": ["company-intelligence"], "requiredTools": ["WebSearch", "WebFetch"], "inputs": ["..."], "outputs": ["..."] }
```

## Procedure

1. For each node, read `purpose` and `completionRules` and translate each concrete need into a generic capability name (e.g. "evidence must resolve to sources" → `evidence-backed-web-research` + `source-quality-assessment`; "freshness required" → `freshness-verification`).
2. Fold `policies.json`'s `evidence.requireClaimLevelEvidence`, `preferPrimarySources`, and `freshnessDays` into the relevant capabilities' descriptions and thresholds rather than inventing new bundle-specific capabilities.
3. Deduplicate: if two nodes need the same generic ability, they share one `capabilityId` with both nodes listed in `requiredByNodes`.
4. For a `map` node (per-role, per-topic, etc.), emit one capability entry that lists the node once — the per-item repetition is execution-time, not a capability-count multiplier.
5. Assign `requiredTools` conservatively — only tools the capability's procedure actually needs.
6. Write `capability-manifest.json` and report any node whose `completionRules` did not map cleanly to an existing capability vocabulary term (flag for user review rather than inventing an overly narrow one).

## Failure Behavior

If a node's purpose is too vague to name a capability confidently, list it as `unresolved` with the raw text — do not guess a name that will mismatch skill-registry-manager's matching.

## Privacy Restrictions

Never emit a capability that is company-, person-, or run-specific (e.g. no `research-acme-corp`). If a node's purpose reads as one-off, generalize it or flag it as unresolved.

## Reuse Conditions

Re-detect only for nodes whose contract or `x-contractgraph` block changed since the last `capability-manifest.json`.

## Regeneration Conditions

Full re-run when the bundle's node set, `policies.json` evidence/freshness settings, or the capability vocabulary itself changes.

## Red Flags

- A capability name that only makes sense for one company or one run.
- Emitting N separate capabilities for one `map` node's N items.
- Deciding skill reuse/creation here instead of leaving that to skill-registry-manager.
