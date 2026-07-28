#!/usr/bin/env python3
"""schedule_plan - weighted, quota-aware concurrency admission.

Given a list of pending work items and the caps for a given mode
(policies.json execution.concurrency.modes), admits as many items per
concurrency CLASS as fit under that class's cap -- replacing a single flat
"N active nodes" integer with per-class quotas so --time-bounded can raise
light-synthesis/verifier throughput without ever bursting heavy web research.
heavyResearch is capped at <=2 in every shipped mode (see policies.json); this
script enforces whatever cap the policy states, it does not hardcode the
safety floor itself -- policy authors must not raise it past 2.

For PRODUCER nodes, class is resolved from the compiled agent-manifest's tools
(WebSearch/WebFetch present -> heavyResearch, else lightSynthesis) via the same
_concurrency_class() build_node_packets.py uses, so packet and scheduler agree.
verifier/globalVerifier are not bundle nodes (they're the reusable
section-verifier/global-verifier subagents) -- callers pass that class
explicitly for verification-pass scheduling.

Usage:
  python scripts/schedule_plan.py --bundle <dir> [--compiled runtime/compiled]
      --mode default|tokenEfficient|timeBounded --ready <ready.json>
  <ready.json>: [{"id": "python", "class": "heavyResearch"}, ...] or a bare
  list of bundle node ids (auto-classified via agent-manifest).
Output: JSON {mode, caps, admitted, deferred, byClass}. Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from build_node_packets import _concurrency_class


def _load(p):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def classify_ready(ready_items, agent_by_node) -> list:
    classified = []
    for item in ready_items:
        if isinstance(item, str):
            item = {"id": item}
        cls = item.get("class")
        if not cls:
            agent = agent_by_node.get(item["id"], {})
            cls = _concurrency_class(item["id"], agent)
        classified.append({"id": item["id"], "class": cls})
    return classified


def admit(classified_items: list, caps: dict) -> dict:
    by_class = {}
    for item in classified_items:
        by_class.setdefault(item["class"], []).append(item["id"])
    admitted, deferred = [], []
    for cls, ids in by_class.items():
        cap = caps.get(cls, len(ids))
        admitted.extend(ids[:cap])
        deferred.extend(ids[cap:])
    return {
        "admitted": sorted(admitted),
        "deferred": sorted(deferred),
        "byClass": {c: sorted(ids) for c, ids in sorted(by_class.items())},
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--bundle": "contracts/company-research", "--compiled": "runtime/compiled",
            "--mode": "default", "--ready": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--ready"]:
        print("usage: schedule_plan.py --bundle <dir> [--compiled DIR] --mode <mode> --ready <ready.json>",
              file=sys.stderr)
        return 2
    bundle_dir = Path(opts["--bundle"])
    policies = _load(bundle_dir / "policies.json") or {}
    caps = policies.get("execution", {}).get("concurrency", {}).get("modes", {}).get(opts["--mode"])
    if caps is None:
        print(json.dumps({"ok": False, "error": f"no concurrency caps defined for mode '{opts['--mode']}'"}),
              file=sys.stderr)
        return 2
    agents = _load(Path(opts["--compiled"]) / "agent-manifest.json") or {"agents": []}
    agent_by_node = {a["nodeId"]: a for a in agents.get("agents", [])}
    try:
        ready_items = json.loads(Path(opts["--ready"]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    classified = classify_ready(ready_items, agent_by_node)
    result = admit(classified, caps)
    print(json.dumps({"ok": True, "mode": opts["--mode"], "caps": caps, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
