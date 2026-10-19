# Skill Generation

This is the mechanics doc: how a missing capability becomes a shipped, bound skill file. For the tier model, the registry index, and the reuse-vs-regenerate decision, see [skill-lifecycle.md](skill-lifecycle.md) — this doc does not repeat that logic.

## Trigger

`skill-registry-manager` calls `skill-creator` for exactly one capability at a time, and only when:

- the capability has no compatible entry in `.claude/skills/reusable/` or `.claude/skills/generated/` (`missing`), or
- an existing entry's regeneration trigger fired (contract change, quality drop, privacy flag, redundancy, tool/output change).

`skill-creator` is never handed the whole capability list at once and never authors a skill "in case it's needed later" — every call maps to one named, currently-required capability.

## Required Shape of a Generated Skill

A skill authored (or regenerated) by `skill-creator` must define, in this order:

1. **Trigger description** — precise enough to fire on the intended capability need and not on adjacent ones (this is what gets independently checked in evaluation dimensions 1–2 of [skill-lifecycle.md](skill-lifecycle.md)).
2. **Bounded procedure** — a fixed sequence of steps for the capability, not an open-ended instruction to "do research" or "do validation."
3. **Expected inputs and outputs** — named, typed where practical, so a node subagent knows exactly what to hand the skill and what it gets back.
4. **Evidence and quality requirements** — what makes this capability's output acceptable (e.g. `evidence-backed-web-research` requires resolvable sources; `freshness-verification` requires an explicit age check against a policy threshold).
5. **Failure behavior** — what the skill's procedure does when it cannot satisfy its own bar (e.g. return an explicit gap rather than fabricating a source).

A skill missing any of these is not accepted into the registry as `clean`/high-quality, regardless of how well it performs on a lucky example.

## Binding a Skill to a Node

Binding happens once, during `agent-definition-generator`'s pass (`graph-compilation.md`, step 7):

```text
capability-manifest.json  (one entry per detected capability)
        │
skill-manifest.json        (registry: which skill satisfies which capability, at what quality)
        │
agent-manifest.json         requiredSkills: [...]   ← per node, from the node's detected capabilities
        │
.claude/agents/generated/<nodeId>.md   Required Skills: section
```

A node's `requiredSkills` in the generated agent file is never hand-picked — it is exactly the set of skills bound to that node's detected capabilities, nothing added for convenience and nothing capability-derived omitted.

## Promotion Path

A skill created for one bundle's need starts in `.claude/skills/generated/`. On reuse by a second, unrelated bundle without a regeneration trigger firing, it is a candidate for promotion into `.claude/skills/reusable/` — reuse across bundles, not just repeated invocation within one, is the promotion signal. Promotion changes only the skill's tier and `compatibleContractTypes`; it never changes the skill's content, since content changes are regeneration, not promotion.

## Privacy at Generation Time

Every generated skill's content is scanned for company-, person-, or run-specific facts before acceptance (dimension 7 in [skill-lifecycle.md](skill-lifecycle.md)) — a skill authored while working a private workflow bundle must read identically to one authored first against the study-plan fixture. See [privacy.md](privacy.md) for the full enforcement model.
