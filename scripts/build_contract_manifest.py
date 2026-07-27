#!/usr/bin/env python3
"""build_contract_manifest - compile a contract bundle into a contract manifest
and a verified runtime graph.

The dependency graph is COMPILED from each node contract's authoritative
`x-contractgraph.dependsOn`, then VERIFIED against the hand-authored graph.yaml
(differences are recorded as conflicts, not silently accepted or blindly copied).
Execution layers are derived deterministically by longest-path levelling.

Emits (under runtime/compiled by default):
  - contract-manifest.json : node/role inventory with hashes + aggregation paths
  - graph.json             : the canonical compiled graph (nodes, deps, layers)

Usage:  python scripts/build_contract_manifest.py [bundle-dir] [--out-dir DIR]
        defaults: bundle-dir=contracts/company-research  out-dir=runtime/compiled
Output: writes both files, prints a JSON summary. Exit 0 ok, 1 compile conflict, 2 IO.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from hash_content import sha256_file, sha256_json
import yaml_lite


def _levels(deps: dict) -> dict:
    """Longest-path level per node (0 = no dependencies). Assumes acyclic."""
    memo: dict = {}

    def lvl(n, seen):
        if n in memo:
            return memo[n]
        if n in seen:
            raise ValueError(f"cycle through {n}")
        ds = deps.get(n, [])
        v = 0 if not ds else 1 + max(lvl(d, seen | {n}) for d in ds if d in deps)
        memo[n] = v
        return v

    return {n: lvl(n, set()) for n in deps}


def build(bundle_dir: Path, out_dir: Path) -> dict:
    bundle = json.loads((bundle_dir / "contract.bundle.json").read_text(encoding="utf-8"))

    nodes_out = []
    deps: dict = {}
    agg_by_node = {}
    multiplicity = {}
    for node in bundle.get("nodes", []):
        nid = node["nodeId"]
        cpath = bundle_dir / node["contract"]
        nc = json.loads(cpath.read_text(encoding="utf-8"))
        xcg = nc.get("x-contractgraph", {})
        d = list(xcg.get("dependsOn", []) or [])
        deps[nid] = d
        agg_by_node[nid] = node.get("aggregationPath") or xcg.get("aggregationPath")
        multiplicity[nid] = xcg.get("multiplicity", "single")
        nodes_out.append({
            "nodeId": nid,
            "contract": node["contract"],
            "contractHash": sha256_file(cpath),
            "aggregationPath": agg_by_node[nid],
            "dependsOn": d,
            "multiplicity": multiplicity[nid],
            "required": bool(node.get("required", False)),
            "purpose": xcg.get("purpose", ""),
        })

    # verify compiled deps against source graph.yaml
    conflicts = []
    graph_yaml = bundle_dir / "graph.yaml"
    source_deps = {}
    if graph_yaml.is_file():
        try:
            gy = yaml_lite.load_file(graph_yaml) or {}
            source_deps = {k: list(v or []) for k, v in (gy.get("dependencies") or {}).items()}
        except yaml_lite.YamlLiteError as exc:
            conflicts.append(f"graph.yaml could not be parsed: {exc}")
        for nid in deps:
            compiled = set(deps[nid])
            source = set(source_deps.get(nid, []))
            if compiled != source:
                conflicts.append({
                    "node": nid,
                    "compiledFromContract": sorted(compiled),
                    "sourceGraphYaml": sorted(source),
                })

    # dangling refs / cycle guard before levelling
    known = set(deps)
    dangling = {n: [d for d in ds if d not in known] for n, ds in deps.items()}
    dangling = {n: v for n, v in dangling.items() if v}
    try:
        levels = _levels(deps) if not dangling else {}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "dangling": dangling}

    layers = []
    if levels:
        for lv in sorted(set(levels.values())):
            layers.append({"level": lv, "nodes": sorted(n for n in levels if levels[n] == lv)})

    map_nodes = [n for n, m in multiplicity.items() if m == "map"]

    graph = {
        "documentType": "ContractGraphCompiledGraph",
        "version": "1.0.0",
        "generatedBy": "build_contract_manifest.py",
        "bundleId": bundle.get("bundleId"),
        "compiledFrom": "node-contract x-contractgraph.dependsOn, verified against graph.yaml",
        "nodes": [{"nodeId": n["nodeId"], "aggregationPath": n["aggregationPath"],
                   "dependsOn": n["dependsOn"], "multiplicity": n["multiplicity"],
                   "required": n["required"]} for n in nodes_out],
        "dependencies": deps,
        "layers": layers,
        "mapNodes": map_nodes,
        "sourceVerification": {
            "graphYamlPresent": graph_yaml.is_file(),
            "dependencyConflicts": conflicts,
            "danglingReferences": dangling,
        },
    }

    roles_out = []
    for role in bundle.get("roles", []):
        rpath = bundle_dir / role["path"]
        roles_out.append({"roleId": role["roleId"], "path": role["path"],
                          "hash": sha256_file(rpath) if rpath.is_file() else None})

    main_contract_path = bundle_dir / bundle["mainContract"]
    manifest = {
        "documentType": "ContractGraphContractManifest",
        "version": "1.0.0",
        "generatedBy": "build_contract_manifest.py",
        "bundleId": bundle.get("bundleId"),
        "bundleVersion": bundle.get("bundleVersion"),
        "mainContract": bundle["mainContract"],
        "mainContractHash": sha256_file(main_contract_path) if main_contract_path.is_file() else None,
        "nodes": nodes_out,
        "roles": roles_out,
        "aggregation": bundle.get("aggregation"),
        "globalValidation": bundle.get("globalValidation"),
    }
    manifest["manifestHash"] = sha256_json({
        "nodes": [{"nodeId": n["nodeId"], "contractHash": n["contractHash"]} for n in nodes_out],
        "roles": roles_out,
        "mainContractHash": manifest["mainContractHash"],
    })

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "contract-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out_dir / "graph.json").write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": not conflicts and not dangling,
        "outDir": out_dir.as_posix(),
        "nodes": len(nodes_out),
        "roles": len(roles_out),
        "layers": len(layers),
        "mapNodes": map_nodes,
        "manifestHash": manifest["manifestHash"],
        "dependencyConflicts": conflicts,
        "danglingReferences": dangling,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    bundle_dir = Path("contracts/company-research")
    out_dir = Path("runtime/compiled")
    i = 0
    while i < len(argv):
        if argv[i] == "--out-dir":
            out_dir = Path(argv[i + 1]); i += 2
        else:
            bundle_dir = Path(argv[i]); i += 1
    if not (bundle_dir / "contract.bundle.json").is_file():
        print(json.dumps({"ok": False, "error": f"no contract.bundle.json in {bundle_dir}"}), file=sys.stderr)
        return 2
    try:
        summary = build(bundle_dir, out_dir)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
