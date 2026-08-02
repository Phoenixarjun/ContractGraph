#!/usr/bin/env python3
"""validate_final_output - structurally validate the aggregated final artifact
against the bundle's main contract (contract.schema.json), via jsonschema_lite.

Runs after deterministic aggregation, before global (Opus) verification.

Usage:  python scripts/validate_final_output.py <final.json> --bundle <dir>
Output: JSON {ok, errorCount, errors:[{path,message}]}. Exit 0 ok, 1 invalid, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema_lite import validate_instance


def _scope_errors(bundle: dict, final: dict) -> list:
    """A bundle's declared scope.outOfScope topics must all be named in the
    final artifact's human-readable scopeDisclaimer -- schema validation alone
    can't check that the disclaimer TEXT actually mentions every excluded
    topic, so this is a deterministic string-containment check, not a
    judgment call."""
    out_of_scope = (bundle.get("scope") or {}).get("outOfScope") or []
    if not out_of_scope:
        return []
    disclaimer = ((final.get("studyPlanMeta") or {}).get("scopeDisclaimer") or "")
    low = disclaimer.lower()
    errors = []
    for entry in out_of_scope:
        topic = entry.get("topic", "")
        if topic and topic.lower() not in low:
            errors.append({"path": "$.studyPlanMeta.scopeDisclaimer",
                            "message": f"scopeDisclaimer does not name out-of-scope topic {topic!r}"})
    return errors


def run(final_path: Path, bundle_dir: Path) -> dict:
    bundle = json.loads((bundle_dir / "contract.bundle.json").read_text(encoding="utf-8"))
    main_contract = bundle_dir / bundle["mainContract"]
    final = json.loads(final_path.read_text(encoding="utf-8"))
    errors = validate_instance(final, main_contract)
    errors = errors + _scope_errors(bundle, final)
    return {"ok": not errors, "mainContract": bundle["mainContract"],
            "errorCount": len(errors), "errors": errors}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: validate_final_output.py <final.json> --bundle <dir>", file=sys.stderr)
        return 2
    final_path = Path(argv[0])
    bundle_dir = Path("contracts/study-plan")
    i = 1
    while i < len(argv):
        if argv[i] == "--bundle":
            bundle_dir = Path(argv[i + 1]); i += 2
        else:
            i += 1
    if not final_path.is_file():
        print(json.dumps({"ok": False, "error": f"final not found: {final_path}"}), file=sys.stderr)
        return 2
    try:
        report = run(final_path, bundle_dir)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
