#!/usr/bin/env python3
"""hash_content - deterministic SHA-256 hashing for files, text, and JSON.

Local-only, stdlib-only. Used by the manifest builders so context and contract
content can be cache-keyed and provenance-tracked. No network, no mutation.

CLI:
  python scripts/hash_content.py <path> [<path> ...]   # hash files
  python scripts/hash_content.py --text "some string"  # hash a literal
Prints a JSON object {path/text: sha256}. Exit 0 on success, 2 on IO error.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj) -> str:
    """Hash a JSON-serialisable object canonically (sorted keys, compact)."""
    return sha256_text(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python hash_content.py <path>... | --text <string>", file=sys.stderr)
        return 2
    out = {}
    if argv[0] == "--text":
        text = " ".join(argv[1:])
        out["text"] = sha256_text(text)
        print(json.dumps(out, indent=2))
        return 0
    rc = 0
    for p in argv:
        try:
            out[p] = sha256_file(Path(p))
        except OSError as exc:
            out[p] = None
            print(f"error hashing {p}: {exc}", file=sys.stderr)
            rc = 2
    print(json.dumps(out, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
