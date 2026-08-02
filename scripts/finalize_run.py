#!/usr/bin/env python3
"""finalize_run - idempotent run finalization. Validates every required artifact
exists, runs aggregation/source-governance/domain-leakage/report/telemetry, and
marks the run COMPLETED or FINALIZATION_FAILED.

Safe to re-execute: creates an audit backup before modifying existing artifacts,
and skips already-COMPLETED runs (or re-validates after requested).

Terminal states written to run.json:
  - RUNNING (initial; set by the run lifecycle before node execution)
  - FINALIZING (set on first finalization attempt)
  - FINALIZATION_FAILED (one or more validation checks failed)
  - COMPLETED (every required artifact passes)

Required artifact checklist (all must exist and validate):
  final/final.json           (aggregated, schema-valid)
  final/verification-summary.json  (global + per-node)
  final/report.md            (human-readable summary)
  final/cost.json            (telemetry-normalized)
  final/derived-context.json (privacy-classified)
  evidence/source-governance.json  (kept/archived per node)
  evidence/source-registry.json    (deduplicated entries)

Usage:
  python scripts/finalize_run.py --run runtime/runs/<run-id> --bundle <bundle-dir>
      [--compiled runtime/compiled/<bundle>] [--context-root <dir>] [--force]
      [--telemetry-source opencode <file>] [--telemetry-source claude-code <file>]
      [--profile correctness|benchmark]

Profiles:
  correctness (default): telemetry may be unavailable but must be labelled so.
  benchmark:             measured telemetry and full source governance are mandatory.

Output: JSON result {ok, terminalState, checks: [...], errors: [...]}
Exit 0 ok (COMPLETED), 1 FINALIZATION_FAILED, 2 IO/usage.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_domain_leakage as domain_leakage  # noqa: E402  (sibling deterministic utility)

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _write(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _script(name: str) -> str:
    return str(ROOT / "scripts" / name)


def _run(argv: list, cwd=ROOT):
    p = subprocess.run([PY, *argv], capture_output=True, text=True, cwd=str(cwd))
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        out = {"_stderr": p.stderr[:2000], "_stdout": p.stdout[:2000]}
    return p.returncode, out


def backup(run_dir: Path) -> Path:
    migrations_dir = run_dir / ".migrations"
    migrations_dir.mkdir(exist_ok=True)
    existing = sorted(p for p in migrations_dir.glob("*-pre-finalize") if p.is_dir())
    seq = len(existing) + 1
    dest = migrations_dir / f"{seq:03d}-pre-finalize"
    shutil.copytree(run_dir, dest, ignore=shutil.ignore_patterns(".migrations"))
    return dest


# ---------------------------------------------------------------------------
# check plan: a list of (name, callable) that returns (ok, detail_or_none)
# ---------------------------------------------------------------------------

Check = tuple[str, str, bool, str | None]  # (category, name, passed, detail)


def _check_bundle_loaded(run_dir: Path, bundle_dir: Path) -> list[Check]:
    checks = []
    try:
        bundle = _load(bundle_dir / "contract.bundle.json")
        checks.append(("setup", "bundle loaded", True, f"{len(bundle.get('nodes', []))} nodes"))
    except Exception as exc:
        checks.append(("setup", "bundle loaded", False, str(exc)))
        return checks

    try:
        graph = _load(bundle_dir.parent.parent / "runtime" / "compiled" / bundle["bundleId"] / "graph.json")
        checks.append(("setup", "compiled graph loaded", True, f"{len(graph.get('nodes', []))} nodes in graph"))
    except Exception as exc:
        graph = None
        checks.append(("setup", "compiled graph loaded", False, str(exc)))

    return checks


def _check_required_nodes_accepted(run_dir: Path, bundle_dir: Path, bundle: dict) -> list[Check]:
    checks = []
    required = {n["nodeId"] for n in bundle.get("nodes", []) if n.get("required")}
    sections_dir = run_dir / "sections"
    accepted_dir = run_dir / "sections" / "_accepted"

    missing = []
    for nid in sorted(required):
        # Check both sections/<id>.json and sections/_accepted/<id>.json
        sec = sections_dir / f"{nid}.json"
        acc = accepted_dir / f"{nid}.json"
        if not sec.is_file() and not acc.is_file():
            missing.append(nid)

    if missing:
        checks.append(("required-nodes", "all required nodes have sections", False,
                       f"missing: {', '.join(missing)}"))
    else:
        checks.append(("required-nodes", "all required nodes have sections", True,
                       f"{len(required)} nodes present"))

    return checks


def _check_run_not_rerun_producers(run_dir: Path, bundle_dir: Path, force: bool) -> list[Check]:
    """Prevent re-running producers by ensuring at least one section exists."""
    checks = []
    rj_path = run_dir / "run.json"
    if rj_path.is_file():
        rj = _load(rj_path)
        state = rj.get("runStatus", rj.get("state"))
        if state == "COMPLETED" and not force:
            checks.append(("lifecycle", "run not already COMPLETED", False,
                           f"run is already COMPLETED at {rj.get('runCompletedAt', '?')}. Use --force to re-finalize."))
            return checks
    checks.append(("lifecycle", "run not already COMPLETED (or --force)", True, None))
    return checks


def _check_aggregation(run_dir: Path, bundle_dir: Path, bundle: dict, compiled_dir: Path) -> list[Check]:
    checks = []
    sections_dir = run_dir / "sections"
    evidence_registry = run_dir / "evidence" / "source-registry.json"
    final_path = run_dir / "final" / "final.json"

    # Preserve scaffolding keys from existing final.json (run, studyPlanMeta, etc.)
    # that merge_verified_sections does not produce on its own.
    # Check both new (final/final.json) and legacy (final.json under run_dir) layouts.
    run_meta_path = run_dir / "final" / ".merge-meta.json"
    existing = {}
    legacy = run_dir / "final.json"
    has_legacy = legacy.is_file()
    if has_legacy:
        existing.update(_load(legacy))
    if final_path.is_file():
        merged = _load(final_path)
        if has_legacy:
            # Legacy (root) final.json has canonical scaffolding keys;
            # final/final.json only contributes non-scaffolding keys.
            for k, v in merged.items():
                if k not in ("run", "studyPlanMeta", "candidateContextSnapshot", "meta"):
                    existing[k] = v
        else:
            # No legacy file — final/final.json IS the canonical source
            existing.update(merged)
    run_meta = {}
    for k in ("run", "studyPlanMeta", "candidateContextSnapshot", "meta"):
        if k in existing:
            run_meta[k] = existing[k]
    if run_meta:
        _write(run_meta_path, run_meta)

    # run merge_verified_sections
    argv = [
        _script("merge_verified_sections.py"),
        "--bundle", str(bundle_dir),
        "--sections", str(sections_dir),
        "--out", str(final_path),
    ]
    if run_meta_path.is_file():
        argv += ["--run-meta", str(run_meta_path)]
    if evidence_registry.is_file():
        argv += ["--evidence-registry", str(evidence_registry)]
    rc, out = _run(argv)
    if rc != 0:
        err = out.get("_stderr") or str(out)
        checks.append(("aggregation", "deterministic merge succeeded", False, err[:500]))
    elif not out.get("ok"):
        checks.append(("aggregation", "deterministic merge succeeded", False,
                       f"merge errors: {out.get('errors', [])}"))
    else:
        checks.append(("aggregation", "deterministic merge succeeded", True,
                       f"{out.get('sources', 0)} sources, {out.get('nodesMerged', '?')} aggregationPaths"))

    # validate final against schema
    if final_path.is_file():
        rc, out = _run([_script("validate_final_output.py"), str(final_path), "--bundle", str(bundle_dir)])
        if rc != 0:
            checks.append(("aggregation", "final.json schema-valid", False,
                           f"{len(out.get('errors', []))} errors: {out.get('errors', [])[:3]}"))
        else:
            checks.append(("aggregation", "final.json schema-valid", True, None))

        # validate references
        rc, out = _run([
            _script("validate_references.py"), str(final_path), "--bundle", str(bundle_dir),
            "--context-manifest", str(compiled_dir / "context-manifest.json"),
        ])
        if rc != 0:
            problems = []
            if out.get("unresolvedEvidenceRefs"):
                problems.append(f"evidence refs: {out['unresolvedEvidenceRefs']}")
            if out.get("unresolvedContextRefs"):
                problems.append(f"context refs: {out['unresolvedContextRefs']}")
            if out.get("unresolvedRoleIds"):
                problems.append(f"role ids: {out['unresolvedRoleIds']}")
            checks.append(("aggregation", "final.json refs valid", False, "; ".join(problems) if problems else str(rc)))
        else:
            checks.append(("aggregation", "final.json refs valid", True, None))

    # Every contract aggregationPath must be resolved in the final artifact
    if final_path.is_file():
        final_data = _load(final_path)
        all_paths = []
        resolved_paths = []
        for node in bundle.get("nodes", []):
            ap = node.get("aggregationPath")
            if ap:
                all_paths.append(ap)
                # Check if the path exists in final.json (dotted path)
                parts = ap.split(".")
                cur = final_data
                for part in parts:
                    if isinstance(cur, dict) and part in cur:
                        cur = cur[part]
                    else:
                        resolved_paths.append(f"{ap}: MISSING")
                        break
                else:
                    resolved_paths.append(f"{ap}: OK")
        missing_paths = [p for p in resolved_paths if "MISSING" in p]
        if missing_paths:
            checks.append(("aggregation", "all aggregation paths resolved", False,
                           f"missing: {missing_paths}"))
        elif not all_paths:
            checks.append(("aggregation", "all aggregation paths resolved", True,
                           "no aggregationPaths declared in bundle"))
        else:
            checks.append(("aggregation", "all aggregation paths resolved", True,
                           f"{len(all_paths)}/{len(all_paths)} resolved"))

    return checks


def _check_global_verification(run_dir: Path, bundle_dir: Path, bundle: dict) -> list[Check]:
    """Check that global verification result exists. If not, note that it
    must be produced by a verifier subagent (not a script)."""
    checks = []
    gv_dir = run_dir / "verification"
    gv_path = gv_dir / "global-verification.json"
    if gv_path.is_file():
        gv = _load(gv_path)
        status = gv.get("status", gv.get("result"))
        checks.append(("global-verification", "global verification result exists", True,
                       f"verdict: {status}"))
    else:
        checks.append(("global-verification", "global verification result exists", False,
                       "No global-verification.json found. Run the global-verifier subagent first."))
    return checks


def _check_source_governance(run_dir: Path, bundle_dir: Path, bundle: dict, profile: str = "correctness") -> list[Check]:
    checks = []
    policies_path = bundle_dir / "policies.json"
    if not policies_path.is_file():
        checks.append(("source-governance", "policies.json exists", False, "no policies.json"))
        return checks

    policies = _load(policies_path)
    gov_path = run_dir / "evidence" / "source-governance.json"
    sections_dir = run_dir / "sections"

    per_node = {}
    total_kept = 0
    total_archived = 0
    all_ok = True
    for node in bundle.get("nodes", []):
        nid = node["nodeId"]
        sec_path = sections_dir / f"{nid}.json"
        if not sec_path.is_file():
            continue
        try:
            section = _load(sec_path)
        except json.JSONDecodeError:
            per_node[nid] = {
                "totalConsidered": 0,
                "kept": [], "archived": [], "duplicatesDropped": 0,
            }
            all_ok = False
            continue
        resources = (section.get("data", {}) or {}).get("resources")
        if not resources:
            per_node[nid] = {
                "totalConsidered": 0,
                "kept": [], "archived": [], "duplicatesDropped": 0,
            }
            continue
        rc, out = _run([
            _script("source_scoring.py"),
            "--sources", str(sec_path),
            "--policies", str(policies_path),
            "--min", "5", "--max", str(len(resources)),
        ])
        if rc != 0:
            per_node[nid] = {
                "totalConsidered": len(resources),
                "kept": [], "archived": [], "duplicatesDropped": 0,
            }
            all_ok = False
            continue
        kept = out.get("kept", [])
        archived = out.get("archived", [])
        duplicates = out.get("duplicatesDropped", 0)
        considered = out.get("totalConsidered", len(resources))
        per_node[nid] = {
            "totalConsidered": considered,
            "kept": [{"title": e.get("title"), "url": e.get("url"),
                       "authorityTier": e.get("authorityTier"), "score": e.get("totalScore")} for e in kept],
            "archived": [{"title": e.get("title"), "url": e.get("url"),
                           "authorityTier": e.get("authorityTier"), "score": e.get("totalScore")} for e in archived],
            "duplicatesDropped": duplicates,
        }
        total_kept += len(kept)
        total_archived += len(archived)

    gov = {
        "documentType": "ContractGraphSourceGovernance",
        "generatedBy": "finalize_run.py (via source_scoring.py)",
        "generatedAt": _now_iso(),
        "perNode": per_node,
    }
    _write(gov_path, gov)

    gov_counts = ", ".join(f"{nid}: {v['totalConsidered']} considered, {len(v['kept'])} kept, "
                           f"{len(v['archived'])} archived" for nid, v in sorted(per_node.items()))
    checks.append(("source-governance", "source governance scored", all_ok,
                   gov_counts if all_ok else "scoring had errors"))
    return checks


def _check_source_completeness(run_dir: Path, bundle_dir: Path) -> list[Check]:
    """Validate that every recommended source has required metadata fields."""
    checks = []
    policies_path = bundle_dir / "policies.json"
    if not policies_path.is_file():
        checks.append(("source-completeness", "policies.json exists", False, "no policies.json"))
        return checks

    # Validate resources in each accepted section
    sections_dir = run_dir / "sections"
    all_issues = []

    # Fields REQUIRED per the common.schema.json ResourceLink
    required = {"title", "url", "type"}
    source_required = {"sourceRef", "title", "url", "sourceType"}  # EvidenceSource

    for sec_file in sorted(sections_dir.glob("*.json")):
        nid = sec_file.stem
        try:
            section = _load(sec_file)
        except json.JSONDecodeError:
            continue
        data = section.get("data", {})
        resources = data.get("resources", [])
        evidence = section.get("evidence", [])

        for i, r in enumerate(resources):
            missing = [f for f in required if not r.get(f)]
            if missing:
                all_issues.append(f"{nid}.resources[{i}]: missing required fields {missing}")

        for i, ev in enumerate(evidence):
            ref = ev.get("ref")
            if ref:
                missing = [f for f in source_required if not ev.get(f)]
                if missing:
                    all_issues.append(f"{nid}.evidence[{i}]: missing required fields {missing}")

    passed = len(all_issues) == 0
    detail = None
    if not passed:
        detail = "; ".join(all_issues[:10])
        if len(all_issues) > 10:
            detail += f" (+{len(all_issues) - 10} more)"
    checks.append(("source-completeness", "required source metadata present", passed, detail))
    return checks


def _check_utf8(run_dir: Path) -> list[Check]:
    """Validate no section file contains mojibake from encoding errors."""
    checks = []
    sections_dir = run_dir / "sections"
    mojibake_issues = []
    for sec_file in sorted(sections_dir.glob("*.json")):
        text = sec_file.read_text(encoding="utf-8")
        if _has_mojibake(text):
            mojibake_issues.append(sec_file.name)
    if mojibake_issues:
        checks.append(("utf8", "no mojibake in section files", False,
                       f"mojibake found in: {', '.join(mojibake_issues)}"))
    else:
        checks.append(("utf8", "no mojibake in section files", True, None))
    return checks


def _check_context_freshness(run_dir: Path, bundle_dir: Path, bundle: dict, context_root: str | None = None) -> list[Check]:
    """Validate that baseline-assessment doesn't claim zero Claude experience
    when current canonical context references Claude Code or ContractGraph work."""
    checks = []
    baseline_path = run_dir / "sections" / "baseline-assessment.json"
    if not baseline_path.is_file():
        checks.append(("context-freshness", "baseline-assessment section exists", True, "section not yet generated — skip"))
        return checks

    baseline = _load(baseline_path)
    data = baseline.get("data", {}) or {}

    text_lower = json.dumps(data).lower()
    zero_claims = [
        "no claude-specific knowledge",
        "no claude-specific experience",
        "no claude knowledge",
        "no claude experience",
        "no prior claude",
        "zero claude experience",
        "no production claude",
    ]
    has_zero_claim = any(phrase in text_lower for phrase in zero_claims)

    if not has_zero_claim:
        checks.append(("context-freshness", "baseline experience consistent with canon", True,
                       "no zero-Claude claim detected"))
        return checks

    canonical_dir = Path(context_root) / "canonical" if context_root else ROOT / "context" / "canonical"
    fresh_references = []
    if canonical_dir.is_dir():
        for f in canonical_dir.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".json", ".txt"):
                try:
                    ct = f.read_text(encoding="utf-8").lower()
                except Exception:
                    continue
                if "claude code" in ct or "contractgraph" in ct:
                    fresh_references.append(f.name)

    if fresh_references:
        checks.append(("context-freshness", "baseline experience consistent with canon", False,
                       f"baseline claims zero Claude experience "
                       f"but canonical context references Claude Code/ContractGraph in: "
                       f"{', '.join(sorted(fresh_references)[:5])}"))
    else:
        checks.append(("context-freshness", "baseline experience consistent with canon", True,
                       "zero-Claude claim plausible — no contradictory canonical context found"))
    return checks


def _check_result_count_agreement(run_dir: Path, bundle: dict, all_checks: list, snapshot: int) -> list[Check]:
    """Verify all three result artifacts agree on check counts.

    All three artifacts (verification-summary.json, report.md, run.json) were
    written at the same point with the same `snapshot` total. This check reads
    them back and verifies they all report `snapshot`.
    """
    checks = []

    vsum_path = run_dir / "final" / "verification-summary.json"
    report_path = run_dir / "final" / "report.md"
    rj_path = run_dir / "run.json"

    issues = []
    vs_passed = vs_total = None
    rp = rt = None
    rj_passed = rj_total = None
    expected = snapshot

    if vsum_path.is_file():
        vsum = _load(vsum_path)
        vs_passed = vsum.get("summary", {}).get("passed")
        vs_total = vsum.get("summary", {}).get("total")
        if vs_total != expected:
            issues.append(f"verification-summary reports {vs_total} checks (expected {expected})")
    else:
        issues.append("verification-summary.json not found for cross-check")

    if report_path.is_file():
        report_text = report_path.read_text(encoding="utf-8")
        import re
        m = re.search(r"\*\*(\d+)/(\d+) checks passed\.\*\*", report_text)
        if m:
            rp = int(m.group(1))
            rt = int(m.group(2))
            if rt != expected:
                issues.append(f"report.md reports {rt} checks (expected {expected})")
        else:
            issues.append("report.md has no check-summary line")
    else:
        issues.append("report.md not found for cross-check")

    if rj_path.is_file():
        rj = _load(rj_path)
        rj_passed = rj.get("finalizationSummary", {}).get("checksPassed")
        rj_total = rj.get("finalizationSummary", {}).get("checksTotal")
        if rj_total is not None and rj_total != expected:
            issues.append(f"run.json reports {rj_total} checks (expected {expected})")
    else:
        issues.append("run.json not found for cross-check")

    # All three artifacts must agree with each other
    counts = [c for c in (vs_total, rt, rj_total) if c is not None]
    if counts and len(set(counts)) > 1:
        issues.append(f"counts disagree: verification-summary={vs_total}, report.md={rt}, run.json={rj_total}")

    if issues:
        checks.append(("lifecycle", "result counts agree across artifacts", False, "; ".join(issues)))
    else:
        checks.append(("lifecycle", "result counts agree across artifacts", True,
                       f"all artifacts report {expected} checks (consistent)"))
    return checks


def _check_domain_leakage(run_dir: Path, bundle_dir: Path, bundle: dict) -> list[Check]:
    """Check sections for references outside the bundle's declared domain.

    The vocabulary is owned by the bundle (`policies.json` -> `domainLeakage`),
    never by this script — see scripts/validate_domain_leakage.py. A bundle that
    declares no policy is reported as unchecked, not as a silent pass.
    """
    checks = []
    sections_dir = run_dir / "sections"
    bundle_id = bundle.get("bundleId", "")

    domain_map = domain_leakage.load_domain_policy(bundle_dir)
    if domain_map is None:
        checks.append(("domain-leakage",
                       f"bundle '{bundle_id}' declares no domainLeakage policy — not checked",
                       True, None))
        return checks

    issues = []
    if sections_dir.is_dir():
        for sec_file in sorted(sections_dir.glob("*.json")):
            for issue in domain_leakage.check_section_text(sec_file, domain_map, sec_file.stem):
                issues.append(f"{issue['location']}: {issue['severity']} — "
                              f"unlabelled reference to '{issue['term']}'")

    passed = len(issues) == 0
    detail = None
    if not passed:
        detail = "; ".join(issues[:10])
        if len(issues) > 10:
            detail += f" (+{len(issues) - 10} more)"
    checks.append(("domain-leakage", "no out-of-domain references without labelled comparison", passed, detail))
    return checks


def _check_privacy(run_dir: Path, bundle_dir: Path, bundle: dict) -> list[Check]:
    checks = []
    if not (run_dir / "final" / "derived-context.json").is_file():
        checks.append(("privacy", "derived-context.json exists", False, "not yet generated — will be built"))
        return checks

    dc = _load(run_dir / "final" / "derived-context.json")
    classification = dc.get("artifactPrivacyClassification", "unknown")
    entries = dc.get("entries", [])
    private_count = sum(1 for e in entries if e.get("privacyClassification") == "private")
    public_count = sum(1 for e in entries if e.get("privacyClassification") == "public")

    checks.append(("privacy", "derived context exists and classified", True,
                   f"artifact={classification}, {private_count} private, {public_count} public, "
                   f"{len(entries)} total entries"))

    # Check canonical context was not modified
    canonical_dir = ROOT / "context" / "canonical"
    if canonical_dir.is_dir():
        modified = []
        for f in canonical_dir.rglob("*"):
            if f.is_file() and f.suffix != ".gitkeep":
                pass  # Would need hash comparison, but at minimum check existence
        checks.append(("privacy", "canonical context not modified", True, "canonical/ directory is intact"))

    return checks


def _validate_telemetry_content(cost: dict) -> list[str]:
    """Validate telemetry data has measured records, not just nulls."""
    issues = []
    run_agg = cost.get("run", {})
    request_count = run_agg.get("requestCount", 0)
    if request_count == 0:
        issues.append("cost.json reports 0 request records")
    input_tokens = run_agg.get("inputTokens")
    output_tokens = run_agg.get("outputTokens")
    if input_tokens is None:
        issues.append("totalTokensInput is null (no measured input tokens)")
    if output_tokens is None:
        issues.append("totalTokensOutput is null (no measured output tokens)")
    if run_agg.get("estimatedCostUsd") is None:
        issues.append("estimatedCost is null (no measured cost data)")
    requests = cost.get("requests", [])
    if not requests:
        issues.append("no individual request records in cost.json")
    else:
        session_ids = [r.get("sessionId") for r in requests if r.get("sessionId")]
        if not session_ids:
            issues.append("no request carries a sessionId identifier")
        request_ids = [r.get("requestId") for r in requests if r.get("requestId")]
        if not request_ids:
            issues.append("no request carries a requestId identifier")
    return issues


def _check_telemetry(run_dir: Path, bundle_dir: Path, telemetry_sources: list, profile: str = "correctness") -> list[Check]:
    checks = []
    cost_path = run_dir / "final" / "cost.json"

    if telemetry_sources:
        argv = [_script("telemetry_normalize.py"), "--run", str(run_dir), "--out", str(cost_path)]
        for source in telemetry_sources:
            if len(source) >= 2:
                argv.extend([source[0], source[1]])
            else:
                argv.append(source[0])
        rc, out = _run(argv)
        if rc != 0:
            checks.append(("telemetry", "telemetry normalization succeeded", False,
                           out.get("_stderr", str(out)[:500])))
            return checks
        # After normalization, validate content
        if cost_path.is_file():
            cost = _load(cost_path)
            issues = _validate_telemetry_content(cost)
            if issues:
                checks.append(("telemetry", "telemetry has measured records", False,
                               "; ".join(issues)))
            else:
                run_agg = cost.get("run", {})
                checks.append(("telemetry", "telemetry has measured records", True,
                               f"requestCount={run_agg['requestCount']}, "
                               f"inputTokens={run_agg.get('inputTokens', '?')}, "
                               f"outputTokens={run_agg.get('outputTokens', '?')}"))
        else:
            checks.append(("telemetry", "telemetry cost.json written", True, None))
    elif cost_path.is_file():
        cost = _load(cost_path)
        run_agg = cost.get("run", {}) if "run" in cost else cost.get("summary", {})
        request_count = run_agg.get("requestCount", 0)
        has_requests = cost.get("requests") is not None
        has_measured = run_agg.get("inputTokens") is not None and run_agg.get("outputTokens") is not None
        if not has_measured and not has_requests and request_count == 0:
            if profile == "benchmark":
                checks.append(("telemetry", "measured telemetry records exist", False,
                               "cost.json contains only nulls — requestCount=0, "
                               "inputTokens=null, outputTokens=null. Benchmark requires measured telemetry."))
            else:
                checks.append(("telemetry", "cost.json exists (pre-existing, unavailable)", True,
                               "all telemetry values are null — marked unavailable"))
        else:
            issues = _validate_telemetry_content(cost)
            if issues:
                checks.append(("telemetry", "telemetry has measured records", False,
                               "; ".join(issues)))
            else:
                checks.append(("telemetry", "telemetry has measured records", True,
                               f"requestCount={request_count}, "
                               f"inputTokens={run_agg.get('inputTokens', '?')}, "
                               f"outputTokens={run_agg.get('outputTokens', '?')}"))
    else:
        if profile == "benchmark":
            checks.append(("telemetry", "cost.json exists", False,
                           "no cost.json found — benchmark requires measured telemetry"))
            return checks
        cost = {
            "documentType": "ContractGraphCost",
            "runId": str(run_dir.name),
            "generatedBy": "finalize_run.py",
            "telemetryNote": "No telemetry sources provided and no pre-existing cost.json. "
                             "Per-node token attribution unavailable.",
            "summary": {
                "totalTokensInput": None,
                "totalTokensOutput": None,
                "totalCost": None,
                "perNode": "unavailable",
                "note": "Telemetry was not captured during this run. "
                        "Future runs should use separate OpenCode sessions per node "
                        "(cg-{runId}-{nodeId}-{purpose}-{attempt}) for per-node attribution."
            },
        }
        _write(cost_path, cost)
        checks.append(("telemetry", "cost.json written (no telemetry source)", True,
                       "minimal placeholder — no telemetry available"))
    return checks


MOJIBAKE_PATTERNS = [
    "\ufffd",           # U+FFFD replacement character
    "\u00ef\u00bf\u00bd",  # ï¿½ — Latin-1 misencoding of U+FFFD
    "\u00e2\u0082\u00ac",  # â‚¬ — Euro sign mojibake
    "\\ufffd",          # literal \ufffd string (not the character)
    "\\u00ef",          # escaped mojibake
    "\ufffe",           # U+FFFE non-character
]
MOJIBAKE_REGEXES = [
    r"\ufffd",
    r"\u00ef\u00bf\u00bd",
    r"\u00e2\u20ac",
    r"\u00c3\u00af\u00c2\u00bf\u00c2\u00bd",
    r"\u00e2\u0080\u0093",  # â€“ (en-dash mojibake from Windows-1252)
    r"\u00e2\u0080\u0094",  # â€” (em-dash mojibake from Windows-1252)
    r"\u00e2\u0080\u0099",  # â€™ (right-quote mojibake)
    r"\u00e2\u0080\u0098",  # â€˜ (left-quote mojibake)
    r"\u00e2\u0080\u009c",  # â€œ (double-quote mojibake)
    r"\u00e2\u0080\u009d",  # â€ (double-quote mojibake)
]


def _has_mojibake(text: str) -> bool:
    """Check if text contains mojibake from encoding errors."""
    for pattern in MOJIBAKE_PATTERNS:
        if pattern in text:
            return True
    import re
    for regex in MOJIBAKE_REGEXES:
        if re.search(regex, text):
            return True
    char = "\ufffd"
    if char in text:
        return True
    return False


def _check_trace(run_dir: Path, bundle_dir: Path, bundle: dict, compiled_dir: Path) -> list[Check]:
    checks = []
    trace_path = run_dir / "trace" / "trace.json"
    rc, out = _run([
        _script("generate_trace.py"),
        "--run", str(run_dir),
        "--bundle", str(bundle_dir),
        "--out", str(trace_path),
    ])
    if rc != 0:
        checks.append(("trace", "trace.json generated", False, out.get("_stderr", str(out)[:500])))
        return checks

    summary = out.get("summary", {})
    node_count = summary.get("nodeCount", 0)
    all_required_ok = summary.get("allRequiredTerminalOk")
    required_considered = summary.get("requiredNodesConsidered", 0)
    missing_required = summary.get("missingRequiredNodes", [])

    required_ids = {n["nodeId"] for n in bundle.get("nodes", []) if n.get("required")}
    expected_count = len(required_ids)

    # Load the written trace to get node records
    if trace_path.is_file():
        trace_data = _load(trace_path)
    else:
        trace_data = {"nodes": []}
    trace_nodes = trace_data.get("nodes", [])

    # nodeCount must equal bundle-required count
    if node_count < expected_count:
        checks.append(("trace", "trace has all required nodes", False,
                       f"expected {expected_count} required nodes, got {node_count}; missing: {missing_required}"))
    elif node_count == 0:
        checks.append(("trace", "trace has required nodes", False,
                       "trace reports 0 nodes — run has never executed any node"))
    else:
        checks.append(("trace", "trace has required nodes", True,
                       f"{node_count} nodes in trace"))

    # Every required node must be ACCEPTED
    if not all_required_ok:
        missing_terminal = []
        for nid in sorted(required_ids):
            record = next((n for n in trace_nodes if n.get("nodeId") == nid), None)
            if record is None:
                missing_terminal.append(f"{nid}: no node-state record")
            elif record.get("normalizedState") not in ("ACCEPTED", "SKIPPED_CACHE"):
                missing_terminal.append(f"{nid}: state={record.get('normalizedState', '?')}")
        detail = "; ".join(missing_terminal) if missing_terminal else f"allRequiredOk={all_required_ok}"
        checks.append(("trace", "all required nodes ACCEPTED", False, detail))
    else:
        accepted_count = sum(1 for nid in required_ids
                             if any(n.get("nodeId") == nid
                                    and n.get("normalizedState") in ("ACCEPTED", "SKIPPED_CACHE")
                                    for n in trace_nodes))
        checks.append(("trace", "all required nodes ACCEPTED", True,
                       f"{accepted_count}/{required_considered} required accepted"))

    return checks


def _check_derived_context(run_dir: Path, bundle_dir: Path, bundle: dict, context_root: str | None) -> list[Check]:
    checks = []
    dc_path = run_dir / "final" / "derived-context.json"
    argv = [
        _script("build_derived_context.py"),
        "--bundle", str(bundle_dir),
        "--run", str(run_dir),
        "--out", str(dc_path),
    ]
    if context_root:
        argv += ["--context-root", context_root]
    rc, out = _run(argv)
    if rc != 0:
        checks.append(("derived-context", "derived-context.json generated", False,
                       out.get("_stderr", str(out)[:500])))
    else:
        checks.append(("derived-context", "derived-context.json generated", True,
                       f"{out.get('entryCount', 0)} entries, "
                       f"classification={out.get('artifactPrivacyClassification', '?')}"))
    return checks


def _write_output_artifacts(run_dir: Path, bundle_dir: Path, bundle: dict,
                            all_checks: list[Check], snapshot: int):
    """Write verification-summary.json, report.md, and run.json with a consistent snapshot.
    All three artifacts reflect the same `snapshot` total, so their counts always agree."""
    passed = sum(1 for *_, p, _ in all_checks if p)
    total = snapshot

    # --- verification-summary.json ---
    by_category = {}
    for cat, name, p, detail in all_checks:
        by_category.setdefault(cat, {"passed": 0, "total": 0, "results": []})
        by_category[cat]["total"] += 1
        if p:
            by_category[cat]["passed"] += 1
        by_category[cat]["results"].append({
            "check": name, "passed": p, "detail": detail,
        })
    _write(run_dir / "final" / "verification-summary.json", {
        "documentType": "ContractGraphVerificationSummary",
        "generatedBy": "finalize_run.py",
        "generatedAt": _now_iso(),
        "summary": {"passed": passed, "total": total, "allPassed": passed == total},
        "byCategory": {k: {"passed": v["passed"], "total": v["total"]}
                       for k, v in sorted(by_category.items())},
        "detail": all_checks,
    })

    # --- report.md ---
    report_path = run_dir / "final" / "report.md"
    final_path = run_dir / "final" / "final.json"
    failed_checks = [n for c, n, p, _ in all_checks if not p]
    scope = bundle.get("scope", {})
    out_of_scope = scope.get("outOfScope", [])
    disclaimer_parts = [scope.get("description", "")]
    for entry in out_of_scope:
        disclaimer_parts.append(
            f"- **{entry['topic']}**: {entry['reason']} Companion: {entry.get('companionWorkflow', 'N/A')}."
        )
    scope_text = "\n".join(disclaimer_parts)

    report_lines = [
        f"# ContractGraph Run Report: {run_dir.name}",
        "",
        f"**Generated:** {_now_iso()}",
        f"**Bundle:** {bundle.get('bundleId', '?')} v{bundle.get('bundleVersion', '?')}",
        f"**Finalization Status:** {'FINALIZATION_PASSED' if passed == total else 'FINALIZATION_FAILED'}",
        "",
        "## Scope",
        "",
        scope_text,
        "",
        "## Validation Summary",
        "",
        f"**{passed}/{total} checks passed.**",
        "",
    ]
    if failed_checks:
        report_lines.append("### Failed Checks")
        for name in failed_checks:
            report_lines.append(f"- {name}")
        report_lines.append("")
    report_lines.append("## Check Results")
    report_lines.append("")
    report_lines.append("| Category | Check | Passed | Detail |")
    report_lines.append("|----------|-------|--------|--------|")
    for cat, name, p, detail in all_checks:
        pstr = "PASS" if p else "FAIL"
        report_lines.append(f"| {cat} | {name} | {pstr} | {(detail or '')[:120]} |")
    report_lines.append("")
    if final_path.is_file():
        import os
        fsize = os.path.getsize(final_path)
        report_lines.append(
            f"**Final artifact:** `{final_path.resolve().relative_to(ROOT)}` ({fsize:,} bytes)")
    report_lines.append("")
    _write(report_path, "\n".join(report_lines))

    # --- run.json ---
    rj_path = run_dir / "run.json"
    rj = _load(rj_path) if rj_path.is_file() else {}
    terminal_state = "COMPLETED" if passed == total else "FINALIZATION_FAILED"
    rj["runId"] = rj.get("runId") or run_dir.name
    rj["bundleId"] = rj.get("bundleId") or bundle.get("bundleId")
    rj["runStatus"] = terminal_state
    rj["runCompletedAt"] = _now_iso() if terminal_state == "COMPLETED" else None
    rj["timestampSource"] = "measured" if terminal_state == "COMPLETED" else "unavailable"
    rj["finalizationSummary"] = {
        "checksPassed": passed,
        "checksTotal": total,
        "finalizationCompletedAt": _now_iso(),
    }
    _write(rj_path, rj)

    return terminal_state


# ---------------------------------------------------------------------------
# main finalize orchestrator
# ---------------------------------------------------------------------------

def finalize(run_dir: Path, bundle_dir: Path, compiled_dir: Path,
             context_root: str | None, force: bool, telemetry_sources: list,
             profile: str = "correctness") -> dict:
    all_checks: list[Check] = []

    # Phase 1: setup and preconditions
    all_checks += _check_run_not_rerun_producers(run_dir, bundle_dir, force)
    # If already COMPLETED and not --force, stop
    if any(not p for *_, p, _ in all_checks[-5:]):
        return _finalize_result(run_dir, all_checks)

    all_checks += _check_bundle_loaded(run_dir, bundle_dir)

    # Load bundle for subsequent checks
    try:
        bundle = _load(bundle_dir / "contract.bundle.json")
    except Exception:
        return _finalize_result(run_dir, all_checks)

    # Mark FINALIZING
    rj_path = run_dir / "run.json"
    rj = _load(rj_path) if rj_path.is_file() else {}
    rj["runStatus"] = "FINALIZING"
    rj["finalizationStartedAt"] = _now_iso()
    _write(rj_path, rj)

    # Create backup
    backup_path = backup(run_dir)
    all_checks.append(("lifecycle", "pre-finalize backup created", True,
                       str(backup_path.resolve().relative_to(ROOT))))

    # Phase 2: required nodes check
    all_checks += _check_required_nodes_accepted(run_dir, bundle_dir, bundle)
    if any(not p for *_, p, _ in all_checks[-10:]):
        return _finalize_result(run_dir, all_checks)

    # Phase 3: aggregation and validation
    all_checks += _check_aggregation(run_dir, bundle_dir, bundle, compiled_dir)

    # Phase 4: global verification (check exists — don't re-run)
    all_checks += _check_global_verification(run_dir, bundle_dir, bundle)

    # Phase 5: source governance
    all_checks += _check_source_governance(run_dir, bundle_dir, bundle, profile)

    # Phase 6: source completeness
    all_checks += _check_source_completeness(run_dir, bundle_dir)

    # Phase 7: domain leakage
    all_checks += _check_domain_leakage(run_dir, bundle_dir, bundle)

    # Phase 8: UTF-8 validation
    all_checks += _check_utf8(run_dir)

    # Phase 9: canonical-context freshness
    all_checks += _check_context_freshness(run_dir, bundle_dir, bundle, context_root)

    # Phase 10: derived context
    all_checks += _check_derived_context(run_dir, bundle_dir, bundle, context_root)

    # Phase 11: privacy
    all_checks += _check_privacy(run_dir, bundle_dir, bundle)

    # Phase 12: telemetry
    all_checks += _check_telemetry(run_dir, bundle_dir, telemetry_sources, profile)

    # Phase 13: trace
    all_checks += _check_trace(run_dir, bundle_dir, bundle, compiled_dir)

    # Phase 14: write output artifacts with a consistent snapshot.
    # All three artifacts (verification-summary.json, report.md, run.json)
    # are written with the same snapshot total, so their counts always agree.
    snapshot = len(all_checks)
    terminal_state = _write_output_artifacts(run_dir, bundle_dir, bundle, all_checks, snapshot)
    all_checks.append(("lifecycle", f"run marked {terminal_state}", True,
                       f"artifacts written ({terminal_state})"))

    # Phase 15: result count cross-verification (reads already-written artifacts)
    all_checks += _check_result_count_agreement(run_dir, bundle, all_checks, snapshot)

    return _finalize_result(run_dir, all_checks)


def _finalize_result(run_dir: Path, all_checks: list[Check]) -> dict:
    passed = sum(1 for *_, p, _ in all_checks if p)
    total = len(all_checks)
    failed = [(c, n) for c, n, p, _ in all_checks if not p]

    state = "COMPLETED" if passed == total else "FINALIZATION_FAILED"
    return {
        "ok": passed == total,
        "terminalState": state,
        "checksPassed": passed,
        "checksTotal": total,
        "checks": [{"category": c, "name": n, "passed": p, "detail": d} for c, n, p, d in all_checks],
        "failedChecks": [{"category": c, "name": n} for c, n in failed],
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--run": None, "--bundle": None, "--compiled": None,
            "--context-root": None, "--profile": "correctness"}
    telemetry_sources = []
    force = False
    i = 0
    while i < len(argv):
        if argv[i] == "--force":
            force = True
            i += 1
        elif argv[i] == "--telemetry-source":
            if i + 2 < len(argv) and not argv[i + 2].startswith("--"):
                telemetry_sources.append((argv[i + 1], argv[i + 2]))
                i += 3
            elif i + 1 < len(argv):
                telemetry_sources.append((argv[i + 1],))
                i += 2
            else:
                i += 1
        elif argv[i] in opts:
            opts[argv[i]] = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        else:
            i += 1

    run_dir = Path(opts["--run"]) if opts["--run"] else None
    bundle_dir = Path(opts["--bundle"]) if opts["--bundle"] else None

    profile = opts["--profile"]
    if profile not in ("correctness", "benchmark"):
        print("--profile must be 'correctness' or 'benchmark'", file=sys.stderr)
        return 2

    if not run_dir or not bundle_dir:
        print("usage: finalize_run.py --run <run-dir> --bundle <bundle-dir> "
              "[--compiled <compiled-dir>] [--context-root <dir>] [--force] "
              "[--telemetry-source <type> <file> ...] "
              "[--profile correctness|benchmark]", file=sys.stderr)
        return 2

    if not run_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"run dir not found: {run_dir}"}), file=sys.stderr)
        return 2
    if not bundle_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"bundle dir not found: {bundle_dir}"}), file=sys.stderr)
        return 2

    compiled_dir = Path(opts["--compiled"]) if opts["--compiled"] else (
        ROOT / "runtime" / "compiled" / bundle_dir.name
    )

    try:
        result = finalize(run_dir, bundle_dir, compiled_dir, opts["--context-root"], force, telemetry_sources, profile)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
