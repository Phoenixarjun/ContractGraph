#!/usr/bin/env python3
"""validate_compiled_graph - deterministic integrity checks on a compiled graph.

Validates the artifact produced by build_contract_manifest (runtime/compiled/study-plan/
graph.json): every dependency resolves to a known node, the graph is acyclic,
every node is placed in exactly one layer, and map nodes reference real nodes.
Accepts JSON (preferred) or the restricted YAML subset via yaml_lite.

Usage:  python scripts/validate_compiled_graph.py [graph-path]
        default: runtime/compiled/study-plan/graph.json
Output: JSON report on stdout. Exit 0 = ok, 1 = invalid graph, 2 = IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml_lite


def _load(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        return yaml_lite.loads(text)
    return json.loads(text)


def _detect_cycle(deps: dict) -> list:
    color = {n: 0 for n in deps}
    stack = []

    def visit(n):
        color[n] = 1
        stack.append(n)
        for m in deps.get(n, []):
            if m not in color:
                continue
            if color[m] == 1:
                return stack[stack.index(m):] + [m]
            if color[m] == 0:
                r = visit(m)
                if r:
                    return r
        color[n] = 2
        stack.pop()
        return []

    for n in deps:
        if color[n] == 0:
            r = visit(n)
            if r:
                return r
    return []


def validate_graph(graph: dict) -> dict:
    errors: list = []
    warnings: list = []

    node_ids = [n["nodeId"] if isinstance(n, dict) else n for n in (graph.get("nodes") or [])]
    known = set(node_ids)
    dupes = {x for x in node_ids if node_ids.count(x) > 1}
    if dupes:
        errors.append(f"duplicate node ids: {sorted(dupes)}")

    deps = graph.get("dependencies") or {}
    for n, ds in deps.items():
        if n not in known:
            errors.append(f"dependencies reference unknown node '{n}'")
        for d in (ds or []):
            if d not in known:
                errors.append(f"node '{n}': missing dependency '{d}' (not a known node)")

    cycle = _detect_cycle({n: list(deps.get(n, []) or []) for n in known})
    if cycle:
        errors.append(f"dependency cycle: {' -> '.join(cycle)}")

    layers = graph.get("layers") or []
    if layers:
        placed = []
        for layer in layers:
            placed.extend(layer.get("nodes", []) if isinstance(layer, dict) else layer)
        placed_set = set(placed)
        for n in known:
            if n not in placed_set:
                errors.append(f"node '{n}' is not placed in any layer")
        for n in placed:
            if placed.count(n) > 1:
                errors.append(f"node '{n}' appears in more than one layer")
            if n not in known:
                errors.append(f"layer references unknown node '{n}'")
        # a node must not share a layer with any of its dependencies
        level_of = {}
        for lv, layer in enumerate(layers):
            for n in (layer.get("nodes", []) if isinstance(layer, dict) else layer):
                level_of[n] = lv
        for n in known:
            for d in deps.get(n, []) or []:
                if d in level_of and n in level_of and level_of[d] >= level_of[n]:
                    errors.append(f"node '{n}' is not strictly after its dependency '{d}'")
    else:
        warnings.append("graph has no layers to validate")

    for mn in graph.get("mapNodes", []) or []:
        if mn not in known:
            errors.append(f"mapNodes references unknown node '{mn}'")

    sv = graph.get("sourceVerification", {})
    if sv.get("dependencyConflicts"):
        warnings.append(f"{len(sv['dependencyConflicts'])} dependency conflict(s) vs source graph.yaml")
    if sv.get("danglingReferences"):
        errors.append(f"compiled graph has dangling references: {sv['danglingReferences']}")

    return {
        "ok": not errors,
        "counts": {"nodes": len(node_ids), "layers": len(layers),
                   "errors": len(errors), "warnings": len(warnings)},
        "errors": errors,
        "warnings": warnings,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    graph_path = Path(argv[0]) if argv else Path("runtime/compiled/study-plan/graph.json")
    if not graph_path.is_file():
        print(json.dumps({"ok": False, "error": f"graph not found: {graph_path}"}), file=sys.stderr)
        return 2
    try:
        graph = _load(graph_path)
    except (OSError, json.JSONDecodeError, yaml_lite.YamlLiteError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    report = validate_graph(graph)
    report["graph"] = graph_path.as_posix()
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
