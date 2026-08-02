#!/usr/bin/env python3
"""validate_node_output - structurally validate one node's output against its
exact node contract (via jsonschema_lite), resolving local $refs to common.schema.

Also confirms the output's nodeId matches the expected node. This is the FIRST
gate in the node lifecycle (STRUCTURAL_PASSED / STRUCTURAL_FAILED); semantic and
evidence verification happen separately, by a different agent.

Usage:
  python scripts/validate_node_output.py <node-output.json> --bundle <dir> [--node <id>]
Output: JSON {ok, nodeId, errorCount, errors:[{path,message}]}. Exit 0 ok, 1 invalid, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema_lite import validate_instance


def _die(msg, code=2):
    print(json.dumps({"ok": False, "error": msg}), file=sys.stderr)
    return code


def run(output_path: Path, bundle_dir: Path, node_hint=None) -> dict:
    output = json.loads(output_path.read_text(encoding="utf-8"))
    bundle = json.loads((bundle_dir / "contract.bundle.json").read_text(encoding="utf-8"))
    node_id = node_hint or output.get("nodeId")
    if not node_id:
        return {"ok": False, "error": "cannot determine nodeId (no --node and no nodeId in output)"}
    entry = next((n for n in bundle.get("nodes", []) if n["nodeId"] == node_id), None)
    if entry is None:
        return {"ok": False, "error": f"nodeId '{node_id}' not in bundle"}
    contract_path = bundle_dir / entry["contract"]

    errors = validate_instance(output, contract_path)
    if output.get("nodeId") not in (None, node_id):
        errors.insert(0, {"path": "$.nodeId", "message": f"output nodeId '{output.get('nodeId')}' != expected '{node_id}'"})
    return {"ok": not errors, "nodeId": node_id, "contract": entry["contract"],
            "errorCount": len(errors), "errors": errors}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _die("usage: validate_node_output.py <node-output.json> --bundle <dir> [--node <id>]")
    output_path = Path(argv[0])
    bundle_dir = Path("contracts/study-plan")
    node_hint = None
    i = 1
    while i < len(argv):
        if argv[i] == "--bundle":
            bundle_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--node":
            node_hint = argv[i + 1]; i += 2
        else:
            i += 1
    if not output_path.is_file():
        return _die(f"node output not found: {output_path}")
    try:
        report = run(output_path, bundle_dir, node_hint)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        return _die(str(exc))
    print(json.dumps(report, indent=2))
    if not report.get("ok") and "error" in report:
        return 2
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
