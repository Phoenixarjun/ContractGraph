#!/usr/bin/env python3
"""source_registry - deterministic, incrementally-updatable global evidence
registry for a run.

Normalizes URLs (lowercase scheme/host, drop fragment, strip utm_* query
params, drop trailing slash) so the same real-world source always mints the
same SRC_<hash> id regardless of which node first cites it or what local
label it used. Full source metadata (title, url, publisher, sourceType,
publicationDate, accessDate, confidence) is stored ONCE in the registry --
the fix for the "duplicate source objects across sections, same URL
under different per-node ids" waste measured in benchmark runs.

A caller (a node producer at generation time, or a migration step) passes the
sources it wants to cite; this script returns the canonical id for each (new
or reused) so the node's own `evidence: [{ref, claims}]` array can be written
against canonical ids instead of ad hoc per-node ones.

Usage:
  python scripts/source_registry.py --registry <registry.json> --sources <sources.json>
      [--out-refmap <refmap.json>]
  <sources.json>: {"sources": [{sourceRef, title, url, ...}, ...]} or a bare array.
Output: JSON {ok, registryPath, totalEntries, added, reused, refMap}.
Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from hash_content import sha256_text


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_")]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def canonical_id(url: str) -> str:
    return f"SRC_{sha256_text(normalize_url(url)).upper()[:12]}"


def _load_registry(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"documentType": "ContractGraphSourceRegistry", "version": "1.0.0", "entries": {}}


def _load_sources(path: Path) -> list:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else raw.get("sources", [])


def merge(registry: dict, sources: list) -> tuple:
    added, reused, ref_map = [], [], {}
    for s in sources:
        url = s.get("url")
        local_ref = s.get("sourceRef")
        if not url:
            continue
        cid = canonical_id(url)
        if cid in registry["entries"]:
            reused.append(cid)
        else:
            entry = {k: v for k, v in s.items() if k != "sourceRef"}
            entry["sourceRef"] = cid
            registry["entries"][cid] = entry
            added.append(cid)
        if local_ref:
            ref_map[local_ref] = cid
    return registry, sorted(set(added)), sorted(set(reused)), ref_map


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--registry": None, "--sources": None, "--out-refmap": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--registry"] or not opts["--sources"]:
        print("usage: source_registry.py --registry <registry.json> --sources <sources.json> "
              "[--out-refmap <refmap.json>]", file=sys.stderr)
        return 2
    registry_path = Path(opts["--registry"])
    try:
        registry = _load_registry(registry_path)
        sources = _load_sources(Path(opts["--sources"]))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    registry, added, reused, ref_map = merge(registry, sources)

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    out = {"ok": True, "registryPath": registry_path.as_posix(), "totalEntries": len(registry["entries"]),
           "added": added, "reused": reused, "refMap": ref_map}
    if opts["--out-refmap"]:
        refmap_path = Path(opts["--out-refmap"])
        refmap_path.parent.mkdir(parents=True, exist_ok=True)
        refmap_path.write_text(json.dumps(ref_map, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
