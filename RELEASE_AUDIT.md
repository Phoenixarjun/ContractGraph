# Release Audit — ContractGraph v1 Public Release

**Role:** Release Engineer / Maintainer
**Scope:** Stabilize the existing implementation for first public open-source release. No architectural changes, no new features.
**Date:** 2026-08-02

---

## 1. Verification Evidence

Everything below was verified by running it in this session, not by inspection alone.

| Check | Command | Result |
|---|---|---|
| Full eval suite, working tree (with local private data present) | `python evals/run_evals.py` | **270/270 passed** |
| Full eval suite, simulated fresh clone (only committable files) | same, in an export of `git ls-files -co --exclude-standard` | **240/240 passed, 7 skipped** |
| Public bundle structural validation | `python scripts/validate_contract_bundle.py contracts/study-plan` | ok — 6 nodes, 0 errors, 0 warnings |
| Public context validation | `python scripts/validate_context.py context/synthetic/study-plan` | ok — 3 files, 0 errors |
| Compiled graph validation | `python scripts/validate_compiled_graph.py runtime/compiled/study-plan/graph.json` | ok — 6 nodes, 3 layers, no cycles/orphans |
| Every relative Markdown link in the repo | link resolver over all `.md` | all resolve |
| Every `scripts/*.py` referenced from a command, skill, or doc | path existence check | 30/30 exist |
| Sensitive-marker scan over all 145 committable files | regex over names, emails, employer, run/session ids, absolute paths | **0 hits** |

The **7 skips** on a fresh clone are intentional and each prints its reason: 6 cases need a completed run under the git-ignored `runtime/runs/`, and 1 needs a local-only private bundle. A skip is never counted as a pass.

---

## 2. Repository Issues Found

### Release blockers

| # | Issue | Impact |
|---|---|---|
| B1 | The eval suite hard-depended on `contracts/company-research/`, a git-ignored private bundle. | On a fresh clone the suite failed 28 cases. The repo's own self-check was broken for every user but the author. |
| B2 | `/contractgraph:init`, `:run`, and `:validate` all defaulted to `contracts/company-research` — a bundle not present in the repo. | Every command failed out of the box. |
| B3 | `/contractgraph:finalize` fell back to `contracts/claude-architect-professional` (also absent) and its usage examples used private run IDs. | Same, plus leaked internal run identifiers. |
| B4 | 11 scripts defaulted `--bundle` to `contracts/company-research`; 8 defaulted compiled paths to a flat `runtime/compiled/` that init no longer produces. | Every script's documented default was wrong. |
| B5 | `scripts/validate_domain_leakage.py` hard-coded a domain vocabulary keyed on `bundleId == "claude-architect-professional"`, and `finalize_run.py` carried a second inline copy keyed on `"claude-architect" in bundle_id`. | Direct violation of the project's own non-negotiable boundary ("no domain workflow hard-coded into the framework core"), and the checker silently no-opped for every public bundle — a validator that appears to run but checks nothing. |

### Consistency and correctness

| # | Issue |
|---|---|
| C1 | Compiled-artifact layout drift: commands, skills, and docs referenced a flat `runtime/compiled/`, while init actually writes per-bundle `runtime/compiled/<bundleId>/`. |
| C2 | `contract-designer` skill taught a bundle layout (`contract-bundle.json`, `main.contract.json`, `nodes/`, `policies.yaml`) that `validate_contract_bundle.py` **rejects**. Any bundle authored from the skill would fail validation. |
| C3 | `/contractgraph:finalize` existed as a command and script but appeared in no doc, no architecture diagram, and no command list. `getting-started.md` still said "The Five Commands". |
| C4 | `docs/graph-compilation.md` referenced `scripts/merge_sections.py`, which does not exist (real name: `merge_verified_sections.py`). |
| C5 | `docs/evaluation.md` claimed the eval directories were "scaffolded and cases are not yet authored" — there were 270 cases. |
| C6 | `docs/execution.md` documented a 19-step lifecycle ending at "write final/", with no finalization stage or terminal run state. |
| C7 | `run.md` referenced `resume-analysis` — a node from a private bundle — inside a generic command. |
| C8 | Architecture diagrams in `README.md`, `CLAUDE.md`, and `docs/architecture.md` predated the `validate`/`finalize` lifecycle. |

### Hygiene

| # | Issue |
|---|---|
| H1 | 13 scratch/debug files tracked or untracked at the repo root and in `evals/`: `ANCHORED_SUMMARY.md`, `files.py`, `_check_dl.py`, `_check_repair.py`, `_check_run.py`, `evals/dbg_*.py` (6), `evals/test_finalize_debug.py`. |
| H2 | `scripts/repair_evidence_domain.py` was a one-off with a hard-coded absolute path to a personal run directory. |
| H3 | `runtime/telemetry-preflight/` contained a raw session export with a real session ID and absolute user paths — untracked but not ignored, one `git add -A` from being published. |
| H4 | `runtime/compiled/claude-architect-professional/` contained a real person's name in its compilation report and context manifest — untracked but not ignored. |
| H5 | `.gitignore` did not cover `runtime/telemetry-preflight/`, `.migrations/`, `contracts/claude-architect-professional/`, editor/OS/venv noise, or scratch-file patterns. |
| H6 | `context/derived/` was ignored by a bare directory rule that would also have dropped its tracked `README.md`. |
| H7 | `__pycache__/` directories present in the working tree. |

### Documentation containing internal or test-run material

| # | Issue |
|---|---|
| D1 | Six docs were written as internal postmortems anchored to a specific private local run ID (`20260728-study-plan`) that ships with neither the repo nor any reader's clone. |
| D2 | `docs/privacy-propagation.md` described the *contents* of the author's real canonical context ("real name, real compensation figures, real portfolio projects"). |
| D3 | `docs/opencode-benchmark.md` and `docs/benchmark-methodology.md` carried task-scope instructions ("do not execute yet", "explicitly out of scope for execution this task", "the user's **real** canonical context"). |
| D4 | `docs/optimization-plan.md` was a 250-line internal build spec addressed to an implementing agent ("Implement with Sonnet", "tasks 13-19"), numbered against a work plan no reader has. |
| D5 | `runtime/compiled/study-plan/compilation-report.md` — a tracked artifact — referenced the private bundle and carried "not performed this task" language. |

---

## 3. Fixes Applied

### Blockers

- **B1** — `evals/run_evals.py` now resolves bundles through `available_bundles()` and guards run-dependent cases with `have_real_run()`. Cases that cannot run call a new `skip(cat, name, reason)` and are printed as `SKIP` with the reason plus a count in the summary line. Three negative-validation cases were rebuilt against the public `study-plan` bundle (invalid subcontract ref, missing role file, dangling dependency), and a **fourth was added** (aggregationPath mismatch). The 14-case finalization fixture was ported from the private bundle to `contracts/study-plan`, so all of it survives a fresh clone. `merge`, `cache_key`, `preserve_user_state`, `validate_references`, and `trace` fixtures were moved onto public node ids and neutral example URLs.
- **B2, B3** — Command defaults now point at `contracts/study-plan`. `finalize.md` derives the bundle from the run's own `run.json` and stops rather than guessing; examples use a neutral run id. The "approved bootstrap exception" carve-out for a private bundle was replaced with a general rule: `init` never designs or edits a contract.
- **B4** — All 11 bundle defaults and 8 compiled-path defaults updated to the public bundle and the per-bundle compiled layout.
- **B5** — Domain-leakage vocabulary moved **out of the framework core and into the bundle**. `validate_domain_leakage.py` now reads `policies.json` → `domainLeakage` (`allowedUnconditional`, `allowedWithLabel`, `disallowed`, `exemptNodes`); `finalize_run.py` delegates to that same loader instead of holding a second inline copy. A bundle with no declared policy is reported `checked: false` with an explanatory note — **never a silent pass**. The `study-plan` bundle now declares its own policy, so the shipped example actually exercises the checker, and a new eval case asserts the no-policy path reports unchecked rather than passing.

### Consistency

- **C1** — `runtime/compiled/<bundleId>/` normalized across all six commands, `workflow-compiler` and `graph-plan-reviewer` skills, `CLAUDE.md`, and `docs/{architecture,execution,graph-compilation,getting-started,token-optimization}.md`. Added the explicit invariant that one bundle compiles into one directory so bundles cannot overwrite each other.
- **C2** — `contract-designer` now teaches the layout the validator actually enforces, with a real `contract.bundle.json` example and the `nodeId`/`aggregationPath` agreement rules it checks.
- **C3** — `finalize` documented in `README.md`, `CLAUDE.md`, `docs/architecture.md`, `docs/execution.md`, and `docs/getting-started.md` ("The Six Commands").
- **C4** — corrected to `merge_verified_sections.py`; the deterministic-script list also gained `build_node_packets.py` and `cache_key.py`.
- **C5** — `docs/evaluation.md` rewritten around the real suite, including how to run it and what SKIP means.
- **C6** — `docs/execution.md` gained the finalization stage and terminal run states; its run-directory tree now shows `trace/`, `.migrations/`, and `final/verification-summary.json`.
- **C7** — generalized to "a node the bundle declares as a map node".
- **C8** — all three diagrams replaced with the canonical `context → contract → init → run → validate → finalize` lifecycle.

### Hygiene

- **H1, H2, H7** — 14 files deleted, `__pycache__/` removed.
- **H3, H4, H5, H6** — `.gitignore` rewritten with sectioned rules covering private context, runtime artifacts, private bundles and their compiled output, generated agents, scratch patterns, and tooling/OS noise. `context/derived/README.md` explicitly re-included. Verified with `git ls-files -i -c --exclude-standard` → nothing tracked is ignored.

### Documentation

- **D1** — `runtime-state.md`, `time-and-provenance.md`, `source-governance.md`, `runtime-telemetry.md`, and `privacy-propagation.md` rewritten as mechanism documentation. Every technical rule is preserved; the private run ID appears nowhere.
- **D2** — the description of real canonical content removed and replaced with the general classification rule.
- **D3** — benchmark docs rewritten as reproducible procedures. Both now state plainly that the repo ships methodology and configs, not results.
- **D4** — `docs/optimization-plan.md` **deleted**. Its durable content already lives in `token-optimization.md` and `token-efficiency.md`; no link to it remained anywhere.
- **D5** — compilation report cleaned of private-bundle references and task-scope language.

### Release documentation

- **`README.md`** — rewritten end to end: badges, TOC, why-it-exists (with a failure-mode table), what-it-is-not, architecture + Mermaid diagram, workflow lifecycle, installation, quick start, all six commands, concepts (Context / Contract / Graph Compilation / Validation / Repair), repository structure, examples, limitations, roadmap, contributing, and a documentation index.
- **`CONTRIBUTING.md`** — new: ways to contribute, setup, the architectural boundaries a PR must respect, project layout, testing rules (including SKIP-vs-FAIL), coding standards, skill/agent/contract authoring rules, privacy rules, Conventional Commits, branching and PR checklist, bug reports, feature proposals, license of contributions.
- **`LICENSE`** — copyright holder aligned to the release identity (PhoenixArjun).
- **`CLAUDE.md`** — compiled layout, finalize stage, command list, diagram, and the "Current V1 Focus" section (which named a private workflow as the project's focus) replaced with a neutral "Reference Workflow" section.

---

## 4. Files Modified

**Deleted (15)**

```
ANCHORED_SUMMARY.md            files.py                       _check_dl.py
_check_repair.py               _check_run.py                  scripts/repair_evidence_domain.py
evals/dbg_happy.py             evals/dbg_happy2.py            evals/dbg_sg.py
evals/dbg_trace.py             evals/dbg_trace2.py            evals/dbg_trace3.py
evals/test_finalize_debug.py   docs/optimization-plan.md      scripts/__pycache__/
```

**Added (2)** — `CONTRIBUTING.md`, `RELEASE_AUDIT.md`

**Modified — commands (6)**
`.claude/commands/contractgraph/{context,contract,init,run,validate,finalize}.md`

**Modified — skills (3)**
`.claude/skills/bootstrap/{contract-designer,workflow-compiler,graph-plan-reviewer}/SKILL.md`

**Modified — scripts (14)**
`build_context_manifest.py`, `build_contract_manifest.py`, `build_dependency_summary.py`, `build_node_packets.py`, `cache_key.py`, `dry_run.py`, `finalize_run.py`, `merge_verified_sections.py`, `preserve_user_state.py`, `schedule_plan.py`, `validate_compiled_graph.py`, `validate_domain_leakage.py`, `validate_final_output.py`, `validate_node_output.py`, `validate_references.py`

**Modified — contracts / runtime fixtures (2)**
`contracts/study-plan/policies.json` (declares `domainLeakage`), `runtime/compiled/study-plan/compilation-report.md`

**Modified — evals (3)**
`evals/run_evals.py`, `evals/README.md`, `evals/workflow-cases/dry-run.json` (now drives the dry-run loop)

**Modified — docs (14)**
`architecture.md`, `benchmark-methodology.md`, `contract-model.md`, `evaluation.md`, `execution.md`, `getting-started.md`, `graph-compilation.md`, `opencode-benchmark.md`, `privacy.md`, `privacy-propagation.md`, `runtime-state.md`, `runtime-telemetry.md`, `source-governance.md`, `time-and-provenance.md`, `token-optimization.md`

**Modified — root (4)**
`README.md`, `CLAUDE.md`, `LICENSE`, `.gitignore`

---

## 5. Personal Information Removed

| Item | Where | Disposition |
|---|---|---|
| Author's real name | `runtime/compiled/claude-architect-professional/{compilation-report.md, context-manifest.json}` | Directory git-ignored; never committed |
| Resume filename and canonical resume paths | same context manifest | Same |
| Employer email in commit metadata | pre-existing commits (`8788bec` and earlier) | Historical; git config set so new commits use the release identity. Not rewritten — see §7 |
| Absolute user paths (`C:\Users\naresh.b\...`) | `_check_*.py`, `evals/dbg_trace*.py`, `scripts/repair_evidence_domain.py` | Files deleted |
| Real OpenCode session export (session id, model, absolute paths, full transcript) | `runtime/telemetry-preflight/opencode/raw/session-*.json` | Directory git-ignored; never committed |
| Company name from a real research run (`paypal`) and run identifiers | `ANCHORED_SUMMARY.md` (forensic audit of private runs) | File deleted |
| Private contract bundle | `contracts/claude-architect-professional/` | Git-ignored |
| Private contract bundle | `contracts/company-research/` | Already ignored; kept ignored |
| Real canonical context (19 files) | `context/canonical/` | Already ignored; ignore rule retained and documented |
| 735 files of real run output | `runtime/runs/` | Already ignored; ignore rule retained |
| Description of real canonical content | `docs/privacy-propagation.md` | Text rewritten |
| Private run IDs referenced as documentation anchors | 6 docs | Rewritten |
| Personal long-form notes with private examples | `ContractGraph.md` | Remains git-ignored (verified to contain a real resume filename and a real company name) |

**Verification:** a regex sweep for names, employer, personal email, session ids, run ids, and absolute user paths across all **145** committable files returns **zero** hits.

---

## 6. Documentation Improvements

- README rewritten to mature open-source standard — every section the brief specified, plus a documentation index and a plainly-stated limitations section.
- CONTRIBUTING.md added, encoding the architectural boundaries so a future contributor cannot violate them by accident.
- Six internal postmortems converted into mechanism documentation that stands on its own.
- One internal build spec removed.
- The `finalize` stage — previously undocumented despite being implemented and tested — now appears in every place the lifecycle is described.
- All three architecture diagrams unified on the intended lifecycle.
- Every relative link, every referenced script path, and every command default verified to resolve.
- `getting-started.md` gained an actual `git clone` → self-check → run sequence.

---

## 7. Remaining Technical Debt

Stated plainly. None of these block release; all are honest limitations rather than hidden ones.

1. **Git history retains the author's employer email** in commits `8788bec` and earlier, plus a private `contracts/company-research/` tree and one generated agent file that were committed before being untracked. Those historical files are contract schemas and agent definitions — no PII was found in them — so history was **not** rewritten. Rewriting would break every existing clone and the two open feature branches. If the employer email must be scrubbed, that is a deliberate `git filter-repo` operation on an otherwise-quiet repository, not part of a stabilization pass.

2. **Six eval cases only run with local data.** They exercise real-run trace normalization, timestamp validation, privacy classification, source scoring at scale, and the migration script. On a fresh clone they skip with a reason. Converting them to synthetic fixtures would restore that coverage for everyone.

3. **`contracts/study-plan` is the only shipped bundle.** Genericity is argued in the docs and enforced by the "no domain logic in core" boundary, but a second *public* bundle of a different shape would prove it to a reader rather than asking for trust.

4. **Node-state writing is a prose instruction, not a script.** `run.md` tells the orchestrator to write `state`; nothing enforces the key at write time, which is why `generate_trace.py` must accept a legacy `status` alias. A `write_node_state.py` would close this.

5. **No CI.** The eval suite is deterministic, offline, and fast — it is a natural GitHub Actions job, and adding one would make the "240/240 on a clean checkout" claim continuously true rather than true as of this audit.

6. **No issue/PR templates, no `CODE_OF_CONDUCT.md`, no `SECURITY.md`.** CONTRIBUTING.md points security-relevant reports at a private advisory, but the file itself does not exist yet.

7. **TOON output-quality dimension remains `pending`.** Size and round-trip losslessness are measured; whether TOON-encoded arrays degrade model output can only come from an executed benchmark. TOON stays disabled at runtime, which is the correct posture until then.

8. **Benchmark results are unpublished.** The methodology, configs, and comparison tooling ship; no numbers do. This is deliberate — see `docs/benchmark-methodology.md`.

9. **`docs/` is 24 files.** Thorough, but there is overlap between `token-efficiency.md` / `token-optimization.md` and between `token-telemetry.md` / `runtime-telemetry.md`. A future consolidation pass would reduce reader load. Not attempted here: merging documents is an editorial rewrite, outside a stabilization brief.

---

## 8. Release Readiness Checklist

| # | Criterion | Status |
|---|---|---|
| 1 | Repository clones and self-checks green with no extra setup | **Pass** — 240/240, 7 explained skips |
| 2 | Every slash command's default resolves to something present in the repo | **Pass** |
| 3 | Every script default path resolves | **Pass** |
| 4 | Every referenced script exists (30/30) | **Pass** |
| 5 | Every relative Markdown link resolves | **Pass** |
| 6 | No personal, private, or experimental data in committable files | **Pass** — 0 hits across 145 files |
| 7 | No test/scratch/debug files | **Pass** — 15 removed |
| 8 | `.gitignore` covers private context, runs, private bundles, generated agents, tooling noise | **Pass** |
| 9 | Nothing tracked is also ignored | **Pass** |
| 10 | Skills carry trigger-first descriptions and no PII (18/18) | **Pass** |
| 11 | Public example bundle validates (bundle, context, compiled graph) | **Pass** |
| 12 | Public example context is fully synthetic | **Pass** |
| 13 | No domain workflow hard-coded into the framework core | **Pass** — last violation moved into bundle policy |
| 14 | Documented architecture matches implemented architecture | **Pass** |
| 15 | README meets mature open-source standard | **Pass** |
| 16 | CONTRIBUTING.md present | **Pass** |
| 17 | LICENSE present and consistent | **Pass** — MIT |
| 18 | Limitations stated honestly | **Pass** |
| 19 | Automated CI | **Not present** — debt item 5 |
| 20 | Issue/PR templates, CODE_OF_CONDUCT, SECURITY.md | **Not present** — debt item 6 |

---

## 9. Final Recommendation

### ✅ Ready for public release

A developer can clone this repository, run one command to verify it works, read one README to understand what it is, and run the bundled example without supplying any data of their own. Every command default, script default, documented path, and cross-reference resolves against files that are actually in the repository. No personal, private, or experimental data reaches a committable file.

The two remaining gaps — CI and community health files — are additive repository configuration, not defects in the framework. They can land in a follow-up without touching a line of framework code.

One judgment call is worth flagging explicitly for the maintainer: the domain-leakage vocabulary was **moved from the framework core into bundle policy** (issue B5). This was not a redesign but the removal of a hard-coded domain that the project's own `CLAUDE.md` forbids, and it turned a validator that silently no-opped on every public bundle into one that actually runs. Behavior is preserved for any bundle that declares the policy; a bundle that declares none is now reported as *unchecked* rather than passing. If you prefer the previous behavior, that decision is a one-file revert in `scripts/validate_domain_leakage.py`.
