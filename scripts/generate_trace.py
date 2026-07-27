#!/usr/bin/env python3
"""generate_trace - assemble a run trace from per-node state files.

Reads runtime/runs/<run-id>/node-state/*.json (each a record written by the run
command: nodeId, state, attempts, model, cacheKey, timings, verifier verdicts)
plus run.json, and emits a single trace.json: the ordered node timeline and a
summary (accepted / exhausted / cached / failed counts). Deterministic; no model.

Usage:  python scripts/generate_trace.py --run <run-dir> [--out <path>]
        default out: <run-dir>/final/trace.json
Output: JSON summary. Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TERMINAL_OK = {"ACCEPTED", "SKIPPED_CACHE"}


def build(run_dir: Path) -> dict:
    run_json = {}
    rj = run_dir / "run.json"
    if rj.is_file():
        run_json = json.loads(rj.read_text(encoding="utf-8"))
    nodes = []
    ns_dir = run_dir / "node-state"
    if ns_dir.is_dir():
        for f in sorted(ns_dir.glob("*.json")):
            try:
                nodes.append(json.loads(f.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                nodes.append({"nodeId": f.stem, "state": "UNREADABLE"})
    states = {}
    total_attempts = 0
    for n in nodes:
        states[n.get("state", "UNKNOWN")] = states.get(n.get("state", "UNKNOWN"), 0) + 1
        total_attempts += int(n.get("attempts", 0) or 0)
    return {
        "documentType": "ContractGraphRunTrace",
        "runId": run_json.get("runId"),
        "bundleId": run_json.get("bundleId"),
        "generatedBy": "generate_trace.py",
        "nodes": sorted(nodes, key=lambda n: n.get("nodeId", "")),
        "summary": {
            "nodeCount": len(nodes),
            "byState": dict(sorted(states.items())),
            "totalAttempts": total_attempts,
            "allRequiredTerminalOk": all(n.get("state") in TERMINAL_OK for n in nodes if n.get("required")),
        },
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    run_dir, out = None, None
    i = 0
    while i < len(argv):
        if argv[i] == "--run":
            run_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--out":
            out = Path(argv[i + 1]); i += 2
        else:
            i += 1
    if not run_dir or not run_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"run dir not found: {run_dir}"}), file=sys.stderr)
        return 2
    trace = build(run_dir)
    out = out or (run_dir / "final" / "trace.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": out.as_posix(), "summary": trace["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
