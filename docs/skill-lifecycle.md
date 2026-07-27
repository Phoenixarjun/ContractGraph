# Skill Lifecycle

Skills are reusable capabilities, not workflow-specific prompts. One large skill containing an entire workflow, or many overlapping skills with slightly different names, are both defects to be caught during evaluation.

## Three Tiers

```text
.claude/skills/
├── bootstrap/    # framework-authoring skills: context-advisor, contract-designer, workflow-compiler,
│                 # capability-detector, skill-registry-manager, agent-definition-generator, graph-plan-reviewer
├── reusable/     # verified, domain-neutral capability skills available to any bundle
└── generated/    # capability skills created (or regenerated) for a specific bundle's needs
```

- **Bootstrap** skills build the framework itself — they are invoked by the `/contractgraph:*` commands and never appear as a node's assigned skill.
- **Reusable** skills satisfy a capability once and get reused across bundles and runs (e.g. `evidence-backed-web-research`, `source-quality-assessment`, `freshness-verification`).
- **Generated** skills are created for a capability with no existing match; once evaluated and accepted, they are candidates for promotion into `reusable/` on reuse elsewhere.

## The Registry Index

`skill-registry-manager` owns the reuse-vs-regenerate decision and maintains one registry entry per capability, written out as `skill-manifest.json`:

| Field | Purpose |
|---|---|
| `capabilityId` | The capability this entry satisfies |
| `skillPath` | Path to the skill file |
| `version` | Skill content version |
| `contentHash` | Hash of the skill's actual content (`scripts/hash_content.py`) |
| `compatibleContractTypes` | Bundle types this skill is verified against |
| `requiredTools` | Minimum tools the skill's procedure needs |
| `qualityScore` | Result of the last evaluation |
| `tokenSizeEstimate` | Preload cost |
| `privacyStatus` | `clean` or flagged — a non-`clean` status blocks reuse regardless of `qualityScore` |
| `creationSource` | `reused` \| `created` \| `regenerated` |
| `lastEvaluationDate` | When the entry was last evaluated |

## Reuse vs. Regeneration

**Reuse** is the default action whenever a registry entry is compatible, `clean`, above the quality threshold, and not redundant with another entry.

**Regenerate** when any one of these triggers fires:

- The capability definition changed since `lastEvaluationDate`.
- The relevant contract changed in a way that affects the skill's inputs/outputs.
- `qualityScore` is below the accepted threshold.
- A private-context leak was detected in the skill's content.
- Redundancy with another registry entry.
- Required tools or outputs changed.

Regeneration is never speculative — it fires only on a specific triggering condition. `skill-registry-manager` decides reuse/regenerate/create; it never edits a skill's actual instructions itself, and it never writes a fabricated registry entry for a skill that doesn't exist — a failed creation stays `missing` and is surfaced in the compilation report.

## `skill-creator` and Evaluation

Skill authoring itself is delegated to `skill-creator`, called only:

- for a capability with no compatible existing skill (`missing`), or
- when a regeneration trigger fires for an existing entry.

Every skill — new or regenerated — is evaluated on these dimensions before acceptance:

1. **Correct triggering** — does its description fire when it should?
2. **False triggering** — does it fire when it shouldn't?
3. **Output quality** — does its procedure reliably produce a usable result?
4. **Contract usefulness** — does it actually serve a node's completion rules?
5. **Token overhead** — is it concise enough to preload without wasting context?
6. **Duplication** — does it overlap another registry entry's capability?
7. **Privacy leakage** — does its content or examples contain company-, person-, or run-specific facts?

A skill that fails any of these does not get accepted into the registry as `clean`/high-quality; it stays flagged for repair or regeneration.

## A Generated Skill Must

- Solve one clear reusable capability.
- Have a precise trigger description.
- Include a bounded procedure.
- Define expected inputs and outputs.
- Define evidence and quality requirements.
- Define failure behavior.
- Avoid private user facts, company-specific detail, and run-specific detail.
- Avoid duplicating another skill.
- Remain concise enough to preload without wasting context.

## Where Skills Fit in Compilation

`workflow-compiler` calls `capability-detector` to name the capabilities a bundle's nodes need (one per distinct requirement, not per node — a `map` node contributes one capability, not N), then hands that list to `skill-registry-manager` for the reuse/create/regenerate decision, then `agent-definition-generator` assigns the resulting skill(s) to each node's subagent. See [graph-compilation.md](graph-compilation.md) for the full sequence.
