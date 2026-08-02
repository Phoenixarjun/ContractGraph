# Privacy

## Location and Isolation

- Canonical **private** context lives under `context/private/` and is git-ignored.
- `context/private/` is never read by any deterministic script (`validate_context.py`, `build_context_manifest.py` both explicitly exclude any path containing `private`), never read by any skill, and never read by any generated subagent.
- `context/canonical/` and `context/derived/` are git-ignored as well: real ground truth and anything derived from it stay local. Only `context/synthetic/` is tracked, and only that tree may appear in public examples.
- Personal run outputs live under ignored `runtime/` subdirectories (`runtime/runs/`, `runtime/cache/`, `runtime/outputs/`, `runtime/sections/`, `runtime/traces/`), not in tracked source. A compiled artifact that embeds a `context/canonical/` or `context/private/` path is ignored too.

## Prohibitions

- Never copy private facts into public examples. Public examples (e.g. a demonstration study-plan contract) must use synthetic context.
- Never embed resume text, personal identifiers, or project secrets into skills or agents. Skills and agents reference facts by path/id, never by value.
- `policies.json`'s `privacy` block encodes this as executable policy: `privateContextMustNotEnterSkills`, `privateContextMustNotEnterPublicExamples`, `derivedContextMustPreserveProvenance`, `canonicalContextIsImmutableDuringRun`.

## Enforcement Points

| Stage | Enforcement |
|---|---|
| Context indexing | `build_context_manifest.py` skips any `private/` path when hashing/indexing canonical context |
| Skill evaluation | Every new/regenerated skill is scored for `privacyStatus`; a non-`clean` status blocks reuse regardless of quality score |
| Agent generation | Agent definitions carry only references (paths, node IDs, capability IDs) — never canonical content, company facts, or run-specific data |
| Final compile gate | `graph-plan-reviewer` scans skill and agent definitions for company-, person-, or run-specific content as a **blocker**, not a warning |

## Derived Context Provenance

Every item under `context/derived/` must carry its source run ID, generating node, creation time, evidence references, confidence, freshness information, and contract version — so a derived fact can always be traced back to the verified run that produced it. Derived context is written only from globally-verified results, and it must never overwrite canonical context.

See [privacy-propagation.md](privacy-propagation.md) for the full mechanism: `scripts/build_derived_context.py` computes a `privacyClassification` (`public`/`internal`/`private`, never a bare boolean) per entry, inherited through the dependency chain and never downgraded on refresh.

## Canonical Immutability

Canonical context is treated as read-only for the duration of a run (`canonicalContextIsImmutableDuringRun`). Nothing in `/contractgraph:run` edits `context/canonical/`; only the user updates it, between runs.

## What Makes a Generated Skill or Agent Safe to Publish

A generated skill or subagent definition is safe to publish (after removing runtime references) when it contains:

- no company-specific facts,
- no person-specific facts,
- no run-specific data (a specific company name, a specific candidate's history, a specific run's evidence),
- only capability-level language, contract/schema references, and generic procedure — the same skill must work identically for a synthetic example as for a real one.

This is the same bar `contract-designer` applies to public examples: the shipped demonstration workflow (`contracts/study-plan`) uses synthetic user context only, never real canonical or private data, even though it shares the identical compile/run mechanism as any private workflow you build alongside it.
