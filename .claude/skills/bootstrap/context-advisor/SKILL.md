---
name: context-advisor
description: Use when a user is setting up ContractGraph context before /contractgraph:init, when creating or restructuring context/, or when unsure which canonical folders and files a given research workflow actually needs. Works for any workflow (company research, study plan, resume analysis, etc.) — it recommends structure, it does not fill in private data.
---

# Context Advisor

## Overview

Canonical context is **only the ground truth Claude cannot discover on its own** — the user's private facts, constraints, and source documents. Everything a research agent can look up at runtime is NOT context.

This skill takes a described workflow and derives the **minimum** set of user-supplied facts it needs, then proposes a domain-neutral `context/` structure containing **only the folders that workflow uses**. It recommends and scaffolds empty structure. It never invents facts and never writes real personal data into files.

## When to Use

- User is about to run `/contractgraph:init` and has no `context/` yet, or an empty one.
- User describes a workflow ("research companies", "build a study plan", "tailor my resume") and asks what context to provide.
- Restructuring context/ because a new workflow needs different ground truth.

**When NOT to use:** the user wants you to *fill in* actual profile/resume/goal content (that is the user's job — this skill only scaffolds), or the task is about contracts/graph compilation rather than context inputs.

## The Core Distinction (this is the whole skill)

Classify every candidate fact before deciding where — or whether — it belongs:

| Class | Test | Where it goes |
|-------|------|---------------|
| **Ground truth** | Only the user knows it; Claude cannot research it | `context/canonical/` |
| **Researchable** | Public / discoverable at runtime (company facts, framework docs, market data) | **Nowhere in context** — the workflow fetches it per run |
| **Derived** | Produced by a verified workflow run | `context/derived/` (created by runs, never scaffolded with data) |
| **Sensitive identifier** | Ground truth that is also PII/secret | `context/private/` (git-ignored) |

If a proposed folder would hold researchable facts, drop it. Canonical context that a workflow could just look up is waste and a staleness risk.

## Procedure

1. **Understand the workflow.** If the user hasn't already described it, ask at most 3 targeted questions — no more:
   - *What must the workflow produce?* (the deliverable / contract output)
   - *What must it draw on that only you can supply?* (the ground truth)
   - *What should stay stable across runs vs. be fetched fresh each run?*
2. **Enumerate candidate facts** the workflow consumes, and **classify each** with the table above. Keep only ground truth (+ note which pieces are sensitive → private).
3. **Map ground truth to the minimum folder set** from the vocabulary below. Include a folder only if step 2 produced a fact for it. Prefer a single `.md` file over a directory unless the user will supply multiple items.
4. **Present the proposal and STOP for approval.** Show: (a) the proposed tree, (b) a one-line rationale per file, (c) the clarifying questions that remain, (d) an explicit note of what you deliberately left out because it is researchable. Do not create anything yet.
5. **Scaffold only after approval.** Create the directories, empty placeholder files (frontmatter + `TODO` prompts, no real data), and a `context-manifest.json` skeleton. Report what was created and what the user must fill in.

## Domain-Neutral Folder Vocabulary

Pick only what the workflow needs — never scaffold the whole list.

```text
context/
├── canonical/
│   ├── profile.md         # who the subject is (identity, role, current situation)
│   ├── goals.md           # what they are trying to achieve, targets, deadlines
│   ├── knowledge.md       # current skills / knowledge / proficiency state
│   ├── preferences.md     # constraints, policies, likes/dislikes, time budget
│   ├── experience/        # history: jobs, projects, background (multi-item)
│   ├── documents/         # source docs: resume, transcripts, specs (originals)
│   └── domain/            # workflow-specific ground truth not covered above
├── derived/               # created by verified runs — scaffold empty only
├── private/               # git-ignored PII/secrets, if any ground truth is sensitive
└── context-manifest.json  # index of canonical sources + provenance
```

## Worked Examples (same method, different minimal output)

**Company research + resume analysis.** Ground truth = the user's background and target roles. Company facts are *researchable* → excluded.
```text
context/
├── canonical/
│   ├── profile.md         # name, current role, seniority
│   ├── preferences.md     # target roles, locations, constraints
│   ├── experience/        # prior roles/projects to map against JDs
│   └── documents/         # resume source file(s)
├── derived/               # research-history/, company dossiers land here per run
└── context-manifest.json
```

**Personalized study plan.** Ground truth = learner state and constraints. Curriculum/resources are *researchable* → excluded.
```text
context/
├── canonical/
│   ├── profile.md         # who is learning
│   ├── goals.md           # what to learn, target date, exam/outcome
│   ├── knowledge.md       # current level, prerequisites already met
│   └── preferences.md     # hours/week, learning style, format
├── derived/               # generated study-plans/ land here per run
└── context-manifest.json
```

Note how `documents/` and `experience/` appear in one and not the other — that is the skill working correctly.

## Templates (use when scaffolding)

Placeholder canonical file:
```markdown
---
source: canonical
required: true
status: empty            # user fills in → set to "provided"
---

# <Title>

<!-- TODO (user): supply ground truth here. Do NOT include anything researchable. -->
```

`context-manifest.json` skeleton:
```json
{
  "workflow": "<workflow-name>",
  "version": 1,
  "generated_by": "context-advisor",
  "canonical": [
    { "path": "canonical/profile.md", "purpose": "<why the workflow needs it>", "required": true, "status": "empty" }
  ],
  "derived": [],
  "notes": "Canonical = user-supplied ground truth only. Researchable facts are fetched per run and never stored here."
}
```

## Common Mistakes

- **Scaffolding the full vocabulary.** Generate only folders that a step-2 fact justified.
- **Storing researchable facts as canonical** (company data, docs versions, market info). These go stale and belong to runtime research, not context.
- **Writing real user data into placeholders.** Scaffold empty; the user fills in.
- **Skipping the approval gate.** Always present the tree and questions first; create only after the user says yes.
- **Directory where a file suffices.** Use `experience/` only for multiple items; otherwise a single `.md`.

## Red Flags — stop and reclassify

- "I'll add a `companies/` (or `frameworks/`, `market/`) folder under canonical" → that is researchable, not ground truth.
- "Let me pre-fill profile.md with what I inferred" → never infer personal facts into canonical.
- "I'll just create all the standard folders to be safe" → minimum set only.
- Creating files before the user approved the proposal.
