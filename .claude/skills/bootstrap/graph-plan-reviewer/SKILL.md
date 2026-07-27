---
name: graph-plan-reviewer
description: Use when a compiled graph plus its capability, skill, and agent manifests needs a final adversarial check — before /contractgraph:init is reported complete, or when asked "review the compiled graph", "audit this workflow plan", "is this graph safe to run". Opus-oriented; this is the last gate before execution, not a design step — do not use it to design the graph (workflow-compiler) or to author contracts (contract-designer).
---

# Graph Plan Reviewer

## Overview

This skill is an adversarial critic, not a builder. It takes a fully compiled graph (`runtime/compiled/graph.yaml`/`graph.json`) plus `capability-manifest.json`, `skill-manifest.json`, and `agent-manifest.json` and tries to break the plan before it runs — looking for structural defects, privilege overreach, misrouting, duplication, privacy leaks, and missing verification. It never fixes the plan itself; it reports blockers and warnings and hands them back for repair.

## When to Use

- As the last step workflow-compiler invokes before declaring compilation complete.
- Directly, whenever asked to audit or second-guess an already-compiled graph.

**When NOT to use:** while the graph is still being assembled (that's workflow-compiler's job), or to design contracts or agents from scratch — this skill only critiques finished artifacts.

## Inputs

- Compiled `graph.yaml`/`graph.json` with resolved dependencies.
- `capability-manifest.json`, `skill-manifest.json`, `agent-manifest.json`.
- `policies.json` (for model-routing and privacy rule checks).

## Outputs

A structured review:
```json
{ "blockers": [{ "issue": "...", "location": "...", "why": "..." }], "warnings": [...], "verdict": "pass" | "fail" }
```

## Procedure

1. **Graph integrity:** walk the dependency edges for cycles, and cross-check every node in `graph.yaml` layers against `dependencies` — flag missing edges, contradictory edges, and orphan nodes with no path to or from the completion layer.
2. **Privilege check:** for each agent in `agent-manifest.json`, confirm every granted tool is required by an assigned skill (per `capability-manifest.json` `requiredTools`). Any extra tool is a blocker.
3. **Model routing:** compare each agent's assigned model against `policies.json` `models` — flag any node routed to Opus without a routing justification (global verification, supervision, adjudication) as a warning; flag any node missing required verification routing as a blocker.
4. **Duplication check:** scan `skill-manifest.json` for two entries covering materially overlapping capabilities — blocker if unresolved, since it signals skill-registry-manager's dedup step was skipped.
5. **Privacy check:** scan skill and agent definitions for company-, person-, or run-specific content — any leak is a blocker per `CLAUDE.md`'s privacy rules, not a warning.
6. **Verification coverage:** confirm every node in the graph has both a completion-rule-based structural check and a semantic verification step (no node may declare itself accepted without an independent verifier) — missing either is a blocker.
7. Emit the structured review with an explicit `pass`/`fail` verdict — `fail` if any blocker exists, regardless of warning count.

## Failure Behavior

Never soften a blocker into a warning to force a `pass`. If evidence for a check is missing (e.g. an unreadable manifest), report that as its own blocker rather than skipping the check silently.

## Privacy Restrictions

This skill only reads compiled manifests and definitions — never `context/private/` or raw canonical context content.

## Reuse Conditions

Re-run whenever workflow-compiler produces a new compiled graph; a review is never reused across a different compilation.

## Regeneration Conditions

Not applicable — this skill has no artifact of its own to regenerate; it always evaluates the current compiled state fresh.

## Red Flags

- Producing a `pass` verdict while a blocker is listed.
- Fixing an issue directly instead of reporting it back to workflow-compiler for repair.
- Treating a privacy leak or missing verification step as a mere warning.
