# Privacy Propagation

## Privacy Is Provenance-Aware Metadata, Never a Bare Boolean

A single top-level `"private": true|false` on a derived-context file is worth
very little: it is one flag, typically written by whatever produced the file,
computed by nothing and validated by nothing. It cannot say *which* entry is
sensitive, *why*, or what it inherited that status from.

Every `derived-context.json` entry instead carries
(`scripts/schemas/derived-context.schema.json`):

| Field | Meaning |
|---|---|
| `privacyClassification` | `public` \| `internal` \| `private` |
| `sourceContextRefs` | canonical-context-relative paths the node declared (`x-contractgraph.contextRefs`) |
| `sourceRunId` / `sourceNodeId` | which run and node produced this entry |
| `evidenceRefs` | the node's cited evidence refs |
| `confidence` | passthrough from the section's `verification.confidence` |
| `createdAt` / `timestampSource` | see [time-and-provenance.md](time-and-provenance.md) |
| `expiresAt` / `freshnessBasis` | populated only when a node contract declares a freshness category; otherwise `null` — never guessed |

The document also carries a top-level `artifactPrivacyClassification`: the
most restrictive classification among its entries (the artifact as a whole is
private if *any* entry is private).

## How Classification Is Computed (`scripts/build_derived_context.py`)

A node's classification is the most restrictive of:

- **its own contextRefs**: any ref under `canonical/` or `private/`, or whose
  path contains a sensitive-content keyword (resume, goal, employ,
  compensation, skill, project, preference, experience, knowledge, certif) →
  `private`. Refs that are *all* under `synthetic/` → `public`. Anything else
  → `internal`.
- **every dependency's final classification**, inherited through the
  `dependsOn` chain — a synthesis node with no canonical refs of its own (e.g.
  `evaluation-plan`) still inherits `private` from the upstream nodes it
  synthesizes.
- **fail-closed default**: a node with no declared refs and no dependencies
  classifies `private`. Nothing on record proves it's safe to call public.

The practical consequence: in a workflow whose foundation node reads real
canonical context, *every* downstream entry ends up `private`, because every
node touches `canonical/` directly or transitively. That is the correct
outcome — a synthesis of private inputs is private.

## Never Downgrade

`build_derived_context.py --existing <prior-derived-context.json>` merges the
newly computed classification with whatever the prior run recorded, taking
the more restrictive of the two. A classification can only escalate
(public→internal→private), never regress. This is enforced in code (`_RANK`
ordering + `max()`), not by convention, and covered by
`t_derived_context_privacy`'s "never downgrades on re-run" case in
`evals/run_evals.py`.

## Synthetic Context Stays Public

The shipped demonstration workflow's synthetic context
(`context/synthetic/study-plan/`) is the one case that should classify
`public` end-to-end — `t_synthetic_context_stays_public` asserts a bundle
built entirely from `synthetic/` refs (including a downstream node with no
refs of its own) resolves to `public`, confirming the classifier doesn't
default to `private` out of over-caution when there's genuine evidence
otherwise.

## What this does not do

- It does not redact or rewrite section content. A `private` classification
  is a label on the derived-context artifact, not a transformation of the
  underlying sections.
- Producing a separate **public** artifact from a private one requires a
  deterministic redaction/export step that does not exist yet — until it
  does, a final artifact with any private entry is private, full stop.
- Reusable skills and agents must never contain copied private context
  (existing `t_privacy` in `evals/run_evals.py` scans `.claude/skills` and
  `.claude/agents` for PII) — that is a separate enforcement point, applied at
  skill-acceptance time rather than at derived-context build time.
