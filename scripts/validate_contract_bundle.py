#!/usr/bin/env python3
"""validate_contract_bundle - deterministic structural + reference-integrity
validation of a ContractGraph contract bundle.

This does NOT perform JSON-Schema draft-2020 instance validation (that needs the
optional `jsonschema` package and is a run-time concern). At init time we verify
that the bundle is internally coherent:
  - contract.bundle.json exists and is valid JSON with the required wiring keys
  - the main contract and common schema files exist and parse
  - every node contract file exists, parses, and its nodeId / aggregationPath
    agree with the bundle
  - node ids and aggregation paths are unique
  - every role file exists, parses, and its roleId matches the bundle
  - every x-contractgraph.dependsOn target is a known node (no dangling refs)
  - the dependency graph is acyclic
  - every required node's aggregationPath is required by the main contract
  - node-contract files on disk that the bundle never references are flagged

Usage:  python scripts/validate_contract_bundle.py <bundle-dir>
Output: JSON report on stdout. Exit 0 = ok, 1 = validation errors, 2 = IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_json(path: Path, errors: list, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{label}: file not found: {path}")
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: invalid JSON in {path}: {exc}")
    except OSError as exc:
        errors.append(f"{label}: cannot read {path}: {exc}")
    return None


def _detect_cycle(deps: dict) -> list:
    """Return a node involved in a cycle, or [] if the graph is acyclic."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in deps}
    stack = []

    def visit(n):
        color[n] = GRAY
        stack.append(n)
        for m in deps.get(n, []):
            if m not in color:
                continue  # dangling ref handled elsewhere
            if color[m] == GRAY:
                return stack[stack.index(m):] + [m]
            if color[m] == WHITE:
                r = visit(m)
                if r:
                    return r
        color[n] = BLACK
        stack.pop()
        return []

    for n in deps:
        if color[n] == WHITE:
            r = visit(n)
            if r:
                return r
    return []


def validate_bundle(bundle_dir: Path) -> dict:
    errors: list = []
    warnings: list = []

    bundle_path = bundle_dir / "contract.bundle.json"
    bundle = _load_json(bundle_path, errors, "bundle")
    if bundle is None:
        return {"ok": False, "bundleDir": str(bundle_dir), "errors": errors, "warnings": warnings}

    for key in ("bundleId", "bundleVersion", "mainContract", "nodes"):
        if key not in bundle:
            errors.append(f"bundle: missing required key '{key}'")

    # main contract
    main_contract = None
    if "mainContract" in bundle:
        main_contract = _load_json(bundle_dir / bundle["mainContract"], errors, "mainContract")
    main_required = set(main_contract.get("required", [])) if isinstance(main_contract, dict) else set()

    # common schema (optional but referenced)
    if bundle.get("commonSchema"):
        _load_json(bundle_dir / bundle["commonSchema"], errors, "commonSchema")

    # runtime inputs sanity
    ri = bundle.get("runtimeInputs", {})
    if not ri.get("required"):
        warnings.append("bundle: runtimeInputs.required is empty or missing")

    # nodes
    nodes = bundle.get("nodes", []) or []
    node_ids: list = []
    agg_paths: list = []
    depends: dict = {}
    referenced_files = set()

    for idx, node in enumerate(nodes):
        nid = node.get("nodeId")
        if not nid:
            errors.append(f"nodes[{idx}]: missing nodeId")
            continue
        node_ids.append(nid)
        contract_rel = node.get("contract")
        if not contract_rel:
            errors.append(f"node '{nid}': missing 'contract' path")
            continue
        referenced_files.add((bundle_dir / contract_rel).resolve())
        nc = _load_json(bundle_dir / contract_rel, errors, f"node '{nid}' contract")
        if nc is None:
            continue
        # nodeId const agreement
        const_id = nc.get("properties", {}).get("nodeId", {}).get("const")
        if const_id is not None and const_id != nid:
            errors.append(f"node '{nid}': contract nodeId const '{const_id}' != bundle nodeId")
        xcg = nc.get("x-contractgraph", {})
        # aggregationPath agreement
        bundle_agg = node.get("aggregationPath")
        contract_agg = xcg.get("aggregationPath")
        if bundle_agg:
            agg_paths.append(bundle_agg)
        if bundle_agg and contract_agg and bundle_agg != contract_agg:
            errors.append(
                f"node '{nid}': aggregationPath mismatch (bundle='{bundle_agg}' contract='{contract_agg}')"
            )
        # dependencies
        depends[nid] = list(xcg.get("dependsOn", []) or [])
        # main-contract coverage for required nodes
        if node.get("required") and bundle_agg and bundle_agg not in main_required:
            errors.append(
                f"node '{nid}': required aggregationPath '{bundle_agg}' not required by main contract"
            )

    # uniqueness
    for label, seq in (("nodeId", node_ids), ("aggregationPath", agg_paths)):
        dupes = {x for x in seq if seq.count(x) > 1}
        if dupes:
            errors.append(f"duplicate {label}(s): {sorted(dupes)}")

    # dangling dependency refs
    known = set(node_ids)
    for nid, deps in depends.items():
        for d in deps:
            if d not in known:
                errors.append(f"node '{nid}': dependsOn references unknown node '{d}'")

    # cycle detection
    cycle = _detect_cycle(depends)
    if cycle:
        errors.append(f"dependency cycle detected: {' -> '.join(cycle)}")

    # roles
    for idx, role in enumerate(bundle.get("roles", []) or []):
        rid = role.get("roleId")
        rpath = role.get("path")
        if not rid or not rpath:
            errors.append(f"roles[{idx}]: missing roleId or path")
            continue
        referenced_files.add((bundle_dir / rpath).resolve())
        rc = _load_json(bundle_dir / rpath, errors, f"role '{rid}'")
        if isinstance(rc, dict) and rc.get("roleId") not in (None, rid):
            errors.append(f"role '{rid}': file roleId '{rc.get('roleId')}' != bundle roleId")

    # orphan node-contract files
    nc_dir = bundle_dir / "node-contracts"
    if nc_dir.is_dir():
        for f in sorted(nc_dir.glob("*.json")):
            if f.resolve() not in referenced_files:
                warnings.append(f"orphan node-contract file not referenced by bundle: {f.name}")

    return {
        "ok": not errors,
        "bundleDir": str(bundle_dir),
        "counts": {
            "nodes": len(node_ids),
            "roles": len(bundle.get("roles", []) or []),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python validate_contract_bundle.py <bundle-dir>", file=sys.stderr)
        return 2
    bundle_dir = Path(argv[0])
    if not bundle_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"not a directory: {bundle_dir}"}), file=sys.stderr)
        return 2
    report = validate_bundle(bundle_dir)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
