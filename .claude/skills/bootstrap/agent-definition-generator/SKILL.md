---
name: agent-definition-generator
description: Use when emitting a subagent definition for one compiled graph node — trigger during /contractgraph:init after skill-manifest.json exists, or directly when asked "generate the agent for node X" or "write the subagent definition for this contract". Domain-neutral: never invoke for designing the contract itself (contract-designer) or for deciding which skills a node needs (capability-detector, skill-registry-manager) — this skill only assembles the agent definition from decisions those already made.
---

# Agent Definition Generator

## Overview

Given exactly one node contract, the routing rules in `policies.json`, and the node's resolved dependencies from the graph, this skill emits one subagent definition file. It never designs contracts, never decides which capabilities a node needs, and never writes skill content — it only assembles an agent from inputs that other steps already produced.

## When to Use

- Called by **workflow-compiler**, once per node, after `skill-manifest.json` exists.
- Directly, to regenerate or inspect a single node's agent definition.

**When NOT to use:** deciding what capabilities a node needs (capability-detector), deciding whether a skill should be reused or regenerated (skill-registry-manager), or defining the node's contract itself (contract-designer).

## Inputs

- One node contract (including its `x-contractgraph` block).
- `policies.json` (`models`, `execution.maxRetriesPerNode`).
- The node's resolved `dependsOn` from the compiled graph.
- `skill-manifest.json` entries for the capabilities this node requires.

## Outputs

One agent definition under `.claude/agents/generated/<nodeId>.md` (or `agent-manifest.json` entry) containing every field below — no field may be omitted.

## Procedure

1. State the node's single responsibility directly from `x-contractgraph.purpose` — do not paraphrase it into something broader.
2. Record the node contract path as the agent's input/output contract reference.
3. List explicit input references: each `dependsOn` node's accepted output path, plus any `contextRefs` the node's schema requires.
4. Set the output path to `runtime/sections/<nodeId>.json` (or the per-item path for a `map` node, e.g. `runtime/sections/<nodeId>/<item>.json`).
5. List only the skills whose `capabilityId` appears in this node's entry from **capability-detector**'s output — no extras.
6. List only the tools those skills actually require — minimum necessary, never a default full toolset.
7. Select the model from `policies.json`'s `models.research.primary` (or `.triage` for lightweight nodes) per the Model Routing rules in `CLAUDE.md` — do not default to Opus.
8. Set retry policy from `policies.json`'s `execution.maxRetriesPerNode`, and note `retryFailedNodesOnly`.
9. Copy the node's evidence requirements from its `verification`/`completionRules` fields verbatim — do not soften or drop them.
10. State completion conditions matching `completionRules`, and add two explicit prohibitions: the agent cannot approve its own output (`workerCannotSelfApprove`), and the agent cannot declare the overall workflow complete.

## Failure Behavior

If a required input (contract, dependency output path, or skill-manifest entry) is missing, do not fabricate a placeholder — report the missing input and stop for that node only; other nodes' generation is unaffected.

## Privacy Restrictions

Agent definitions must contain no canonical context content, no company-specific facts, no run-specific data — only references (paths, node ids, capability ids).

## Reuse Conditions

Regenerate an agent definition only when its node contract, assigned skills, or routing inputs changed; otherwise leave the existing definition in place.

## Regeneration Conditions

Node contract changes, `policies.json` model routing changes, or the node's skill assignment changes in `skill-manifest.json`.

## Red Flags

- An agent definition missing any of: node contract path, explicit inputs, explicit output path, model, retry policy, evidence requirements, or the two prohibitions.
- Assigning Opus to routine per-node work instead of following `policies.json` routing.
- Granting a tool no assigned skill actually needs.
