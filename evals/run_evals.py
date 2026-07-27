#!/usr/bin/env python3
"""run_evals - deterministic evaluation + test suite for ContractGraph.

Exercises the real script CLIs (via subprocess) over the company-research and
study-plan bundles and synthetic fixtures, covering the eval categories in
docs/evaluation.md. No model calls, no network, no live research. Prints a
pass/fail table and exits non-zero if any case fails.

Usage:  python evals/run_evals.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
TMP = ROOT / "runtime" / "runs" / "_evaltmp"
results = []


def run(args, cwd=ROOT):
    p = subprocess.run([PY, *args], capture_output=True, text=True, cwd=str(cwd))
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        out = None
    return p.returncode, out, p.stdout, p.stderr


def check(cat, name, passed, detail=""):
    results.append((cat, name, bool(passed), detail))


def write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def setup():
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)


# ---------------- compilation ----------------
def t_compilation():
    for bundle in ("contracts/company-research", "contracts/study-plan"):
        rc, out, *_ = run(["scripts/validate_contract_bundle.py", bundle])
        check("graph-compilation", f"bundle valid: {bundle}", rc == 0 and out and out["ok"])
        rc, out, *_ = run(["scripts/build_contract_manifest.py", bundle, "--out-dir", str(TMP / Path(bundle).name)])
        check("graph-compilation", f"graph compiles 0-conflict: {bundle}",
              rc == 0 and out and out["ok"] and not out["dependencyConflicts"])
        rc, out, *_ = run(["scripts/validate_compiled_graph.py", str(TMP / Path(bundle).name / "graph.json")])
        check("global-consistency", f"compiled graph valid: {bundle}", rc == 0 and out and out["ok"])


# ---------------- negative bundle cases ----------------
def t_negatives():
    b = TMP / "neg"
    shutil.copytree(ROOT / "contracts/company-research", b)
    bundle = json.loads((b / "contract.bundle.json").read_text(encoding="utf-8"))
    bundle["nodes"][3]["contract"] = "node-contracts/NOPE.contract.json"
    write(b / "contract.bundle.json", bundle)
    rc, out, *_ = run(["scripts/validate_contract_bundle.py", str(b)])
    check("node-contract-adherence", "invalid subcontract reference fails", rc == 1 and out and not out["ok"])

    b2 = TMP / "neg2"
    shutil.copytree(ROOT / "contracts/company-research", b2)
    (b2 / "roles/ml-engineer.role.json").unlink()
    rc, out, *_ = run(["scripts/validate_contract_bundle.py", str(b2)])
    check("node-contract-adherence", "missing required role fails", rc == 1 and out and not out["ok"])

    b3 = TMP / "neg3"
    shutil.copytree(ROOT / "contracts/company-research", b3)
    nc = json.loads((b3 / "node-contracts/dsa.contract.json").read_text(encoding="utf-8"))
    nc["x-contractgraph"]["dependsOn"].append("ghost")
    write(b3 / "node-contracts/dsa.contract.json", nc)
    rc, out, *_ = run(["scripts/validate_contract_bundle.py", str(b3)])
    check("graph-compilation", "dangling dependency fails", rc == 1 and out and not out["ok"])


# ---------------- node contract adherence (real study-plan contract) ----------------
def t_node_output():
    valid = {"nodeId": "python", "contractVersion": "1.0.0", "status": "complete",
             "data": {"topic": "Python for backend", "objectives": ["Master async IO"],
                      "resources": [{"title": "Python docs", "url": "https://docs.python.org/3/", "type": "doc"}],
                      "milestones": [{"name": "Build an API", "successCriteria": "all tests pass"}]},
             "sources": [], "verification": {"verifiedBy": "section-verifier", "status": "passed"}}
    write(TMP / "py_valid.json", valid)
    rc, out, *_ = run(["scripts/validate_node_output.py", str(TMP / "py_valid.json"),
                       "--bundle", "contracts/study-plan", "--node", "python"])
    check("node-contract-adherence", "valid node output accepted", rc == 0 and out and out["ok"], out and str(out.get("errors")))

    invalid = json.loads(json.dumps(valid))
    del invalid["data"]["objectives"]           # required missing
    invalid["data"]["resources"] = []            # violates minItems 1
    write(TMP / "py_invalid.json", invalid)
    rc, out, *_ = run(["scripts/validate_node_output.py", str(TMP / "py_invalid.json"),
                       "--bundle", "contracts/study-plan", "--node", "python"])
    ok = rc == 1 and out and not out["ok"] and any("objectives" in e["path"] for e in out["errors"])
    check("node-contract-adherence", "invalid node output rejected (path-specific)", ok)

    wrong = json.loads(json.dumps(valid)); wrong["nodeId"] = "WRONG"
    write(TMP / "py_wrongid.json", wrong)
    rc, out, *_ = run(["scripts/validate_node_output.py", str(TMP / "py_wrongid.json"),
                       "--bundle", "contracts/study-plan", "--node", "python"])
    check("node-contract-adherence", "wrong nodeId detected", rc == 1 and out and any("nodeId" in e["path"] for e in out["errors"]))


# ---------------- final + references + urls ----------------
def t_final_refs_urls():
    bad_final = {"schemaVersion": "1.0.0", "documentType": "PersonalizedStudyPlan"}  # missing required
    write(TMP / "bad_final.json", bad_final)
    rc, out, *_ = run(["scripts/validate_final_output.py", str(TMP / "bad_final.json"), "--bundle", "contracts/study-plan"])
    check("global-consistency", "invalid final rejected", rc == 1 and out and not out["ok"])

    refdoc = {"sourceRegistry": {"s1": {"sourceRef": "s1"}},
              "data": {"claims": [{"evidenceRefs": ["s1", "MISSING"]}], "link": "not-a-url", "ok": "https://x.com/a"}}
    write(TMP / "refdoc.json", refdoc)
    rc, out, *_ = run(["scripts/validate_references.py", str(TMP / "refdoc.json"), "--bundle", "contracts/company-research"])
    check("evidence-quality", "unresolved evidenceRef caught", rc == 1 and out and out["unresolvedEvidenceRefs"] == ["MISSING"])
    rc, out, *_ = run(["scripts/validate_source_urls.py", str(TMP / "refdoc.json")])
    check("evidence-quality", "malformed url caught", rc == 1 and out and out["malformed"] == ["not-a-url"])


# ---------------- deterministic aggregation ----------------
def t_merge():
    sdir = TMP / "sections"
    write(sdir / "company-intelligence.json", {"nodeId": "company-intelligence", "data": {"name": "Acme"},
          "sources": [{"sourceRef": "s1", "canonicalUrl": "https://acme.com/a", "title": "A"}]})
    write(sdir / "role-intelligence.json", {"nodeId": "role-intelligence", "data": {"roles": ["ai-engineer"]},
          "sources": [{"sourceRef": "s1", "canonicalUrl": "https://acme.com/a", "title": "A"},
                      {"sourceRef": "s2", "canonicalUrl": "https://acme.com/b", "title": "B"}]})
    run(["scripts/merge_verified_sections.py", "--bundle", "contracts/company-research",
         "--sections", str(sdir), "--out", str(TMP / "f1.json")])
    run(["scripts/merge_verified_sections.py", "--bundle", "contracts/company-research",
         "--sections", str(sdir), "--out", str(TMP / "f2.json")])
    identical = (TMP / "f1.json").read_text() == (TMP / "f2.json").read_text()
    reg = json.loads((TMP / "f1.json").read_text())["sourceRegistry"]
    check("deterministic-aggregation", "merge deterministic", identical)
    check("deterministic-aggregation", "sources deduped (s1 once)", sorted(reg) == ["s1", "s2"])


# ---------------- caching ----------------
def t_cache():
    write(TMP / "in1.json", {"companyName": "Acme", "targetRoles": ["ai-engineer"]})
    write(TMP / "in2.json", {"companyName": "Globex", "targetRoles": ["ai-engineer"]})
    _, o1, *_ = run(["scripts/cache_key.py", "--bundle", "contracts/company-research", "--node", "dsa", "--input", str(TMP / "in1.json")])
    _, o1b, *_ = run(["scripts/cache_key.py", "--bundle", "contracts/company-research", "--node", "dsa", "--input", str(TMP / "in1.json")])
    _, o2, *_ = run(["scripts/cache_key.py", "--bundle", "contracts/company-research", "--node", "dsa", "--input", str(TMP / "in2.json")])
    check("cache-correctness", "cache key stable for same input", o1 and o1b and o1["cacheKey"] == o1b["cacheKey"])
    check("cache-correctness", "cache key changes with input", o1 and o2 and o1["cacheKey"] != o2["cacheKey"])


# ---------------- user state preservation (retry targeting / refresh) ----------------
def t_preserve():
    write(TMP / "old.json", {"items": [{"globalProblemId": "p1", "title": "OLD", "masteryStatus": "mastered", "userNotes": "mine"}]})
    write(TMP / "new.json", {"items": [{"globalProblemId": "p1", "title": "NEW", "masteryStatus": "", "userNotes": ""}]})
    run(["scripts/preserve_user_state.py", "--old", str(TMP / "old.json"), "--new", str(TMP / "new.json"),
         "--bundle", "contracts/company-research", "--out", str(TMP / "merged.json")])
    m = json.loads((TMP / "merged.json").read_text())["items"][0]
    check("retry-targeting", "research field updated on refresh", m["title"] == "NEW")
    check("candidate-truthfulness", "user-owned state preserved on refresh", m["masteryStatus"] == "mastered" and m["userNotes"] == "mine")


# ---------------- trace ----------------
def t_trace():
    rd = TMP / "run"
    write(rd / "run.json", {"runId": "r1", "bundleId": "company-research"})
    write(rd / "node-state" / "company-intelligence.json", {"nodeId": "company-intelligence", "state": "ACCEPTED", "attempts": 1, "required": True})
    rc, out, *_ = run(["scripts/generate_trace.py", "--run", str(rd)])
    check("token-efficiency", "trace generated", rc == 0 and out and out["ok"])


# ---------------- privacy ----------------
def t_privacy():
    import re
    email = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone = re.compile(r"(?<!\d)(?:\+\d[\d ().-]{8,}\d|\d{10,})(?!\d)")
    leaks = []
    for f in list((ROOT / ".claude/skills").rglob("SKILL.md")) + list((ROOT / ".claude/agents").rglob("*.md")):
        txt = f.read_text(encoding="utf-8")
        if email.search(txt) or phone.search(txt):
            leaks.append(str(f.relative_to(ROOT)))
    check("privacy-leakage", "no PII (email/phone) in skills/agents", not leaks, str(leaks))


# ---------------- skill triggering (proxy) ----------------
def t_triggering():
    bad = []
    for f in (ROOT / ".claude/skills").rglob("SKILL.md"):
        head = f.read_text(encoding="utf-8").split("---")
        desc = ""
        if len(head) >= 3:
            for line in head[1].splitlines():
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
        if not desc.lower().startswith("use whenever") and not desc.lower().startswith("use when") and "use when" not in desc.lower():
            bad.append(f.parent.name)
    check("skill-triggering", "all skill descriptions are trigger-first ('Use when')", not bad, str(bad))


# ---------------- genericity (study-plan proves no hard-coding) ----------------
def t_genericity():
    g = json.loads((ROOT / "runtime/compiled/study-plan/graph.json").read_text())
    sp_nodes = {n["nodeId"] for n in g["nodes"]}
    cr_terms = {"dsa", "hld", "lld", "resume-analysis", "company-intelligence", "behavioral"}
    check("graph-compilation", "study-plan has its OWN nodes (no company-research nodes)",
          sp_nodes == {"baseline-assessment", "python", "fastapi", "databases", "distributed-systems", "evaluation-plan"})
    # no company-research concept strings leak into study-plan bundle files
    leak = []
    for f in (ROOT / "contracts/study-plan").rglob("*.json"):
        low = f.read_text(encoding="utf-8").lower()
        for term in ("dsa", "hld", "lld", "resume", "company-intelligence", "salesforce"):
            if term in low:
                leak.append((f.name, term))
    check("privacy-leakage", "no company-research concepts in study-plan bundle", not leak, str(leak))


# ---------------- dry runs ----------------
def t_dryruns():
    rc, out, *_ = run(["scripts/dry_run.py", "--bundle", "contracts/company-research", "--compiled", "runtime/compiled"])
    check("token-efficiency", "company-research dry-run plan", rc == 0 and out and len(out["layerOrder"]) == 8)
    rc, out, *_ = run(["scripts/dry_run.py", "--bundle", "contracts/study-plan", "--compiled", "runtime/compiled/study-plan"])
    check("token-efficiency", "study-plan dry-run plan", rc == 0 and out and len(out["layerOrder"]) == 3)


def main():
    setup()
    for t in (t_compilation, t_negatives, t_node_output, t_final_refs_urls, t_merge,
              t_cache, t_preserve, t_trace, t_privacy, t_triggering, t_genericity, t_dryruns):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            check("runner", f"{t.__name__} crashed", False, repr(exc))
    passed = sum(1 for *_, ok, _ in [(c, n, p, d) for c, n, p, d in results] if ok)
    total = len(results)
    width = max(len(n) for _, n, _, _ in results)
    print(f"{'CATEGORY':<26} {'CASE':<{width}}  RESULT")
    print("-" * (26 + width + 10))
    for cat, name, ok, detail in results:
        line = f"{cat:<26} {name:<{width}}  {'PASS' if ok else 'FAIL'}"
        if not ok and detail:
            line += f"  <- {detail[:80]}"
        print(line)
    print("-" * (26 + width + 10))
    print(f"{passed}/{total} passed")
    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
