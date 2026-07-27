#!/usr/bin/env python3
"""build_context_manifest - index canonical context into a manifest.

Records, for every canonical context file, its source path, SHA-256, byte size,
type, and (for markdown) frontmatter status - plus a flag for large files that a
downstream summarization step should condense. Originals are NEVER modified or
copied; the manifest only references them by path. context/private is never read.

An overall contextManifestHash (hash of the sorted per-file hashes) is emitted so
runs can be cache-keyed and the final contract's run.contextManifestHash resolved.

Usage:  python scripts/build_context_manifest.py [context-dir] [--out PATH]
        defaults: context-dir=context  out=runtime/compiled/context-manifest.json
Output: writes the manifest, prints a JSON summary. Exit 0 ok, 2 on IO error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from hash_content import sha256_file, sha256_json

TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}
LARGE_FILE_BYTES = 16 * 1024


def _frontmatter_status(text: str):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            for fl in lines[1:i]:
                key, _, val = fl.partition(":")
                if key.strip() == "status":
                    return val.strip()
            return None
    return None


def build(context_dir: Path, out_path: Path) -> dict:
    canonical = context_dir / "canonical"
    scan_root = canonical if canonical.is_dir() else context_dir
    entries = []
    for path in sorted(p for p in scan_root.rglob("*") if p.is_file()):
        rel_parts = path.relative_to(context_dir).parts
        if "private" in rel_parts:
            continue
        if path.name == "README.md":
            continue  # scaffolding guide, not context content
        rel = path.relative_to(context_dir).as_posix()
        size = path.stat().st_size
        is_text = path.suffix.lower() in TEXT_SUFFIXES
        status = None
        if is_text:
            try:
                status = _frontmatter_status(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                status = "unreadable"
        entries.append({
            "path": rel,
            "sourcePath": f"context/{rel}",
            "sha256": sha256_file(path),
            "bytes": size,
            "type": "text" if is_text else "binary",
            "status": status,
            "needsSummary": size > LARGE_FILE_BYTES,
        })

    manifest = {
        "documentType": "ContractGraphContextManifest",
        "version": "1.0.0",
        "generatedBy": "build_context_manifest.py",
        "contextDir": context_dir.as_posix(),
        "note": "References canonical sources by path and hash. Originals are never modified. Private context is excluded.",
        "entries": entries,
    }
    manifest["contextManifestHash"] = sha256_json(
        [{"path": e["path"], "sha256": e["sha256"]} for e in entries]
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    context_dir = Path("context")
    out_path = Path("runtime/compiled/context-manifest.json")
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out_path = Path(argv[i + 1]); i += 2
        else:
            context_dir = Path(argv[i]); i += 1
    if not context_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"context dir not found: {context_dir}"}), file=sys.stderr)
        return 2
    try:
        manifest = build(context_dir, out_path)
    except OSError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({
        "ok": True,
        "out": out_path.as_posix(),
        "entries": len(manifest["entries"]),
        "contextManifestHash": manifest["contextManifestHash"],
        "needsSummary": [e["path"] for e in manifest["entries"] if e["needsSummary"]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
