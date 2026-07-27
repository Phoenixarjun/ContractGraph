---
description: Design a contract bundle for a workflow (explicit / assisted / hybrid), then validate it. Runs before /contractgraph:init.
argument-hint: [intent and/or paths to example or legacy JSON outputs, e.g. "company research; examples/legacy-salesforce.json"]
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion
---

Invoke the `contract-designer` bootstrap skill (`.claude/skills/bootstrap/contract-designer/SKILL.md`) and follow its procedure exactly.

User input (intent and/or example/legacy file paths, may be empty): $ARGUMENTS

Steps:
1. Determine the mode (explicit / assisted / hybrid). If example or legacy JSON files were provided, read them and treat them as a source of candidate subcontracts, field structures, and validation requirements — never copy a legacy blob as one giant contract.
2. Name the final output and decompose it into a main contract plus machine-validatable node subcontracts. Model repeated sections (e.g. per-role analyses) as one node contract applied over a set in a subfolder. Infer dependencies from data needs, not tree nesting. Do NOT hard-code any domain concept into framework logic.
3. **Present the proposed contract tree and stop for approval.** Show:
   - the bundle layout (`contract-bundle.json`, `main.contract.json`, `nodes/`, any set folder, `policies.yaml`),
   - a one-line purpose per node,
   - the dependency edges between nodes,
   - what you mined from any provided example,
   - open questions.
   Create no files yet.
4. Only after the user approves, write the bundle under `contracts/<workflow>/` using the skill's layout. Each node contract must include `outputSchema` and a `verification` block; the main contract must include `finalOutputSchema`, `requiredSubcontracts`, `aggregation`, and `globalVerification`.
5. Validate the written bundle by running:
   `python scripts/validate_contract_bundle.py contracts/<workflow>`
   Report exactly what passed and what failed. If validation fails, fix the contract files and re-run until it passes. Never write private personal data into any contract.
