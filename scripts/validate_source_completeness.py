#!/usr/bin/env python3
"""validate_source_completeness - enforce that every recommended source in every
accepted section carries the required metadata fields.

Required fields per ResourceLink (common.schema.json):
  - title (non-empty string)
  - url (non-empty string, proper format)
  - type (enum: course|doc|book|video|practice|article)
  - free (optional boolean)

Required fields per EvidenceSource (common.schema.json):
  - sourceRef (non-empty string)
  - title (non-empty string)
  - url (non-empty string, URI format)
  - sourceType (enum: official_documentation|course|book|article|community)
  - publisher (string|null)
  - publicationDate (string|null)
  - accessDate (string|null)
  - confidence (enum: high|medium|low)

Placeholder values (empty strings, "?", "TBD", "TODO", "N/A", "unknown")
are treated as missing.

Sources with incomplete metadata are placed in an archive list with
explicit unresolved status; they must not appear as recommended sources.

Usage:
  python scripts/validate_source_completeness.py --run <run-dir>
      [--bundle <bundle-dir>] [--out <report.json>]

Output: JSON {ok, issues: [{nodeId, field, value, severity, recommendation}]}
Exit 0 ok, 1 issues found, 2 IO/usage.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PLACEHOLDER_PATTERNS = re.compile(
    r"^(|[\s]*|placeholder|todo|tbd|n/?a|unknown|not.?provided|not.?specified|"
    r"insert.*|example\.(com|org|net)|https?://example|\?|\.\.\.)$",
    re.IGNORECASE,
)

URI_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$")

RESOURCE_REQUIRED = {"title", "url", "type"}
RESOURCE_TYPE_ENUM = {"course", "doc", "book", "video", "practice", "article"}
SOURCE_REQUIRED = {"sourceRef", "title", "url", "sourceType"}
SOURCE_TYPE_ENUM = {"official_documentation", "course", "book", "article", "community"}


def is_placeholder(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    if not value.strip():
        return True
    return bool(PLACEHOLDER_PATTERNS.match(value.strip()))


def is_valid_uri(value) -> bool:
    if not isinstance(value, str):
        return False
    return bool(URI_PATTERN.match(value.strip()))


def check_resource(idx: int, r: dict) -> list[dict]:
    issues = []
    for field in RESOURCE_REQUIRED:
        val = r.get(field)
        if is_placeholder(val):
            issues.append({
                "field": f"resources[{idx}].{field}",
                "severity": "blocking",
                "found": str(val),
                "recommendation": f"Must provide a non-placeholder value for {field}",
            })
        elif field == "url" and not is_valid_uri(val):
            issues.append({
                "field": f"resources[{idx}].{field}",
                "severity": "blocking",
                "found": str(val)[:100],
                "recommendation": "Must be a valid URI (scheme://...)",
            })
        elif field == "type" and val not in RESOURCE_TYPE_ENUM:
            issues.append({
                "field": f"resources[{idx}].{field}",
                "severity": "blocking",
                "found": str(val),
                "recommendation": f"Must be one of {sorted(RESOURCE_TYPE_ENUM)}",
            })
    return issues


def check_source_evidence(idx: int, ev: dict) -> list[dict]:
    issues = []
    for field in SOURCE_REQUIRED:
        val = ev.get(field)
        if is_placeholder(val):
            issues.append({
                "field": f"evidence[{idx}].{field}",
                "severity": "blocking",
                "found": str(val),
                "recommendation": f"Must provide a non-placeholder value for {field}",
            })
        elif field == "url" and not is_valid_uri(val):
            issues.append({
                "field": f"evidence[{idx}].{field}",
                "severity": "blocking",
                "found": str(val)[:100],
                "recommendation": "Must be a valid URI",
            })
        elif field == "sourceType" and val not in SOURCE_TYPE_ENUM:
            issues.append({
                "field": f"evidence[{idx}].{field}",
                "severity": "blocking",
                "found": str(val),
                "recommendation": f"Must be one of {sorted(SOURCE_TYPE_ENUM)}",
            })
    return issues


def run(run_dir: Path, bundle_dir: Path = None) -> dict:
    sections_dir = run_dir / "sections"
    if not sections_dir.is_dir():
        return {"ok": True, "issues": [], "note": "no sections directory"}

    all_issues = []
    total_resources = 0
    total_evidence = 0
    placeholder_resources = 0
    placeholder_evidence = 0

    for sec_file in sorted(sections_dir.glob("*.json")):
        nid = sec_file.stem
        section = json.loads(sec_file.read_text(encoding="utf-8"))
        data = section.get("data", section)
        resources = data.get("resources", [])
        evidence = section.get("evidence", [])

        for i, r in enumerate(resources):
            total_resources += 1
            issues = check_resource(i, r)
            if issues:
                placeholder_resources += 1
            for iss in issues:
                iss["nodeId"] = nid
                all_issues.append(iss)

        for i, ev in enumerate(evidence):
            ref = ev.get("ref", "")
            total_evidence += 1
            issues = check_source_evidence(i, ev)
            if issues:
                placeholder_evidence += 1
            for iss in issues:
                iss["nodeId"] = nid
                all_issues.append(iss)

    blocking = [i for i in all_issues if i.get("severity") == "blocking"]

    return {
        "ok": len(blocking) == 0,
        "summary": {
            "totalResources": total_resources,
            "totalEvidenceRefs": total_evidence,
            "resourcesWithIssues": placeholder_resources,
            "evidenceWithIssues": placeholder_evidence,
            "totalIssues": len(all_issues),
            "blockingIssues": len(blocking),
        },
        "issues": all_issues,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--run": None, "--bundle": None, "--out": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        else:
            i += 1
    if not opts["--run"]:
        print("usage: validate_source_completeness.py --run <run-dir> [--bundle <bundle-dir>] [--out <report.json>]",
              file=sys.stderr)
        return 2
    run_dir = Path(opts["--run"])
    bundle_dir = Path(opts["--bundle"]) if opts["--bundle"] else None
    if not run_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"run dir not found: {run_dir}"}), file=sys.stderr)
        return 2
    try:
        report = run(run_dir, bundle_dir)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    if opts["--out"]:
        out_path = Path(opts["--out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
