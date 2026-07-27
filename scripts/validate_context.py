#!/usr/bin/env python3
"""validate_context - deterministic checks over the canonical context tree.

Verifies that canonical context is machine-readable and well-formed enough to be
indexed by build_context_manifest. It does NOT judge content quality (that is a
semantic concern) and it never reads context/private (privacy boundary).

Checks:
  - context/ exists
  - each canonical .md file is valid UTF-8
  - any file that opens a frontmatter block ('---') also closes it (else malformed)
  - files whose frontmatter status is 'empty' are reported as warnings (unfilled)
Binary source files (e.g. resume PDFs) are recorded but not parsed.

Usage:  python scripts/validate_context.py [context-dir]   (default: context)
Output: JSON report on stdout. Exit 0 = ok, 1 = malformed files, 2 = IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}


def _parse_frontmatter(text: str):
    """Return (status, error) for a leading --- frontmatter block, if present."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            status = None
            for fl in lines[1:i]:
                key, _, val = fl.partition(":")
                if key.strip() == "status":
                    status = val.strip()
            return status, None
    return None, "frontmatter opened with '---' but never closed"


def validate_context(context_dir: Path) -> dict:
    errors: list = []
    warnings: list = []
    files: list = []

    if not context_dir.is_dir():
        return {"ok": False, "contextDir": str(context_dir),
                "errors": [f"context dir not found: {context_dir}"], "warnings": [], "files": []}

    canonical = context_dir / "canonical"
    scan_root = canonical if canonical.is_dir() else context_dir

    for path in sorted(p for p in scan_root.rglob("*") if p.is_file()):
        if "private" in path.relative_to(context_dir).parts:
            continue  # never inspect private context
        rel = path.relative_to(context_dir).as_posix()
        entry = {"path": rel, "type": "text" if path.suffix.lower() in TEXT_SUFFIXES else "binary",
                 "status": None}
        if path.name == "README.md":
            entry["type"] = "readme"
        if entry["type"] == "binary":
            files.append(entry)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{rel}: not readable as UTF-8 text: {exc}")
            entry["status"] = "unreadable"
            files.append(entry)
            continue
        status, fm_err = _parse_frontmatter(text)
        if fm_err:
            errors.append(f"{rel}: {fm_err}")
        entry["status"] = status
        if status == "empty" and entry["type"] != "readme":
            warnings.append(f"{rel}: canonical file still marked status: empty (not yet filled in)")
        files.append(entry)

    return {
        "ok": not errors,
        "contextDir": str(context_dir),
        "counts": {"files": len(files), "errors": len(errors), "warnings": len(warnings)},
        "errors": errors,
        "warnings": warnings,
        "files": files,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    context_dir = Path(argv[0]) if argv else Path("context")
    report = validate_context(context_dir)
    print(json.dumps(report, indent=2))
    if report.get("errors") and any("not found" in e for e in report["errors"]):
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
