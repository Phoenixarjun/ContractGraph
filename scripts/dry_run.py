#!/usr/bin/env python3
"""dry_run - produce the execution plan for a compiled workflow without running
any node. Backs `/contractgraph:run ... --dry-run`.

Reads the compiled artifacts (graph.json, agent-manifest.json, context-manifest.json,
skill-manifest.json, contract-manifest.json) plus policies.json and shows: the
layer order, parallel groups, chosen model per node, context references that would
load, skills selected per node, expected cache hits, an estimated token budget,
and the files that would be written. Deterministic; no model, no network.

Usage:
  python scripts/dry_run.py --bundle <dir> [--compiled runtime/compiled/study-plan]
      [--input <input.json>] [--cache runtime/cache]
Output: JSON plan. Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TIER_TOKENS = {"haiku": 8000, "sonnet": 25000, "opus": 40000}


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def plan(bundle_dir: Path, compiled: Path, run_input: dict, cache_dir: Path) -> dict:
    graph = _load(compiled / "graph.json")
    agents = _load(compiled / "agent-manifest.json") or {"agents": []}
    ctx = _load(compiled / "context-manifest.json") or {"entries": []}
    policies = _load(bundle_dir / "policies.json") or {}
    if graph is None:
        raise FileNotFoundError(f"no compiled graph at {compiled/'graph.json'} — run /contractgraph:init first")

    agent_by_node = {a["nodeId"]: a for a in agents["agents"]}
    layers = [{"level": L["level"], "parallelGroup": L["nodes"]} for L in graph["layers"]]

    node_plan = []
    est_tokens = 0
    for L in graph["layers"]:
        for nid in L["nodes"]:
            a = agent_by_node.get(nid, {})
            model = a.get("model", "sonnet")
            est_tokens += TIER_TOKENS.get(model, 25000)
            node_plan.append({
                "nodeId": nid, "layer": L["level"], "model": model,
                "tools": a.get("tools", []), "skills": a.get("requiredSkills", []),
                "dependsOn": graph["dependencies"].get(nid, []),
                "output": a.get("output") or f"runtime/runs/<run-id>/sections/{nid}.json",
            })

    # expected cache hits
    cache_hits = []
    if cache_dir.is_dir():
        cached = {p.stem for p in cache_dir.glob("*.json")}
        cache_hits = [n["nodeId"] for n in node_plan if n["nodeId"] in cached]

    files = ["run.json", "input.json", "graph.snapshot.yaml", "manifests/",
             "node-state/<nodeId>.json (per node)", "sections/<nodeId>.json (per accepted node)",
             "verification/<nodeId>.json (per node)", "evidence/", "logs/",
             "final/final.json", "final/report.md", "final/trace.json",
             "final/cost.json", "final/validation-report.json", "final/derived-context.json"]

    return {
        "documentType": "ContractGraphDryRun",
        "bundle": bundle_dir.as_posix(),
        "runtimeInput": run_input,
        "configuredRoles": run_input.get("targetRoles",
                            _load(bundle_dir / "contract.bundle.json").get("runtimeInputs", {}).get("defaults", {}).get("targetRoles", [])) if (bundle_dir / "contract.bundle.json").is_file() else [],
        "layerOrder": layers,
        "mapNodes": graph.get("mapNodes", []),
        "nodes": node_plan,
        "modelHistogram": _hist(node_plan),
        "contextReferences": [e.get("sourcePath") for e in ctx.get("entries", [])],
        "expectedCacheHits": cache_hits,
        "estimatedTokenBudget": est_tokens,
        "estimatedNote": "rough per-node tier estimate; excludes verification + repair passes",
        "filesThatWouldBeWritten": files,
        "globalVerification": {"model": policies.get("models", {}).get("verification", {}).get("global", "opus")},
    }


def _hist(node_plan):
    h = {}
    for n in node_plan:
        h[n["model"]] = h.get(n["model"], 0) + 1
    return dict(sorted(h.items()))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    bundle_dir = Path("contracts/study-plan")
    compiled = Path("runtime/compiled/study-plan")
    cache_dir = Path("runtime/cache")
    run_input = {}
    i = 0
    while i < len(argv):
        if argv[i] == "--bundle":
            bundle_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--compiled":
            compiled = Path(argv[i + 1]); i += 2
        elif argv[i] == "--cache":
            cache_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--input":
            run_input = json.loads(Path(argv[i + 1]).read_text(encoding="utf-8")); i += 2
        else:
            i += 1
    try:
        out = plan(bundle_dir, compiled, run_input, cache_dir)
    except (OSError, json.JSONDecodeError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
