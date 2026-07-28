#!/usr/bin/env python3
"""validate_references - deterministic reference-integrity checks for a section
or the final artifact: evidenceRefs resolve to a source registry, contextRefs
resolve to the context manifest, and roleIds resolve to configured roles.

Two evidence shapes are recognized: the legacy embedded `sourceRegistry` /
`sources[].sourceRef` (final artifact, company-research), and the newer
`evidence: [{ref, claims}]` array against an EXTERNAL run-level registry file
(--evidence-registry; study-plan's dedup-by-registry design) -- a pre-merge
section no longer embeds full source metadata, so its refs are checked
against that external file instead of anything inline.

Usage:
  python scripts/validate_references.py <file.json> --bundle <dir>
      [--context-manifest runtime/compiled/context-manifest.json]
      [--evidence-registry runtime/runs/<run-id>/evidence/source-registry.json]
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


def run(doc_path: Path, bundle_dir: Path, ctx_manifest_path: Path, evidence_registry_path: Path = None) -> dict:
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    bundle = json.loads((bundle_dir / "contract.bundle.json").read_text(encoding="utf-8"))
    role_ids = {r["roleId"] for r in bundle.get("roles", [])}

    # available source keys: final.sourceRegistry keys, section.sources[].sourceRef
    # (legacy embedded shape), or an external run-level evidence registry file
    # (newer evidence:[{ref,claims}] shape -- nothing is embedded pre-merge).
    source_keys = set()
    if isinstance(doc.get("sourceRegistry"), dict):
        source_keys |= set(doc["sourceRegistry"].keys())
    for s in _collect(doc, "sources"):
        if isinstance(s, dict) and s.get("sourceRef"):
            source_keys.add(s["sourceRef"])
    if evidence_registry_path and evidence_registry_path.is_file():
        registry = json.loads(evidence_registry_path.read_text(encoding="utf-8"))
        source_keys |= set(registry.get("entries", {}).keys())

    evidence_refs = set(_collect(doc, "evidenceRefs"))
    for ev in _collect(doc, "evidence"):
        if isinstance(ev, dict) and ev.get("ref"):
            evidence_refs.add(ev["ref"])
    unresolved_evidence = sorted(r for r in evidence_refs if r not in source_keys)

    # context refs
    ctx_paths = set()
    if ctx_manifest_path.is_file():
        cm = json.loads(ctx_manifest_path.read_text(encoding="utf-8"))
        for e in cm.get("entries", []):
            ctx_paths.add(e.get("sourcePath"))
            ctx_paths.add(e.get("path"))
    referenced_ctx = set(_collect(doc, "contextRefs"))
    # A contextEvidence entry resolves via its concrete source path. Per
    # common.schema.json ContextEvidence, `contextRef` is a free-form label
    # (not a manifest path) paired with a resolvable `sourcePath`; only fall
    # back to the label when no sourcePath/path is present.
    for ce in _collect(doc, "contextEvidence"):
        if isinstance(ce, dict):
            ref = ce.get("sourcePath") or ce.get("path") or ce.get("contextRef")
            if ref:
                referenced_ctx.add(ref)
    unresolved_ctx = sorted(r for r in referenced_ctx if ctx_paths and r not in ctx_paths)

    # role ids. targetRoles may be a list of strings (runtime input) or of
    # objects (e.g. company-intelligence data.targetRoles); object entries carry
    # their own roleId which _collect(doc, "roleId") already captures, so filter
    # to hashable strings before set-ifying to avoid "unhashable type: dict".
    referenced_roles = {
        r for r in (_collect(doc, "roleId") + _collect(doc, "configuredRoles") + _collect(doc, "targetRoles"))
        if isinstance(r, str)
    }
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
        print("usage: validate_references.py <file.json> --bundle <dir> [--context-manifest PATH] "
              "[--evidence-registry PATH]", file=sys.stderr)
        return 2
    doc_path = Path(argv[0])
    bundle_dir = Path("contracts/company-research")
    ctx = Path("runtime/compiled/context-manifest.json")
    evidence_registry = None
    i = 1
    while i < len(argv):
        if argv[i] == "--bundle":
            bundle_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--context-manifest":
            ctx = Path(argv[i + 1]); i += 2
        elif argv[i] == "--evidence-registry":
            evidence_registry = Path(argv[i + 1]); i += 2
        else:
            i += 1
    if not doc_path.is_file():
        print(json.dumps({"ok": False, "error": f"file not found: {doc_path}"}), file=sys.stderr)
        return 2
    try:
        report = run(doc_path, bundle_dir, ctx, evidence_registry)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
