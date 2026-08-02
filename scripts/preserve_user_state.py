#!/usr/bin/env python3
"""preserve_user_state - during a refresh, keep user-maintained tracking state
that research must never overwrite.

Research owns fields like titles/patterns/resource links; the user owns fields
like masteryStatus/confidence/lastPracticedDate/userNotes/bookmarked (see the
bundle's stateOwnership.userOwnedFields). When a node is refreshed, we take the
NEW research output but carry forward the OLD non-empty user-owned values,
aligning list items by their canonical key (globalProblemId / globalTopicId).

Usage:
  python scripts/preserve_user_state.py --old <prev.json> --new <fresh.json>
      --bundle <dir> --out <merged.json>
Output: JSON summary. Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CANONICAL_KEYS = ("globalProblemId", "globalTopicId", "canonicalKey", "id")


def _empty(v):
    return v in (None, "", [], {}, 0, False)


def _canon(item):
    if isinstance(item, dict):
        for k in CANONICAL_KEYS:
            if item.get(k):
                return (k, item[k])
    return None


def preserve(old, new, user_fields):
    """Return new with old's non-empty user-owned values carried forward."""
    if isinstance(new, dict) and isinstance(old, dict):
        out = {}
        for k, v in new.items():
            if k in user_fields and k in old and not _empty(old[k]):
                out[k] = old[k]                      # carry forward user value
            else:
                out[k] = preserve(old.get(k), v, user_fields)
        return out
    if isinstance(new, list) and isinstance(old, list):
        old_index = {}
        for it in old:
            c = _canon(it)
            if c:
                old_index[c] = it
        merged = []
        for it in new:
            c = _canon(it)
            merged.append(preserve(old_index[c], it, user_fields) if c in old_index else it)
        return merged
    return new


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--old": None, "--new": None, "--bundle": "contracts/study-plan", "--out": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not all((opts["--old"], opts["--new"], opts["--out"])):
        print("usage: preserve_user_state.py --old <prev> --new <fresh> --bundle <dir> --out <merged>", file=sys.stderr)
        return 2
    try:
        old = json.loads(Path(opts["--old"]).read_text(encoding="utf-8"))
        new = json.loads(Path(opts["--new"]).read_text(encoding="utf-8"))
        bundle = json.loads((Path(opts["--bundle"]) / "contract.bundle.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    user_fields = set(bundle.get("stateOwnership", {}).get("userOwnedFields", []))
    merged = preserve(old, new, user_fields)
    Path(opts["--out"]).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": opts["--out"], "userOwnedFields": sorted(user_fields)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
