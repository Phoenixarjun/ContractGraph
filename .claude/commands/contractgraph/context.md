---
description: Advise on and scaffold a minimal, domain-neutral context/ structure for your workflow (runs before /contractgraph:init).
argument-hint: [optional: describe your workflow, e.g. "research target companies and tailor my resume"]
allowed-tools: Read, Write, Glob, AskUserQuestion
---

Invoke the `context-advisor` bootstrap skill (`.claude/skills/bootstrap/context-advisor/SKILL.md`) and follow its procedure exactly.

Workflow description from the user (may be empty): $ARGUMENTS

Steps:
1. If the workflow description above is empty or too vague to classify ground truth, ask the advisor's clarifying questions (at most 3) before proposing anything.
2. Apply the skill's ground-truth / researchable / derived classification to determine the **minimum** canonical folders and files this workflow needs.
3. **Present, then stop for approval.** Show:
   - the proposed `context/` tree (only the folders this workflow uses),
   - a one-line rationale per file,
   - what you deliberately excluded because it is researchable at runtime,
   - any remaining clarifying questions.
   Do NOT create any files yet.
4. Only after the user explicitly approves, scaffold: create the directories, empty placeholder files (frontmatter + TODO prompts, no real data), and a `context-manifest.json` skeleton using the skill's templates.
5. Report exactly what was created and what the user must fill in. Never write real personal data into any file.
