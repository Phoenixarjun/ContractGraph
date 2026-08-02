<!--
Target `dev`, not `main`. Keep the PR to one concern.
See CONTRIBUTING.md for the full guidelines.
-->

## What changed

<!-- One or two sentences. What is different after this PR? -->

## Why

<!-- The problem being solved. Link the issue: Closes #123 -->

## How it was verified

<!--
Paste the actual output, not a claim. At minimum the final line of the suite.
-->

```text
$ python evals/run_evals.py
...
```

## Out of scope

<!--
Anything you deliberately did NOT do, and why. "Nothing" is a valid answer.
-->

---

## Checklist

- [ ] `python evals/run_evals.py` passes with no FAILs, and the output is pasted above.
- [ ] An eval case covers the new behaviour. For a validator change, a planted-defect case fails before the fix and passes after.
- [ ] Docs updated for every user-visible change.
- [ ] No path under `context/canonical/`, `context/private/`, `context/derived/`, or `runtime/runs/` appears in `git diff --stat`.
- [ ] No personal identifiers, resume text, or secrets in any skill, agent, contract, doc, or fixture.
- [ ] Commits follow Conventional Commits and are scoped to one concern.
- [ ] This PR targets `dev`.

## Architectural boundaries

<!-- Untick anything this PR crosses and explain why. -->

- [ ] Adds no server, database, queue, or background daemon.
- [ ] Adds no external model API and no API key requirement.
- [ ] Adds no domain-specific term to `scripts/`, `.claude/commands/`, or a bootstrap skill — domain knowledge stays in `contracts/`.
- [ ] Python scripts stay deterministic: no model calls, no agent reasoning, no network beyond what they document.
- [ ] JSON stays the canonical format; any TOON use remains benchmark-gated.
