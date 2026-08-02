#!/usr/bin/env python3
"""build_opencode_session_slug - deterministic OpenCode session slug generator.

Produces a stable, human-readable session slug for a ContractGraph run node:

  cg-<runId>-<nodeId>-<purpose>-<attempt>

This ensures every producer, verifier, and repair request maps to its own
OpenCode session, enabling per-node telemetry attribution.

Purposes:
  - producer   : a node producing its section output (heavyResearch / lightSynthesis)
  - verifier   : a section-verifier checking one node's output
  - global     : the global-verifier checking the merged artifact
  - repair     : a repair pass on a node (semantic/evidence/freshness)

Usage:
  python scripts/build_opencode_session_slug.py
      --run-id <runId> --node-id <nodeId> --purpose <purpose> [--attempt <N>]
  OR (JSON input):
  python scripts/build_opencode_session_slug.py --input <request.json>

Output: JSON {slug, fullSlug, slugParts: [...]}
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

VALID_PURPOSES = {"producer", "verifier", "global", "repair"}


def _sanitize(s: str) -> str:
    """Lowercase, replace non-alphanumeric with '-', collapse runs, strip."""
    result = []
    for ch in s.lower():
        if ch.isalnum():
            result.append(ch)
        else:
            if result and result[-1] != "-":
                result.append("-")
    return "".join(result).strip("-") or "unknown"


def build(run_id: str, node_id: str, purpose: str, attempt: int = 1) -> dict:
    if purpose not in VALID_PURPOSES:
        raise ValueError(f"Invalid purpose '{purpose}'. Must be one of {sorted(VALID_PURPOSES)}")

    safe_run = _sanitize(run_id)
    safe_node = _sanitize(node_id)
    safe_purpose = _sanitize(purpose)
    safe_attempt = str(max(1, int(attempt)))

    slug = f"cg-{safe_run}-{safe_node}-{safe_purpose}-{safe_attempt}"

    # Full slug with hash suffix for uniqueness
    hash_input = f"{run_id}|{node_id}|{purpose}|{attempt}"
    short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
    full_slug = f"{slug}-{short_hash}"

    return {
        "ok": True,
        "slug": slug,
        "fullSlug": full_slug,
        "slugParts": [f"cg", safe_run, safe_node, safe_purpose, safe_attempt],
        "hash": short_hash,
        "opencode_session_label": full_slug,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--run-id": None, "--node-id": None, "--purpose": None, "--attempt": "1", "--input": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        else:
            i += 1

    if opts["--input"]:
        try:
            req = json.loads(Path(opts["--input"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 2
        run_id = req.get("runId") or req.get("run_id")
        node_id = req.get("nodeId") or req.get("node_id")
        purpose = req.get("purpose")
        attempt = req.get("attempt", 1)
    else:
        run_id = opts["--run-id"]
        node_id = opts["--node-id"]
        purpose = opts["--purpose"]
        attempt = int(opts["--attempt"])

    if not all([run_id, node_id, purpose]):
        print("usage: build_opencode_session_slug.py --run-id <id> --node-id <id> --purpose <purpose> "
              "[--attempt <N>] [--input <request.json>]", file=sys.stderr)
        return 2

    try:
        result = build(run_id, node_id, purpose, attempt)
    except (ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
