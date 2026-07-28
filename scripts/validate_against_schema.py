#!/usr/bin/env python3
"""validate_against_schema - generic JSON-Schema instance validator: a thin CLI
wrapper over jsonschema_lite for the ad hoc schemas under scripts/schemas/
(cost, node-packet, dependency-summary, verifier-verdict) that don't warrant a
bespoke validate_*.py of their own.

Usage:
  python scripts/validate_against_schema.py <instance.json> --schema <schema.json>
Output: JSON {ok, errorCount, errors}. Exit 0 valid, 1 invalid, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jsonschema_lite import validate_instance  # noqa: E402


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or "--schema" not in argv:
        print("usage: validate_against_schema.py <instance.json> --schema <schema.json>", file=sys.stderr)
        return 2
    instance_path = Path(argv[0])
    schema_path = Path(argv[argv.index("--schema") + 1])
    try:
        instance = json.loads(instance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    errors = validate_instance(instance, schema_path)
    out = {"ok": not errors, "errorCount": len(errors), "errors": errors}
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
