#!/usr/bin/env python3
"""merge_verified_sections - deterministically aggregate ACCEPTED node sections
into the final artifact.

Places each accepted node's `data` at its bundle aggregationPath, merges any
map node from per-item fragments, and builds a global source registry deduplicated
by canonicalUrl (else sourceRef). Deterministic: identical inputs -> byte-identical
output (sorted keys). It never calls a model; it only assembles what verification
already accepted.

Two evidence shapes feed the final registry: embedded `sources[]` (full metadata
per section) and, when --evidence-registry is given, `data.evidence: [{ref, claims}]`
resolved against that external run-level registry (study-plan's dedup-by-registry
design) -- sections in this shape never embed full source metadata, so the
external file supplies it.

Run-scoped scaffolding (run / candidateContextSnapshot / meta) is merged in from
--run-meta when provided; otherwise those keys are left for the run command to
fill. Rejects duplicate source ownership (same sourceRef, different content).

Usage:
  python scripts/merge_verified_sections.py --bundle <dir> --sections <dir>
      --out <final.json> [--run-meta <run-meta.json>]
      [--evidence-registry <run-id>/evidence/source-registry.json]
Output: JSON summary. Exit 0 ok, 1 merge conflict / missing required node, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def merge(bundle_dir: Path, sections_dir: Path, run_meta, evidence_registry=None) -> tuple:
    bundle = _load(bundle_dir / "contract.bundle.json")
    main = _load(bundle_dir / bundle["mainContract"])
    consts = {k: v.get("const") for k, v in main.get("properties", {}).items()
              if isinstance(v, dict) and "const" in v}

    final = {}
    for k, c in consts.items():
        final[k] = c  # schemaVersion, documentType, etc.

    errors, missing = [], []
    registry = {}
    conflicts = []

    def add_sources(section):
        for s in section.get("sources", []) or []:
            if not isinstance(s, dict):
                continue
            ref = s.get("sourceRef") or s.get("canonicalUrl") or s.get("url")
            if not ref:
                continue
            if ref in registry and registry[ref] != s:
                conflicts.append(ref)
            registry[ref] = s

    def add_evidence_refs(section):
        if not evidence_registry:
            return
        entries = evidence_registry.get("entries", {})
        for ev in ((section.get("data") or {}).get("evidence") or []):
            if not isinstance(ev, dict):
                continue
            ref = ev.get("ref")
            meta = entries.get(ref) if ref else None
            if meta is None:
                continue  # unresolved -- validate_references flags this separately
            if ref in registry and registry[ref] != meta:
                conflicts.append(ref)
            registry[ref] = meta

    for node in bundle.get("nodes", []):
        nid, agg = node["nodeId"], node["aggregationPath"]
        # multiplicity
        contract = _load(bundle_dir / node["contract"])
        mult = contract.get("x-contractgraph", {}).get("multiplicity", "single")
        single = sections_dir / f"{nid}.json"
        frag_dir = sections_dir / nid
        if single.is_file():
            sec = _load(single)
            final[agg] = sec.get("data", sec)
            add_sources(sec)
            add_evidence_refs(sec)
        elif frag_dir.is_dir():
            frags = [_load(f) for f in sorted(frag_dir.glob("*.json"))]
            for fr in frags:
                add_sources(fr)
                add_evidence_refs(fr)
            # map node: collect fragment data into a roleAnalyses-style list, sorted for determinism
            final[agg] = {"roleAnalyses": [fr.get("data", fr) for fr in frags]}
        else:
            if node.get("required"):
                missing.append(nid)

    if run_meta:
        for k in ("run", "studyPlanMeta", "candidateContextSnapshot", "meta"):
            if k in run_meta:
                final[k] = run_meta[k]

    final["sourceRegistry"] = dict(sorted(registry.items()))

    if missing:
        errors.append(f"missing required node section(s): {sorted(missing)}")
    if conflicts:
        errors.append(f"duplicate source ownership conflict(s): {sorted(set(conflicts))}")

    return final, {"ok": not errors, "nodesMerged": len([k for k in consts]) and None,
                   "aggregationPaths": sorted(consts.keys()),
                   "sources": len(registry), "missingRequired": sorted(missing),
                   "ownershipConflicts": sorted(set(conflicts)), "errors": errors}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--bundle": "contracts/study-plan", "--sections": None, "--out": None,
            "--run-meta": None, "--evidence-registry": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--sections"] or not opts["--out"]:
        print("usage: merge_verified_sections.py --bundle <dir> --sections <dir> --out <final.json> "
              "[--run-meta <json>] [--evidence-registry <source-registry.json>]", file=sys.stderr)
        return 2
    run_meta = _load(Path(opts["--run-meta"])) if opts["--run-meta"] else None
    evidence_registry = _load(Path(opts["--evidence-registry"])) if opts["--evidence-registry"] else None
    try:
        final, summary = merge(Path(opts["--bundle"]), Path(opts["--sections"]), run_meta, evidence_registry)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    out = Path(opts["--out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["out"] = out.as_posix()
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
