# Contributing to ContractGraph

Thanks for considering a contribution. This document covers how to set up, what
the project will and will not accept, and how to get a change merged.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
Disagreements are resolved with evidence — a failing test, a file and line, a
reproduction — not assertion.

Security and privacy issues follow a separate, private path: see
[SECURITY.md](SECURITY.md). Never open a public issue for one.

---

## Table of Contents

- [Ways to Contribute](#ways-to-contribute)
- [Development Setup](#development-setup)
- [Architectural Boundaries](#architectural-boundaries)
- [Project Layout for Contributors](#project-layout-for-contributors)
- [Testing](#testing)
- [Coding Standards](#coding-standards)
- [Writing Skills, Agents, and Contracts](#writing-skills-agents-and-contracts)
- [Privacy Rules](#privacy-rules)
- [Commit Convention](#commit-convention)
- [Branching and Pull Requests](#branching-and-pull-requests)
- [Reporting Bugs](#reporting-bugs)
- [Proposing Features](#proposing-features)
- [License of Contributions](#license-of-contributions)

---

## Ways to Contribute

| Contribution | Notes |
|---|---|
| Bug reports | Especially anything the eval suite fails to catch. |
| Deterministic script fixes | The highest-value area — these are directly testable. |
| New eval cases | Planted-defect fixtures that prove a validator actually rejects something. |
| Documentation | Corrections, clarifications, and worked examples. |
| Reusable skills | A genuinely cross-bundle capability that no existing skill covers. |
| Example bundles | A synthetic, publishable contract bundle demonstrating a new workflow shape. |

## Development Setup

```bash
git clone https://github.com/Phoenixarjun/ContractGraph.git
cd ContractGraph
python evals/run_evals.py
```

**Requirements**

- Python 3.11+ (standard library only for the core).
- [Claude Code](https://claude.com/claude-code) if you want to exercise the slash commands.

Optional extras used by a few scripts are listed in `scripts/requirements.txt`.
Every one of them is optional: a script whose optional dependency is missing must
report a documented `unavailable` state and must never invent data to fill the gap.

A clean checkout with nothing installed should print
`226/226 passed, 8 skipped`. A SKIP means the case needed something a clean
checkout legitimately lacks: a local-only private bundle, a completed run under
the git-ignored `runtime/runs/`, or an optional extra. Installing the extras
(`pip install pypdf`) raises it to `240/240 passed, 7 skipped`. A **FAIL** on a
clean checkout is a bug — please report it.

## Architectural Boundaries

These are not stylistic preferences. A PR that crosses one will be asked to
change, regardless of how useful the feature is.

**The framework core must never:**

- Introduce LangGraph, the Anthropic SDK, an external model API, or an API key requirement.
- Introduce a web server, database, queue, or background daemon.
- Call a model, implement agent reasoning, or choose a research conclusion from a Python script.
- Hard-code a domain concept. If a term like "resume", "DSA", or "compensation" appears in
  `scripts/`, `.claude/commands/`, or a bootstrap skill, that knowledge belongs in a
  contract bundle instead.
- Require the user to hand-design the execution graph.
- Place private user information into a generated skill or agent definition.

**Python scripts in `scripts/` are for deterministic operations only:** document
extraction, OCR fallback, hashing, indexing, JSON Schema validation, JSON
merging, cache keys, TOON conversion, token-size comparison, trace formatting,
telemetry normalization. Same input, same output, every time.

**JSON is canonical.** TOON is a transport encoding, gated behind a measured
benchmark, and never a schema change.

If your change makes a workflow work by editing a script, a skill, or a command
rather than a contract, that is a genericity regression. The public
`contracts/study-plan` bundle exists to catch exactly this.

## Project Layout for Contributors

| Path | What lives there | Change it when |
|---|---|---|
| `scripts/` | Deterministic utilities | Fixing a validator, aggregator, or formatter |
| `.claude/commands/contractgraph/` | The six slash commands (plain Markdown) | Changing a command's procedure |
| `.claude/skills/bootstrap/` | Skills that build the framework | Changing how compilation itself works |
| `.claude/skills/reusable/` | Verified cross-bundle capabilities | Adding a genuinely reusable capability |
| `contracts/<workflow>/` | Domain knowledge — all of it | Adding or changing a workflow |
| `context/synthetic/` | Publishable example context | Extending an example |
| `evals/` | The regression suite | Always, alongside a behavior change |
| `docs/` | Topic documentation | Alongside anything user-visible |

`.claude/agents/generated/`, `runtime/compiled/<bundleId>/`, and
`runtime/runs/` are **outputs**. Do not hand-edit them and do not commit
generated artifacts that reference a private context path.

## Testing

```bash
python evals/run_evals.py
```

Rules for the suite:

- Every behavior change ships with an eval case. A validator change without a
  planted-defect case that fails before your fix is incomplete.
- Cases run offline: no network, no model calls, no live research.
- A case that cannot run in this environment must call `skip(...)` with a
  reason. Never silently drop a case, and never let a skip count as a pass.
- Prefer building fixtures against the public `contracts/study-plan` bundle so
  the case survives a fresh clone.

You can also run any validator directly:

```bash
python scripts/validate_contract_bundle.py contracts/study-plan
python scripts/validate_compiled_graph.py runtime/compiled/study-plan/graph.json
```

## Coding Standards

**Python**

- Standard library only in the core. Anything else is optional and degrades gracefully.
- `from __future__ import annotations` at the top; type annotations on function signatures.
- A script CLI prints a JSON report on stdout and uses these exit codes:
  `0` = ok, `1` = validation failure, `2` = IO/usage error.
- Errors are reported, never guessed around. Missing data becomes an explicit
  `null` with a stated reason — never a plausible-looking default.
- No hidden global state, no network access, no writes outside the paths the CLI was given.

**Markdown (commands, skills, docs)**

- A skill description is trigger-first and begins with "Use when …" — the eval
  suite enforces this.
- Reference real paths. A broken path in a command or skill is a bug of the same
  severity as a broken import.

## Writing Skills, Agents, and Contracts

**A skill must:** solve one reusable capability; carry a precise trigger
description; define bounded procedure, inputs, outputs, evidence requirements,
and failure behavior; contain no private facts, company-specific details, or
run-specific details; not duplicate an existing skill; and stay small enough to
preload without wasting context.

Do not create one large skill containing an entire workflow, and do not create
several overlapping skills with slightly different names.

**A generated subagent must:** own one bounded responsibility with explicit
input and output contracts, the minimum necessary tools, an assigned model, a
token and search budget, a retry policy, evidence requirements, and clear stop
conditions. A subagent may complete its own node. It must never approve its own
output or declare the workflow complete.

**A contract bundle must** match the layout `scripts/validate_contract_bundle.py`
enforces — `contract.bundle.json`, `contract.schema.json`, `node-contracts/`,
`graph.yaml`, `policies.json` — with each node contract's
`properties.nodeId.const` and `x-contractgraph.aggregationPath` agreeing with
the bundle, and every required node's `aggregationPath` required by the main
contract.

## Privacy Rules

Non-negotiable, and enforced by evals:

- Never commit anything from `context/canonical/`, `context/private/`,
  `context/derived/`, or `runtime/runs/`. All are git-ignored.
- Never put personal identifiers, resume text, or project secrets into a skill,
  an agent definition, a contract, a doc, or an eval fixture.
- Public examples use synthetic context only.
- Derived context carries provenance (source run, generating node, evidence refs,
  confidence, freshness, contract version) and never overwrites canonical context.
- Before opening a PR, check your diff: `git diff --stat` and confirm no path
  under an ignored directory appears.

## Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<scope>): <subject>

<body — what changed and why, not how>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`.
Scopes are usually a directory or bundle: `scripts`, `evals`, `docs`,
`commands`, `skills`, `study-plan`.

```text
fix(scripts): read domain-leakage vocabulary from the bundle, not the core
docs(execution): document the finalize stage and terminal run states
test(evals): add a planted aggregationPath-mismatch case
```

Keep the subject imperative and under ~72 characters. Reference an issue with
`Closes #123` in the body when applicable.

## Branching and Pull Requests

- `main` — released, stable.
- `dev` — integration branch. **Branch from `dev` and target `dev`.**
- `feat/<short-name>` / `fix/<short-name>` — your working branch.

Before opening a PR:

1. `python evals/run_evals.py` passes with no FAILs.
2. Docs are updated for any user-visible change.
3. An eval case covers the new behavior.
4. No ignored path appears in your diff.
5. Commits are conventional and scoped to one concern.

CI runs the same suite on every push and pull request — Ubuntu and Windows,
Python 3.11 and 3.12 — plus the public-bundle validators and a check that no
private path is tracked. The PR template restates this checklist; paste your
actual eval output into it rather than asserting it passed.

A PR description should state what changed, why, how it was verified (with the
actual command output), and anything deliberately left out of scope. Small,
single-concern PRs are reviewed faster than large ones.

## Reporting Bugs

Open an issue with:

- What you ran (exact command) and what you expected.
- What actually happened, including exit code and the JSON error output.
- Your OS and Python version.
- Whether `python evals/run_evals.py` passes on a clean checkout.

For anything with a security or privacy impact — a path that leaks private
context, an artifact that embeds PII — please open a private security advisory
on the repository rather than a public issue.

## Proposing Features

Open an issue before writing code. Describe the problem, not just the solution,
and say which architectural boundary it touches. Features that would require a
server, an external model API, or domain logic in the core will be declined —
but there is very often a way to express the same idea as a contract, a policy,
or a reusable skill instead.

## License of Contributions

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE) that covers this project.
