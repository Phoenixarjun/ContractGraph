#!/usr/bin/env python3
"""validate_references - deterministic reference-integrity checks for a section
or the final artifact: evidenceRefs resolve to a source registry, contextRefs
resolve to the context manifest, and roleIds resolve to configured roles.

Usage:
  python scripts/validate_references.py <file.json> --bundle <dir>
      [--context-manifest runtime/compiled/context-manifest.json]
Output: JSON report. Exit 0 ok, 1 unresolved refs, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _collect(obj, key):
    """Yield every value found under `key` anywhere in a nested structure."""
    out = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == key:
                    if isinstance(v, list):
                        out.extend(v)
                    else:
                        out.append(v)
                walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)
    walk(obj)
    return out


def run(doc_path: Path, bundle_dir: Path, ctx_manifest_path: Path) -> dict:
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    bundle = json.loads((bundle_dir / "contract.bundle.json").read_text(encoding="utf-8"))
    role_ids = {r["roleId"] for r in bundle.get("roles", [])}

    # available source keys: final.sourceRegistry keys, or section.sources[].sourceRef
    source_keys = set()
    if isinstance(doc.get("sourceRegistry"), dict):
        source_keys |= set(doc["sourceRegistry"].keys())
    for s in _collect(doc, "sources"):
        if isinstance(s, dict) and s.get("sourceRef"):
            source_keys.add(s["sourceRef"])

    evidence_refs = set(_collect(doc, "evidenceRefs"))
    unresolved_evidence = sorted(r for r in evidence_refs if r not in source_keys)

    # context refs
    ctx_paths = set()
    if ctx_manifest_path.is_file():
        cm = json.loads(ctx_manifest_path.read_text(encoding="utf-8"))
        for e in cm.get("entries", []):
            ctx_paths.add(e.get("sourcePath"))
            ctx_paths.add(e.get("path"))
    referenced_ctx = set(_collect(doc, "contextRefs"))
    for ce in _collect(doc, "contextEvidence"):
        if isinstance(ce, dict):
            for k in ("contextRef", "sourcePath", "path"):
                if ce.get(k):
                    referenced_ctx.add(ce[k])
    unresolved_ctx = sorted(r for r in referenced_ctx if ctx_paths and r not in ctx_paths)

    # role ids
    referenced_roles = set(_collect(doc, "roleId")) | set(_collect(doc, "configuredRoles")) | set(_collect(doc, "targetRoles"))
    referenced_roles = {r for r in referenced_roles if isinstance(r, str)}
    unresolved_roles = sorted(r for r in referenced_roles if role_ids and r not in role_ids)

    errors = []
    if unresolved_evidence:
        errors.append(f"{len(unresolved_evidence)} unresolved evidenceRef(s)")
    if unresolved_ctx:
        errors.append(f"{len(unresolved_ctx)} unresolved contextRef(s)")
    if unresolved_roles:
        errors.append(f"{len(unresolved_roles)} unresolved roleId(s)")

    return {"ok": not errors, "file": doc_path.as_posix(),
            "unresolvedEvidenceRefs": unresolved_evidence,
            "unresolvedContextRefs": unresolved_ctx,
            "unresolvedRoleIds": unresolved_roles,
            "counts": {"sourceKeys": len(source_keys), "evidenceRefs": len(evidence_refs),
                       "contextPathsKnown": len(ctx_paths), "rolesConfigured": len(role_ids)}}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: validate_references.py <file.json> --bundle <dir> [--context-manifest PATH]", file=sys.stderr)
        return 2
    doc_path = Path(argv[0])
    bundle_dir = Path("contracts/company-research")
    ctx = Path("runtime/compiled/context-manifest.json")
    i = 1
    while i < len(argv):
        if argv[i] == "--bundle":
            bundle_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--context-manifest":
            ctx = Path(argv[i + 1]); i += 2
        else:
            i += 1
    if not doc_path.is_file():
        print(json.dumps({"ok": False, "error": f"file not found: {doc_path}"}), file=sys.stderr)
        return 2
    try:
        report = run(doc_path, bundle_dir, ctx)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
