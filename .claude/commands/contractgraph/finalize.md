---
description: Finalize a completed run — aggregate accepted sections, validate everything, generate artifacts, and mark the run COMPLETED or FINALIZATION_FAILED. Idempotent: safe to re-run.
argument-hint: <run-id> [--bundle <bundle>] [--force] [--telemetry-source opencode <file>] [--context-root <dir>]
allowed-tools: Read, Write, Bash
---

Finalizes a run that has all required nodes ACCEPTED. This is the terminal stage of `/contractgraph:run`. It never launches producers, never runs research, and never re-verifies already-accepted sections.

Run ID from the user (required): $ARGUMENTS

Usage:

```
/contractgraph:finalize 20260801-study-plan-01
/contractgraph:finalize 20260801-study-plan-01 --force
/contractgraph:finalize 20260801-study-plan-01 --telemetry-source opencode /path/to/export.json
```

Steps:

1. **Parse the argument.** The first positional token is the <run-id>. Optional flags: `--bundle <path>` (default: derive from the run's `run.json` `bundleId`; if that is missing, stop and ask rather than guessing a bundle), `--force` (re-finalize even if already COMPLETED), `--telemetry-source <type> <file>` (pass to telemetry_normalize), `--context-root <dir>` (pass to build_derived_context).

2. **Resolve paths.** The run dir is `runtime/runs/<run-id>/`. The bundle dir is `contracts/<bundleId>/`. The compiled dir is `runtime/compiled/<bundleId>/`.

3. **Check preconditions.** Confirm the run dir exists, the bundle dir exists, and the compiled graph exists. If `run.json` shows `runStatus: COMPLETED` and `--force` is not set, report "already completed" and stop — nothing to do.

4. **Create backup.** Run `python scripts/finalize_run.py ...` internally creates an audit backup in `.migrations/<NNN>-pre-finalize/` before any modification. Never skip this.

5. **Let the script run.** Execute:
   ```
   python scripts/finalize_run.py --run runtime/runs/<run-id> --bundle contracts/<bundleId>
       [--compiled runtime/compiled/<bundleId>]
       [--context-root <dir>]
       [--force]
       [--telemetry-source <type> <file> ...]
   ```
   This single command runs ALL checks in sequence (required nodes, aggregation, schema validation, reference validation, global verification check, source governance, source completeness, domain leakage, derived context, privacy, telemetry, trace, report, terminal state). The script is deterministic and never calls a model.

6. **Read the result.** The script prints JSON `{ok, terminalState, checksPassed, checksTotal, checks: [...], failedChecks: [...]}`. If `terminalState` is `COMPLETED`, all checks passed — the run is complete. If `FINALIZATION_FAILED`, report the failed checks to the user.

7. **Report outcomes.** One line per failed check. If `COMPLETED`, report "Run <id> successfully finalized (<N>/<M> checks passed)".

Key behaviors:
- The script never launches producers or research.
- It never re-verifies already-accepted sections.
- It creates an audit backup before modifying anything.
- It is idempotent — re-running after a partial success picks up from where it left off (backups are sequential).
- Terminal states written to `run.json`: `FINALIZING`, `COMPLETED`, `FINALIZATION_FAILED`.
- Missing telemetry is never fabricated. Per-node token counts remain `null` when unavailable.
- Evidence/source-registry.json is validated for completeness but not regenerated.
- Global verification is checked for existence but not re-run.
