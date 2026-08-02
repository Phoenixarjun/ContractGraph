# Security Policy

## Supported Versions

ContractGraph is developed on `main`. Security fixes land on `main`; there are
no maintained release branches yet.

## What Counts as a Security Issue Here

ContractGraph has no server, no database, no network listener, and no API keys.
Its security surface is therefore narrower than a typical application — and
almost entirely about **data confinement**. Please report any of the following:

- **Private context leaking into a publishable artifact.** A path under
  `context/private/`, `context/canonical/`, or `context/derived/` read by a
  script, embedded in a generated skill or subagent, copied into a compiled
  manifest, or written into anything git-tracked.
- **A `.gitignore` gap** that would cause run output, canonical context, or a
  private bundle to be committed by an ordinary `git add -A`.
- **Derived context misclassified as public** when it was produced from private
  inputs, or a privacy classification that downgrades on re-run.
- **A deterministic script reaching outside its given paths** — writing outside
  the directories passed on its command line, reading `context/private/`, or
  making a network call it does not document.
- **Arbitrary code execution** from processing an untrusted contract bundle,
  context file, node output, or telemetry export.
- **Path traversal** via a contract's `contract`, `contextRefs`, or `path`
  fields escaping the bundle or context root.

## What Is Not a Security Issue

- A model producing a wrong, unsupported, or low-quality research claim. That
  is a correctness concern — open a normal issue.
- `context/private/` being enforced by path exclusion and eval checks rather
  than an OS-level sandbox. This is a documented limitation, stated in the
  README: it is a confinement convention, not a security boundary.
- Anything requiring an attacker to already have write access to your local
  repository or your Claude Code configuration.

## Reporting

**Do not open a public issue for a security report.**

Use GitHub's private vulnerability reporting on this repository:
**Security → Report a vulnerability**
(<https://github.com/Phoenixarjun/ContractGraph/security/advisories/new>)

Please include:

- what leaks or executes, and the exact path or command that demonstrates it,
- a minimal reproduction — ideally a synthetic contract bundle or context file,
  never one containing your own real personal data,
- the commit you reproduced against, your OS, and your Python version,
- the impact as you see it.

**Never attach real private context, a real resume, or a real run's output to a
report.** If a reproduction seems to need one, describe its shape instead and a
synthetic equivalent will be constructed.

## Response

This is a single-maintainer project, so timelines are best-effort rather than
contractual:

| Stage | Target |
|---|---|
| Acknowledgement | within 7 days |
| Initial assessment | within 14 days |
| Fix or documented mitigation | depends on severity; you will be kept updated |

Valid reports are credited in the release notes unless you ask otherwise.
Please give a reasonable window for a fix before disclosing publicly.

## Hardening You Control

- Keep real ground truth in `context/canonical/` and `context/private/`. Both
  are git-ignored. Public examples belong in `context/synthetic/`.
- Review `git status` before committing. `python evals/run_evals.py` includes
  privacy-leakage cases over `.claude/skills/` and `.claude/agents/`.
- Treat a contract bundle from an untrusted source the way you would treat any
  untrusted config: read it before running `/contractgraph:init` on it.
