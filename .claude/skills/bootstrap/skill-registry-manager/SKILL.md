---
name: skill-registry-manager
description: Use when deciding whether to reuse, regenerate, or newly create a skill for a detected capability — maintaining the registry under .claude/skills/{bootstrap,reusable,generated}. Trigger during /contractgraph:init after capability-detector runs, or directly when asked "do we already have a skill for X", "should this skill be regenerated", or "check the skill registry". Not for authoring skill content itself (delegates to skill-creator) and not for detecting what capabilities are needed in the first place (capability-detector).
---

# Skill Registry Manager

## Overview

This skill owns the reuse-vs-regenerate decision for every capability in `capability-manifest.json`. It maintains a registry index — one entry per skill — and is the only place that decides whether an existing skill under `.claude/skills/reusable/` or `.claude/skills/generated/` satisfies a capability, needs regeneration, or is genuinely missing.

## When to Use

- Called by **workflow-compiler** once per compilation, after **capability-detector** produces `capability-manifest.json`.
- Directly, to audit the registry, check for duplication, or decide a single skill's fate.

**When NOT to use:** writing or rewriting a skill's actual content — always delegate that to `skill-creator`. This skill decides; `skill-creator` executes.

## Inputs

- `capability-manifest.json`.
- Existing skills under `.claude/skills/bootstrap/`, `.claude/skills/reusable/`, `.claude/skills/generated/`.
- Prior registry index (if one exists).

## Outputs

A registry index and `skill-manifest.json`, one entry per capability:
```json
{ "capabilityId": "...", "skillPath": "...", "version": "...", "contentHash": "...", "compatibleContractTypes": ["..."], "requiredTools": ["..."], "qualityScore": 0.0, "tokenSizeEstimate": 0, "privacyStatus": "clean", "creationSource": "reused|created|regenerated", "lastEvaluationDate": "..." }
```

## Procedure

1. For each capability in `capability-manifest.json`, search the registry for a skill whose `capabilityId` matches and whose `compatibleContractTypes` covers the current bundle type.
2. If found and none of the regeneration triggers below apply → mark `reused`, no content change.
3. If found but a trigger applies → mark `regenerate`, hand the capability plus the reason to `skill-creator`.
4. If no compatible skill exists → mark `missing`, hand the full capability spec to `skill-creator` for first-time creation.
5. Compute `contentHash` (`scripts/hash_content.py`) for every reused/created/regenerated skill and update the registry entry.
6. Scan for duplication: two registry entries covering near-identical capability descriptions is a defect — flag for consolidation, do not silently keep both.
7. Write `skill-manifest.json` reflecting the final state of every capability (reused, created, or regenerated), each pointing at one skill path.

## Regeneration Triggers (any one is sufficient)

- The capability definition changed since `lastEvaluationDate`.
- The relevant contract changed in a way that affects the skill's inputs/outputs.
- `qualityScore` is below the accepted threshold.
- A private-context leak was detected in the skill's content.
- Redundancy with another registry entry.
- Required tools or outputs changed.

## Failure Behavior

If `skill-creator` fails to produce a usable skill, leave the capability marked `missing` in `skill-manifest.json` and surface it in the compilation report — do not fabricate a registry entry for a skill that doesn't exist.

## Privacy Restrictions

Registry entries and skill content must contain no company-specific, person-specific, or run-specific detail. A `privacyStatus` other than `clean` blocks reuse regardless of `qualityScore`.

## Reuse Conditions

Default action for any capability with a compatible, clean, above-threshold, non-redundant existing skill.

## Regeneration Conditions

See triggers above — regenerate only on a specific triggering condition, never speculatively.

## Red Flags

- Editing a skill's actual instructions directly instead of routing through `skill-creator`.
- Marking a capability `reused` without checking `compatibleContractTypes` against the current bundle.
- Two registry entries with overlapping responsibility left unconsolidated.
