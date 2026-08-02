# Runtime State

## The Canonical Enum

Every node in a run has exactly one state, drawn from this enum and written
under the key **`state`** in `runtime/runs/<run-id>/node-state/<nodeId>.json`:

```text
PENDING  READY  RUNNING
STRUCTURAL_FAILED  SEMANTIC_FAILED  EVIDENCE_FAILED  FRESHNESS_FAILED
ACCEPTED  EXHAUSTED  SKIPPED_CACHE
```

`ACCEPTED` and `SKIPPED_CACHE` are the only terminal-OK states
(`generate_trace.py`'s `TERMINAL_OK`). A required node in any other terminal
state — `EXHAUSTED`, or a `*_FAILED` state that exhausted its retries — blocks
`allRequiredTerminalOk`, which blocks completion.

## Where State Is Written

`.claude/commands/contractgraph/run.md` step 6 instructs the orchestrator to
record each transition (`PENDING → READY → RUNNING → … → terminal`) under the
`state` key as the node moves through the pipeline. This is a prose instruction
to the executing agent, not a deterministic script — there is no
`write_node_state.py`, and nothing enforces the key name at write time. That is
precisely why the *reader* is defensive.

## Read-Time Normalization

`scripts/generate_trace.py`'s `normalize_node_state()`:

1. Reads `state` first, then falls back to the legacy `status` key.
2. Uppercases the value and validates it against the canonical enum above.
3. **Never silently maps an unrecognized value.** A record with neither key, a
   non-string value, a null value, or a value outside the enum is excluded from
   `byState` and appended to a top-level `validationErrors[]` entry naming the
   node id, the field inspected, and the reason. There is no `UNKNOWN` bucket:
   a state either normalizes to a real enum value or it is a reported error.
4. Emits `summary.invalidRecordCount`, `summary.requiredNodesConsidered`, and
   `summary.requiredNodesSource` so the trustworthiness of
   `allRequiredTerminalOk` is auditable rather than assumed.

The reader is forgiving of the legacy shape so that older runs still produce a
correct trace. `run.md` is explicit that **new** writes use `state`. The
`status` alias is a backward-compatible read path, never a second sanctioned
write shape.

## `allRequiredTerminalOk` Is Never Vacuous

Node-state's own `required` flag is not something `run.md` mandates writing, so
relying on it alone would make `allRequiredTerminalOk` an `all()` over zero
nodes — vacuously true. Passing `--bundle <dir>` makes `generate_trace.py`
cross-reference `contract.bundle.json`'s own required-node list instead:

- `requiredNodesSource` becomes `"bundle"`,
- `requiredNodesConsidered` reflects the bundle's real node count,
- a required node with **no node-state file at all** — one that never ran — is
  reported in `missingRequiredNodes` rather than silently passing.

`run.md` always passes `--bundle`. The flag remains optional only for
backward compatibility with callers that have no bundle path at hand.

## Terminal Run States

`run.json`'s `runStatus` is written by `scripts/finalize_run.py`:

| State | Meaning |
|---|---|
| `RUNNING` | Set by the run lifecycle before node execution. |
| `FINALIZING` | Set on the first finalization attempt. |
| `COMPLETED` | Every finalization check passed. |
| `FINALIZATION_FAILED` | One or more checks failed; the failing check names are recorded. |

A run is complete only when `runStatus` is `COMPLETED`. See
[execution.md](execution.md).

## Migration

`scripts/migrate_run_metadata.py` normalizes an existing run's
`node-state/*.json` files on disk to the canonical `state` key and regenerates
`trace.json` with the current reader. See
[time-and-provenance.md](time-and-provenance.md) for what else the same pass
touches.

## Tests

`evals/run_evals.py`'s `t_trace_state_normalization` and
`t_trace_required_from_bundle` cover the legacy `status` key, a lowercase
value, a missing field, an invalid enum value, and the difference between a
bundle-sourced and a record-sourced required-node count.
