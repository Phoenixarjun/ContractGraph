#!/usr/bin/env python3
"""build_dependency_summary - compact, cacheable handoff summary for one
accepted node, referenced by DOWNSTREAM node packets instead of the full
section (fixing the "full-prose sections passed whole to downstream nodes"
waste). Extracts the producer-authored `data.handoffSummary` block if the
node contract defines one, else derives a minimal ref-only summary -- never
copies full prose downstream either way.

summaryHash covers exactly {handoff, evidenceRefs, confidence}: unchanged
upstream output (even after re-running the same node) yields an identical
hash, so cache_key.py's depSummaryHashes fold lets downstream nodes recognize
"nothing actually changed" and skip re-execution; any real change busts it.

Usage:
  python scripts/build_dependency_summary.py --bundle <dir> --node <id>
      --section <accepted-section.json> --out <summary.json>
Output: JSON summary (also written to --out). Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from hash_content import sha256_json


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def build(bundle_dir: Path, node_id: str, section: dict, full_section_ref: str) -> dict:
    bundle = _load(bundle_dir / "contract.bundle.json")
    node = next((n for n in bundle["nodes"] if n["nodeId"] == node_id), None)
    if node is None:
        raise KeyError(f"node '{node_id}' not in bundle")

    data = section.get("data", {}) or {}
    handoff = data.get("handoffSummary")
    if handoff is None:
        handoff = {"nodeId": node_id, "status": section.get("status"), "derived": True}

    evidence_refs = sorted({
        e.get("ref") for e in (data.get("evidence") or [])
        if isinstance(e, dict) and e.get("ref")
    })
    confidence = None
    ver = section.get("verification", {}) or {}
    if isinstance(ver.get("confidence"), (int, float)):
        confidence = ver["confidence"]

    summary_hash = sha256_json({"handoff": handoff, "evidenceRefs": evidence_refs, "confidence": confidence})
    return {
        "documentType": "ContractGraphDependencySummary",
        "nodeId": node_id,
        "aggregationPath": node["aggregationPath"],
        "contractVersion": section.get("contractVersion"),
        "summaryHash": summary_hash,
        "handoff": handoff,
        "evidenceRefs": evidence_refs,
        "confidence": confidence,
        "fullSectionRef": full_section_ref,
        "producedAt": None,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--bundle": "contracts/study-plan", "--node": None, "--section": None, "--out": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--node"] or not opts["--section"] or not opts["--out"]:
        print("usage: build_dependency_summary.py --bundle <dir> --node <id> "
              "--section <section.json> --out <summary.json>", file=sys.stderr)
        return 2
    try:
        section = _load(opts["--section"])
        summary = build(Path(opts["--bundle"]), opts["--node"], section,
                         full_section_ref=f"sections/{opts['--node']}.json")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    out_path = Path(opts["--out"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
