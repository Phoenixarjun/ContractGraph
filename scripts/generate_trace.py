#!/usr/bin/env python3
"""generate_trace - assemble a run trace from per-node state files.

Reads runtime/runs/<run-id>/node-state/*.json (each a record written by the run
command: nodeId, state, attempts, model, cacheKey, timings, verifier verdicts)
plus run.json, and emits a single trace.json: the ordered node timeline and a
summary (accepted / exhausted / cached / failed counts). Deterministic; no model.

Canonical node-state field is "state", enum CANONICAL_STATES below. Legacy
node-state files (like the study-plan fixture) wrote the same enum values
under the key "status" instead -- that key is accepted as a backward-compatible
alias, normalized to "state" here, and both raw and normalized shape are kept
in the emitted node record (nothing is dropped). A record that has neither key,
a non-string value, or a value outside the enum is NEVER silently bucketed as
"UNKNOWN": it is excluded from byState and reported in `validationErrors`
instead, so a malformed record surfaces as a visible error, not a lost count.

Usage:  python scripts/generate_trace.py --run <run-dir> [--bundle <bundle-dir>] [--out <path>]
        default out: <run-dir>/final/trace.json. Pass --bundle so
        allRequiredTerminalOk is checked against the bundle's own required-node
        list rather than a node-state.required flag nothing currently writes.
Output: JSON summary. Exit 0 ok (even with validation errors -- they're
        reported, not fatal), 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CANONICAL_STATES = {
    "PENDING", "READY", "RUNNING",
    "STRUCTURAL_FAILED", "SEMANTIC_FAILED", "EVIDENCE_FAILED", "FRESHNESS_FAILED",
    "ACCEPTED", "EXHAUSTED", "SKIPPED_CACHE",
}
TERMINAL_OK = {"ACCEPTED", "SKIPPED_CACHE"}


def normalize_node_state(record: dict) -> tuple:
    """Return (normalizedState|None, sourceField|None, error|None) for one node-state record.

    Tries the canonical "state" key first, then the legacy "status" alias.
    Never guesses at an unrecognized value -- that becomes an error instead.
    """
    if "state" in record:
        raw, source_field = record.get("state"), "state"
    elif "status" in record:
        raw, source_field = record.get("status"), "status"
    else:
        return None, None, "missing both 'state' and 'status' fields"
    if raw is None:
        return None, source_field, f"'{source_field}' is null"
    if not isinstance(raw, str):
        return None, source_field, f"'{source_field}' must be a string, got {type(raw).__name__}"
    normalized = raw.strip().upper()
    if normalized not in CANONICAL_STATES:
        return None, source_field, f"unrecognized {source_field} value: {raw!r}"
    return normalized, source_field, None


def build(run_dir: Path, bundle_dir: Path = None) -> dict:
    run_json = {}
    rj = run_dir / "run.json"
    if rj.is_file():
        run_json = json.loads(rj.read_text(encoding="utf-8"))

    # Authoritative required-node set, when available: node-state's own
    # `required` flag is nothing run.md ever mandates writing (neither real
    # run fixture in this repo carries it), which made allRequiredTerminalOk
    # vacuously true -- an empty `all()` is trivially True. Cross-referencing
    # the bundle's own contract.bundle.json.nodes[].required is authoritative
    # and doesn't depend on the orchestrator remembering to stamp a flag.
    required_from_bundle = None
    if bundle_dir is not None:
        bundle_path = Path(bundle_dir) / "contract.bundle.json"
        if bundle_path.is_file():
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            required_from_bundle = {n["nodeId"] for n in bundle.get("nodes", []) if n.get("required")}

    raw_nodes = []
    ns_dir = run_dir / "node-state"
    if ns_dir.is_dir():
        for f in sorted(ns_dir.glob("*.json")):
            try:
                raw_nodes.append(json.loads(f.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                raw_nodes.append({"nodeId": f.stem, "_unreadable": str(exc)})

    nodes = []
    states = {}
    validation_errors = []
    total_attempts = 0
    required_considered = 0

    for n in raw_nodes:
        node_id = n.get("nodeId", "unknown")
        if "_unreadable" in n:
            validation_errors.append({"nodeId": node_id, "sourceField": None,
                                       "error": f"invalid JSON: {n['_unreadable']}"})
            nodes.append({"nodeId": node_id, "normalizedState": None, "stateSourceField": None})
            continue

        normalized, source_field, err = normalize_node_state(n)
        node_record = dict(n)
        node_record["normalizedState"] = normalized
        node_record["stateSourceField"] = source_field
        nodes.append(node_record)

        if err:
            validation_errors.append({"nodeId": node_id, "sourceField": source_field, "error": err,
                                       "raw": n.get(source_field) if source_field else None})
        else:
            states[normalized] = states.get(normalized, 0) + 1

        total_attempts += int(n.get("attempts", 0) or 0)
        if required_from_bundle is None and n.get("required"):
            required_considered += 1

    missing_required = []
    if required_from_bundle is not None:
        present_by_id = {n.get("nodeId"): n for n in nodes}
        missing_required = sorted(required_from_bundle - set(present_by_id))
        required_considered = len(required_from_bundle)
        all_required_ok = not missing_required and all(
            present_by_id[nid].get("normalizedState") in TERMINAL_OK
            for nid in required_from_bundle if nid in present_by_id
        )
    else:
        all_required_ok = all(
            n.get("normalizedState") in TERMINAL_OK
            for n in nodes if n.get("required")
        )

    return {
        "documentType": "ContractGraphRunTrace",
        "runId": run_json.get("runId"),
        "bundleId": run_json.get("bundleId"),
        "generatedBy": "generate_trace.py",
        "nodes": sorted(nodes, key=lambda n: n.get("nodeId", "")),
        "validationErrors": validation_errors,
        "summary": {
            "nodeCount": len(nodes),
            "byState": dict(sorted(states.items())),
            "totalAttempts": total_attempts,
            "requiredNodesConsidered": required_considered,
            "requiredNodesSource": "bundle" if required_from_bundle is not None else "node-state.required",
            "missingRequiredNodes": missing_required,
            "allRequiredTerminalOk": all_required_ok,
            "invalidRecordCount": len(validation_errors),
        },
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    run_dir, out, bundle_dir = None, None, None
    i = 0
    while i < len(argv):
        if argv[i] == "--run":
            run_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--out":
            out = Path(argv[i + 1]); i += 2
        elif argv[i] == "--bundle":
            bundle_dir = Path(argv[i + 1]); i += 2
        else:
            i += 1
    if not run_dir or not run_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"run dir not found: {run_dir}"}), file=sys.stderr)
        return 2
    trace = build(run_dir, bundle_dir)
    out = out or (run_dir / "final" / "trace.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": out.as_posix(), "summary": trace["summary"],
                       "validationErrors": trace["validationErrors"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
