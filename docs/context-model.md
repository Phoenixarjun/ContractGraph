# Context Model

Context is evolving, but every fact must retain its origin. ContractGraph recognizes three kinds of context plus one privacy overlay.

## The Three (+1) Kinds

| Kind | Definition | Location | Mutability |
|---|---|---|---|
| **Canonical** | Ground truth only the user can supply — Claude cannot discover it by research | `context/canonical/` | Immutable during a run; user-edited between runs |
| **Derived** | Produced by a verified workflow run | `context/derived/` | Append-only; never overwrites canonical |
| **Private** | Ground truth that is also PII/secret | `context/private/` (git-ignored) | Never read into skills, agents, or manifests |
| *(Researchable)* | Public/discoverable at runtime (company facts, framework docs, market data) | *not stored in context at all* | Fetched fresh per run |

The fourth row is a deliberate non-category: if a fact can be looked up at runtime, it does not belong in `context/` — storing it there is waste and a staleness risk. This is the core test the `context-advisor` skill applies when scaffolding a workflow's context tree.

## Rules

- Never silently modify canonical context. Only the user edits `context/canonical/`.
- Never infer missing personal facts and store them as truth.
- Preserve the source path for every extracted fact.
- Summarize large documents when useful; load originals when exact evidence is required.
- Use OCR only when normal extraction produces no usable text.
- Canonical context is immutable for the duration of a run (`policies.json` → `canonicalContextIsImmutableDuringRun`).
- `context/private/` is never read by `build_context_manifest.py`, `validate_context.py`, or any skill/agent — it is excluded by path segment, unconditionally.

## The Context Manifest

`/contractgraph:init` runs `scripts/build_context_manifest.py` to produce `runtime/compiled/context-manifest.json`. It walks `context/canonical/` (skipping any path containing `private`, and skipping `README.md` scaffolding files) and records, per file:

```json
{
  "path": "profile.md",
  "sourcePath": "context/canonical/profile.md",
  "sha256": "<hash>",
  "bytes": 512,
  "type": "text",
  "status": "provided",
  "needsSummary": false
}
```

- **Hash, not content** — the manifest references originals by path and SHA-256; it never copies file bodies into the compiled artifact.
- **`needsSummary`** flags files over 16 KB so a downstream step can condense them by reference rather than duplicating full text into every node's context.
- **`status`** is read from each file's own frontmatter (`empty` vs `provided`), letting `validate_context.py` warn on unfilled canonical files without judging content quality.
- A top-level **`contextManifestHash`** (hash of all per-file hashes) makes the whole canonical context set one cache-key input for `/contractgraph:run`.

Originals are never replaced or edited by this process — the manifest is a read-only index.

## Scaffolding: `context-advisor`

Before a workflow has any `context/` tree, the `context-advisor` bootstrap skill (invoked via `/contractgraph:context`) proposes the **minimum** structure a described workflow needs:

1. Classify every candidate fact: ground truth → ✅, researchable → excluded, sensitive → private.
2. Map surviving ground truth to the smallest folder set from a domain-neutral vocabulary (`profile.md`, `goals.md`, `knowledge.md`, `preferences.md`, `experience/`, `documents/`, `domain/`).
3. **Stop for approval** — present the proposed tree, a one-line rationale per file, and what was deliberately excluded as researchable. Create nothing until approved.
4. Only after approval, scaffold empty placeholder files (frontmatter + `TODO` prompts, no real data) and a `context-manifest.json` skeleton.

The skill never fills in real personal data — that remains the user's job. Two workflows can need very different minimum sets (e.g. a career roadmap needs `experience/` and `documents/`; a study plan needs `goals.md` and `knowledge.md` instead) — the same procedure produces both without any domain logic baked into the skill itself.

## Derived Context

Every item under `context/derived/` must carry, at minimum:

- source run ID,
- generating node,
- creation time,
- evidence references,
- confidence,
- freshness information,
- contract version.

Derived context is written only from **verified** (globally-accepted) run results, and it must never overwrite canonical context — it is additive provenance, not a replacement for ground truth.
