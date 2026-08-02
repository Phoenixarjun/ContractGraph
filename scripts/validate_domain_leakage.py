#!/usr/bin/env python3
"""validate_domain_leakage - contract-aware scan that detects evidence or
recommendations unrelated to the current workflow domain.

Compares the content of each accepted section against the domain keyword sets
**declared by the bundle itself** in `policies.json` -> `domainLeakage`. No
domain vocabulary lives in this script: a bundle that declares no policy is
reported as unchecked, never silently passed.

`policies.json`:

  "domainLeakage": {
    "allowedUnconditional": ["term", ...],          # expected in this domain
    "allowedWithLabel": {"term": "why it needs a label", ...},
    "disallowed": {"term": "why it may never appear", ...},
    "exemptNodes": {"<nodeId>": ["term", ...]}      # nodes that compare on purpose
  }

Severity: `disallowed` hits are blocking; unlabelled `allowedWithLabel` hits are
warnings. `allowedUnconditional` is declarative — it documents the in-domain
vocabulary and is never flagged.

Usage:
  python scripts/validate_domain_leakage.py --run <run-dir> --bundle <bundle-dir>
      [--out <report.json>]

Output: JSON {ok, issues: [{nodeId, term, location, severity, context}]}
Exit 0 ok (no blocking issues), 1 issues found, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

COMPARISON_TRIGGERS = {
    "vs", "comparison", "versus", "alternative", "alternatively",
    "alongside", "including but not limited to", "including", "e.g.", "i.e.",
    "for example", "such as", "or ", "like ", "unlike ",
    "in contrast", "as opposed to", "rather than", "instead of",
}


def load_domain_policy(bundle_dir: Path) -> dict | None:
    """Read the bundle's declared domainLeakage policy, or None if it declares none."""
    policies_path = bundle_dir / "policies.json"
    if not policies_path.is_file():
        return None
    policy = json.loads(policies_path.read_text(encoding="utf-8")).get("domainLeakage")
    if not isinstance(policy, dict):
        return None
    return {
        "allowed_unconditional": set(policy.get("allowedUnconditional", []) or []),
        "allowed_with_label": dict(policy.get("allowedWithLabel", {}) or {}),
        "disallowed": dict(policy.get("disallowed", {}) or {}),
        "exempt_nodes": {k: set(v or []) for k, v in (policy.get("exemptNodes", {}) or {}).items()},
    }


def check_section_text(section_path: Path, domain_map: dict | None, nid: str) -> list[dict]:
    """Check one section file for domain leakage against a loaded domain policy."""
    if not domain_map:
        return []

    text = section_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    lower_text = text.lower()

    exempt_terms = domain_map.get("exempt_nodes", {}).get(nid, set())

    issues = []

    # Check disallowed terms (always blocking)
    for term in domain_map.get("disallowed", {}):
        if term.lower() in lower_text:
            for lineno, line in enumerate(lines, 1):
                if term.lower() in line.lower():
                    issues.append({
                        "nodeId": nid,
                        "term": term,
                        "location": f"{section_path.name}:{lineno}",
                        "severity": "blocking",
                        "context": line.strip()[:200],
                        "recommendation": f"Remove reference to '{term}' — outside workflow domain",
                    })

    # Check allowed_with_label terms (need comparison context)
    for term, reason in domain_map.get("allowed_with_label", {}).items():
        if term.lower() in lower_text:
            if term.lower() in {t.lower() for t in exempt_terms}:
                continue  # Node is intentionally comparative
            for lineno, line in enumerate(lines, 1):
                if term.lower() in line.lower():
                    has_comparison = any(cw in line.lower() for cw in COMPARISON_TRIGGERS)
                    if not has_comparison:
                        issues.append({
                            "nodeId": nid,
                            "term": term,
                            "location": f"{section_path.name}:{lineno}",
                            "severity": "warning",
                            "context": line.strip()[:200],
                            "recommendation": (
                                f"Add 'vs', 'alongside', or other comparison marker. "
                                f"Reason: {reason}"
                            ),
                        })

    return issues


def run(run_dir: Path, bundle_dir: Path) -> dict:
    bundle = json.loads((bundle_dir / "contract.bundle.json").read_text(encoding="utf-8"))
    bundle_id = bundle.get("bundleId", "")
    domain_map = load_domain_policy(bundle_dir)

    sections_dir = run_dir / "sections"
    if not sections_dir.is_dir():
        return {"ok": True, "issues": [], "note": "no sections directory"}

    if domain_map is None:
        return {"ok": True, "blockingCount": 0, "warningCount": 0, "issues": [],
                "checked": False,
                "note": f"bundle '{bundle_id}' declares no policies.json domainLeakage policy — nothing to check against"}

    all_issues = []
    for sec_file in sorted(sections_dir.glob("*.json")):
        if sec_file.name == "_accepted":
            continue
        nid = sec_file.stem
        issues = check_section_text(sec_file, domain_map, nid)
        all_issues.extend(issues)

    blocking = [i for i in all_issues if i.get("severity") == "blocking"]
    warnings = [i for i in all_issues if i.get("severity") == "warning"]

    return {
        "ok": len(blocking) == 0,
        "checked": True,
        "blockingCount": len(blocking),
        "warningCount": len(warnings),
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
    if not opts["--run"] or not opts["--bundle"]:
        print("usage: validate_domain_leakage.py --run <run-dir> --bundle <bundle-dir> [--out <report.json>]",
              file=sys.stderr)
        return 2
    run_dir = Path(opts["--run"])
    bundle_dir = Path(opts["--bundle"])
    if not run_dir.is_dir() or not bundle_dir.is_dir():
        print(json.dumps({"ok": False, "error": "run or bundle dir not found"}), file=sys.stderr)
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
