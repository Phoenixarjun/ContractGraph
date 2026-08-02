#!/usr/bin/env python3
"""cache_key - compute a deterministic cache key for one node in a run.

Per CLAUDE.md the key must fold in everything that could change the node's valid
output: bundle version, node contract hash, relevant canonical-context hashes,
runtime input, configured role set, skill versions, agent version, freshness
policy, and node implementation version. Same inputs -> same key; any change ->
new key (selective refresh).

Also folds --dep-summaries (a {depNode: summaryHash} map from
build_dependency_summary.py) and --node-packet (a compiled node-packets/<id>/
packet.json from build_node_packets.py, keyed by its packetHash): unchanged
upstream summaries and an unchanged packet keep the key stable; either
changing busts it, so downstream nodes correctly re-run only when something
that could affect their output actually changed.

Usage:
  python scripts/cache_key.py --bundle <dir> --node <id> --input <input.json>
      [--context-manifest runtime/compiled/study-plan/context-manifest.json]
      [--agent-manifest runtime/compiled/study-plan/agent-manifest.json]
      [--skill-manifest runtime/compiled/study-plan/skill-manifest.json]
      [--dep-summaries <depNode-to-summaryHash.json>]
      [--node-packet <node-packets/<id>/packet.json>]
Output: JSON {cacheKey, components}. Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from hash_content import sha256_file, sha256_json


def _load(p):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def build(bundle_dir: Path, node_id: str, run_input: dict,
          ctx_manifest, agent_manifest, skill_manifest,
          dep_summary_hashes=None, node_packet_hash=None) -> dict:
    bundle = _load(bundle_dir / "contract.bundle.json")
    node = next((n for n in bundle["nodes"] if n["nodeId"] == node_id), None)
    if node is None:
        raise KeyError(f"node '{node_id}' not in bundle")
    policies = _load(bundle_dir / "policies.json") or {}

    components = {
        "bundleVersion": bundle.get("bundleVersion"),
        "nodeContractHash": sha256_file(bundle_dir / node["contract"]),
        "runtimeInput": {k: run_input.get(k) for k in sorted(run_input)},
        "configuredRoles": sorted(run_input.get("targetRoles",
                                  bundle.get("runtimeInputs", {}).get("defaults", {}).get("targetRoles", []))),
        "freshnessPolicy": policies.get("freshnessDays", {}),
        "nodeImplVersion": "1.0.0",
    }
    # relevant context hashes (all canonical, for now; a finer node->context map can narrow this)
    if ctx_manifest:
        components["contextHashes"] = {e["path"]: e["sha256"] for e in ctx_manifest.get("entries", [])}
    # skill + agent versions
    if skill_manifest:
        boot = {s["skillId"]: s.get("contentHash") for s in skill_manifest.get("registry", {}).get("bootstrap", [])}
        reuse = {s["skillId"]: s.get("contentHash") for s in skill_manifest.get("registry", {}).get("reusable", [])}
        components["skillVersions"] = {**boot, **reuse}
    if agent_manifest:
        a = next((x for x in agent_manifest.get("agents", []) if x["nodeId"] == node_id), None)
        if a:
            components["agentVersion"] = sha256_json(a)
    if dep_summary_hashes:
        components["depSummaryHashes"] = dict(sorted(dep_summary_hashes.items()))
    if node_packet_hash:
        components["nodePacketHash"] = node_packet_hash

    return {"nodeId": node_id, "cacheKey": sha256_json(components), "components": components}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--bundle": "contracts/study-plan", "--node": None, "--input": None,
            "--context-manifest": "runtime/compiled/study-plan/context-manifest.json",
            "--agent-manifest": "runtime/compiled/study-plan/agent-manifest.json",
            "--skill-manifest": "runtime/compiled/study-plan/skill-manifest.json",
            "--dep-summaries": None, "--node-packet": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--node"]:
        print("usage: cache_key.py --bundle <dir> --node <id> --input <input.json>", file=sys.stderr)
        return 2
    run_input = {}
    if opts["--input"]:
        run_input = json.loads(Path(opts["--input"]).read_text(encoding="utf-8"))
    dep_summary_hashes = _load(opts["--dep-summaries"]) if opts["--dep-summaries"] else None
    node_packet_hash = None
    if opts["--node-packet"]:
        packet = _load(opts["--node-packet"])
        node_packet_hash = packet.get("packetHash") if packet else None
    try:
        out = build(Path(opts["--bundle"]), opts["--node"], run_input,
                    _load(opts["--context-manifest"]), _load(opts["--agent-manifest"]),
                    _load(opts["--skill-manifest"]),
                    dep_summary_hashes=dep_summary_hashes, node_packet_hash=node_packet_hash)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
