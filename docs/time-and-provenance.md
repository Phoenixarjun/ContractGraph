# Time and Provenance

A timestamp in a run artifact is a claim about when something happened. If it
was typed by an agent rather than read from a clock, it is not a measurement —
and an artifact that presents an estimate as a measurement is worse than one
with no timestamp at all. This document describes the rules that keep that
distinction enforceable.

## One Function Reads the Clock

`scripts/timestamp_now.py` prints `datetime.now(timezone.utc)` in the single
canonical format:

```text
YYYY-MM-DDTHH:MM:SS.mmmZ    (ISO-8601, UTC, exactly 3 fractional digits)
```

`run.md` instructs the orchestrator to call this script — never to estimate a
value — at each event boundary:

| Event | Field | Written to |
|---|---|---|
| run dir created | `runCreatedAt` | `run.json` |
| node reaches RUNNING | `nodeStartedAt` | `node-state/<id>.json` |
| node reaches a terminal state | `nodeCompletedAt` | `node-state/<id>.json` |
| global verdict produced | `verificationCompletedAt` | `verification/global-verification.json` |
| derived context written | `aggregationCompletedAt` (aliased `generatedAt`) | `final/derived-context.json` |
| final artifact written | `finalArtifactGeneratedAt` (aliased `generatedAt`, nested) | `final/final.json` |
| run marked complete | `runCompletedAt` | `run.json` |

Scripts never fabricate a timestamp or derive one from an estimated duration.
`timestamp_now.py` is the one narrow exception, because its entire job is
reading the real clock at the moment it is called — a measurement, not an
estimate.

## `validate_timestamps.py`: Format and Ordering

Two independent checks over a whole run directory:

**1. Format.** Every non-null timestamp must match the strict pattern above. A
value like `2026-07-28T13:45:00Z` — no milliseconds, landing exactly on a
5-minute boundary — fails: real wall-clock reads carry sub-second precision, and
a value that does not is a signal it was hand-typed. A `null` is valid only
when its record also carries a sibling `timestampSource: "unavailable"`. A bare
`null` with no explanation is itself a violation, because "missing" and
"explicitly unavailable" must stay distinguishable.

**2. Ordering.** `nodeStartedAt ≤ nodeCompletedAt` per node; `runCreatedAt ≤`
every `nodeStartedAt`; and

```text
max(nodeCompletedAt) ≤ verificationCompletedAt ≤ aggregationCompletedAt
                     ≤ finalArtifactGeneratedAt ≤ runCompletedAt
```

`verificationCompletedAt ≤ runCompletedAt` is also checked **directly**, not
only transitively, so it still fires when the intermediate
aggregation/final-artifact fields are absent entirely — the shape a partially
instrumented run actually has.

A stage that has not run yet — no `verification/global-verification.json` on an
in-progress run, say — is treated as *absence*, not a malformed null. The
validator only checks fields belonging to files that exist.

## "Completed" and "Generated" Legitimately Differ

A node's `nodeCompletedAt` is when its content was accepted. Global
verification, aggregation, and final-artifact generation are separate steps that
happen *after* every required node is accepted, so `finalArtifactGeneratedAt`
trailing every `nodeCompletedAt` by minutes or hours is expected.

What is never acceptable is a **later** stage timestamped **earlier** than an
**earlier** stage. That inversion is the class of defect this validator exists
to catch: a `verifiedAt` that precedes the completion it supposedly verified is
physically impossible and indicates a fabricated value.

## Migration: Null, Never Guess

`scripts/migrate_run_metadata.py` cannot recover the true wall-clock times of a
run whose timestamps were fabricated. Per the rule above it writes `null` plus
`timestampSource: "unavailable"` rather than a plausible-looking
reconstruction — including for a `generatedAt` whose original value had genuine
sub-second precision but disagreed with the rest of the run's timeline enough
that its authenticity could not be confirmed.

The original values are preserved unmodified in the pre-migration backup at
`runtime/runs/<run-id>/.migrations/<NNN>-pre-migration/` for audit. They are
simply no longer presented as trustworthy in the live artifacts.

## Tests

`evals/run_evals.py` covers valid ordering, the impossible
verification-after-completion sequence, missing-millisecond format rejection,
and null-with-source versus null-without-source.
