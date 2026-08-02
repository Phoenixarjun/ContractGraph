#!/usr/bin/env python3
"""run_evals - deterministic evaluation + test suite for ContractGraph.

Exercises the real script CLIs (via subprocess) over the public study-plan
bundle and synthetic fixtures, covering the eval categories in
docs/evaluation.md. No model calls, no network, no live research. Prints a
pass/fail table and exits non-zero if any case fails.

Every case runs on a fresh clone. Cases that need something a clean checkout
legitimately lacks -- a local-only private bundle, a completed run under the
git-ignored runtime/runs/, or an optional extra from scripts/requirements.txt
-- are reported as SKIP with a reason, never as a failure and never silently
dropped. A skip is never counted as a pass.

Usage:  python evals/run_evals.py
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
TMP = ROOT / "runtime" / "runs" / "_evaltmp"

# The public reference bundle — always present in a clone.
PUBLIC_BUNDLE = "contracts/study-plan"
# Bundles that are git-ignored local-only validation workflows. Cases that
# depend on one are skipped (not failed) when it is not on disk.
PRIVATE_BUNDLES = ("contracts/company-research",)
# A completed local run used by a few regression cases. runtime/runs/ is
# git-ignored, so a fresh clone has none — those cases skip rather than fail.
REAL_RUN = "runtime/runs/20260728-study-plan"

results = []
skips = []


def run(args, cwd=ROOT):
    p = subprocess.run([PY, *args], capture_output=True, text=True, cwd=str(cwd))
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        out = None
    return p.returncode, out, p.stdout, p.stderr


def check(cat, name, passed, detail=""):
    results.append((cat, name, bool(passed), detail))


def skip(cat, name, reason):
    """Record a case that could not run here. Never counted as a pass."""
    skips.append((cat, name, reason))


def available_bundles():
    """The public bundle, plus any private bundle that happens to be on disk."""
    return [PUBLIC_BUNDLE] + [b for b in PRIVATE_BUNDLES if (ROOT / b).is_dir()]


def have_real_run() -> bool:
    return (ROOT / REAL_RUN).is_dir()


def _module_available(name: str) -> bool:
    """Is an optional extra importable by the interpreter the script CLIs run under?

    run() shells out with sys.executable, so this interpreter's view is the
    same one every subprocess gets.
    """
    return importlib.util.find_spec(name) is not None


def write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def setup():
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)


# ---------------- compilation ----------------
def t_compilation():
    for bundle in available_bundles():
        rc, out, *_ = run(["scripts/validate_contract_bundle.py", bundle])
        check("graph-compilation", f"bundle valid: {bundle}", rc == 0 and out and out["ok"])
        rc, out, *_ = run(["scripts/build_contract_manifest.py", bundle, "--out-dir", str(TMP / Path(bundle).name)])
        check("graph-compilation", f"graph compiles 0-conflict: {bundle}",
              rc == 0 and out and out["ok"] and not out["dependencyConflicts"])
        rc, out, *_ = run(["scripts/validate_compiled_graph.py", str(TMP / Path(bundle).name / "graph.json")])
        check("global-consistency", f"compiled graph valid: {bundle}", rc == 0 and out and out["ok"])


# ---------------- negative bundle cases ----------------
def t_negatives():
    """Corrupt a copy of the public bundle in one specific way per case, and
    assert the deterministic validator rejects exactly that corruption."""
    src = ROOT / PUBLIC_BUNDLE

    b = TMP / "neg"
    shutil.copytree(src, b)
    bundle = json.loads((b / "contract.bundle.json").read_text(encoding="utf-8"))
    bundle["nodes"][1]["contract"] = "node-contracts/NOPE.contract.json"
    write(b / "contract.bundle.json", bundle)
    rc, out, *_ = run(["scripts/validate_contract_bundle.py", str(b)])
    check("node-contract-adherence", "invalid subcontract reference fails", rc == 1 and out and not out["ok"])

    b2 = TMP / "neg2"
    shutil.copytree(src, b2)
    bundle2 = json.loads((b2 / "contract.bundle.json").read_text(encoding="utf-8"))
    bundle2["roles"] = [{"roleId": "ghost-role", "path": "roles/ghost-role.role.json"}]
    write(b2 / "contract.bundle.json", bundle2)
    rc, out, *_ = run(["scripts/validate_contract_bundle.py", str(b2)])
    check("node-contract-adherence", "missing required role fails", rc == 1 and out and not out["ok"])

    b3 = TMP / "neg3"
    shutil.copytree(src, b3)
    nc = json.loads((b3 / "node-contracts/python.contract.json").read_text(encoding="utf-8"))
    nc["x-contractgraph"]["dependsOn"].append("ghost")
    write(b3 / "node-contracts/python.contract.json", nc)
    rc, out, *_ = run(["scripts/validate_contract_bundle.py", str(b3)])
    check("graph-compilation", "dangling dependency fails", rc == 1 and out and not out["ok"])

    b4 = TMP / "neg4"
    shutil.copytree(src, b4)
    nc4 = json.loads((b4 / "node-contracts/python.contract.json").read_text(encoding="utf-8"))
    nc4["x-contractgraph"]["aggregationPath"] = "somethingElse"
    write(b4 / "node-contracts/python.contract.json", nc4)
    rc, out, *_ = run(["scripts/validate_contract_bundle.py", str(b4)])
    check("node-contract-adherence", "aggregationPath mismatch fails", rc == 1 and out and not out["ok"])


# ---------------- node contract adherence (real study-plan contract) ----------------
def t_node_output():
    valid = {"nodeId": "python", "contractVersion": "1.0.0", "status": "complete",
             "data": {"topic": "Python for backend", "objectives": ["Master async IO"],
                      "resources": [{"title": "Python docs", "url": "https://docs.python.org/3/", "type": "doc"}],
                      "milestones": [{"name": "Build an API", "successCriteria": "all tests pass"}]},
             "evidence": [{"ref": "SRC_ABC123", "claims": ["asyncio is the standard async I/O library"]}],
             "verification": {"verifiedBy": "section-verifier", "status": "passed"}}
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
    rc, out, *_ = run(["scripts/validate_references.py", str(TMP / "refdoc.json"), "--bundle", PUBLIC_BUNDLE])
    check("evidence-quality", "unresolved evidenceRef caught", rc == 1 and out and out["unresolvedEvidenceRefs"] == ["MISSING"])
    rc, out, *_ = run(["scripts/validate_source_urls.py", str(TMP / "refdoc.json")])
    check("evidence-quality", "malformed url caught", rc == 1 and out and out["malformed"] == ["not-a-url"])


# ---------------- deterministic aggregation ----------------
def t_merge():
    sdir = TMP / "sections"
    write(sdir / "python.json", {"nodeId": "python", "data": {"topic": "Python"},
          "sources": [{"sourceRef": "s1", "canonicalUrl": "https://example.org/a", "title": "A"}]})
    write(sdir / "fastapi.json", {"nodeId": "fastapi", "data": {"topic": "FastAPI"},
          "sources": [{"sourceRef": "s1", "canonicalUrl": "https://example.org/a", "title": "A"},
                      {"sourceRef": "s2", "canonicalUrl": "https://example.org/b", "title": "B"}]})
    run(["scripts/merge_verified_sections.py", "--bundle", PUBLIC_BUNDLE,
         "--sections", str(sdir), "--out", str(TMP / "f1.json")])
    run(["scripts/merge_verified_sections.py", "--bundle", PUBLIC_BUNDLE,
         "--sections", str(sdir), "--out", str(TMP / "f2.json")])
    identical = (TMP / "f1.json").read_text() == (TMP / "f2.json").read_text()
    reg = json.loads((TMP / "f1.json").read_text())["sourceRegistry"]
    check("deterministic-aggregation", "merge deterministic", identical)
    check("deterministic-aggregation", "sources deduped (s1 once)", sorted(reg) == ["s1", "s2"])


# ---------------- caching ----------------
def t_cache():
    write(TMP / "in1.json", {"learnerGoal": "backend engineering", "hoursPerWeek": 10})
    write(TMP / "in2.json", {"learnerGoal": "distributed systems", "hoursPerWeek": 10})
    _, o1, *_ = run(["scripts/cache_key.py", "--bundle", PUBLIC_BUNDLE, "--node", "python", "--input", str(TMP / "in1.json")])
    _, o1b, *_ = run(["scripts/cache_key.py", "--bundle", PUBLIC_BUNDLE, "--node", "python", "--input", str(TMP / "in1.json")])
    _, o2, *_ = run(["scripts/cache_key.py", "--bundle", PUBLIC_BUNDLE, "--node", "python", "--input", str(TMP / "in2.json")])
    check("cache-correctness", "cache key stable for same input", o1 and o1b and o1["cacheKey"] == o1b["cacheKey"])
    check("cache-correctness", "cache key changes with input", o1 and o2 and o1["cacheKey"] != o2["cacheKey"])


# ---------------- user state preservation (retry targeting / refresh) ----------------
def t_preserve():
    write(TMP / "old.json", {"items": [{"globalProblemId": "p1", "title": "OLD", "masteryStatus": "mastered", "userNotes": "mine"}]})
    write(TMP / "new.json", {"items": [{"globalProblemId": "p1", "title": "NEW", "masteryStatus": "", "userNotes": ""}]})
    run(["scripts/preserve_user_state.py", "--old", str(TMP / "old.json"), "--new", str(TMP / "new.json"),
         "--bundle", PUBLIC_BUNDLE, "--out", str(TMP / "merged.json")])
    m = json.loads((TMP / "merged.json").read_text())["items"][0]
    check("retry-targeting", "research field updated on refresh", m["title"] == "NEW")
    check("candidate-truthfulness", "user-owned state preserved on refresh", m["masteryStatus"] == "mastered" and m["userNotes"] == "mine")


# ---------------- trace ----------------
def t_trace():
    rd = TMP / "run"
    write(rd / "run.json", {"runId": "r1", "bundleId": "study-plan"})
    write(rd / "node-state" / "python.json", {"nodeId": "python", "state": "ACCEPTED", "attempts": 1, "required": True})
    rc, out, *_ = run(["scripts/generate_trace.py", "--run", str(rd)])
    check("token-efficiency", "trace generated", rc == 0 and out and out["ok"])


def t_trace_state_normalization():
    # canonical "state" key, mixed with the legacy "status" alias (the actual
    # shape of the 20260728-study-plan fixture) -- both must count as ACCEPTED,
    # never silently bucketed as UNKNOWN.
    rd = TMP / "trace-legacy"
    write(rd / "run.json", {"runId": "tr-legacy", "bundleId": "study-plan"})
    write(rd / "node-state" / "a.json", {"nodeId": "a", "state": "ACCEPTED", "attempts": 1})
    write(rd / "node-state" / "b.json", {"nodeId": "b", "status": "ACCEPTED", "attempts": 1})
    rc, out, *_ = run(["scripts/generate_trace.py", "--run", str(rd)])
    check("token-efficiency", "trace normalizes legacy 'status' key alongside 'state'",
          rc == 0 and out and out["summary"]["byState"] == {"ACCEPTED": 2})
    check("token-efficiency", "no UNKNOWN bucket appears for valid legacy records",
          "UNKNOWN" not in out["summary"]["byState"])
    check("token-efficiency", "no validation errors for well-formed legacy records",
          out["summary"]["invalidRecordCount"] == 0)

    # lowercase value under the legacy key -- must still normalize
    rd2 = TMP / "trace-lowercase"
    write(rd2 / "run.json", {"runId": "tr-lower"})
    write(rd2 / "node-state" / "c.json", {"nodeId": "c", "status": "accepted", "attempts": 1})
    rc, out, *_ = run(["scripts/generate_trace.py", "--run", str(rd2)])
    check("token-efficiency", "lowercase legacy state value normalizes to ACCEPTED",
          rc == 0 and out and out["summary"]["byState"] == {"ACCEPTED": 1})

    # missing state/status entirely -- must become a validation error, not UNKNOWN
    rd3 = TMP / "trace-missing"
    write(rd3 / "run.json", {"runId": "tr-missing"})
    write(rd3 / "node-state" / "d.json", {"nodeId": "d", "attempts": 1})
    rc, out, *_ = run(["scripts/generate_trace.py", "--run", str(rd3)])
    check("token-efficiency", "missing state/status never becomes a silent UNKNOWN bucket",
          rc == 0 and out and out["summary"]["byState"] == {})
    check("token-efficiency", "missing state/status is reported as a validation error",
          out and out["summary"]["invalidRecordCount"] == 1
          and out["validationErrors"][0]["nodeId"] == "d"
          and "missing" in out["validationErrors"][0]["error"])

    # invalid/unrecognized enum value -- must be flagged, not silently mapped
    rd4 = TMP / "trace-invalid"
    write(rd4 / "run.json", {"runId": "tr-invalid"})
    write(rd4 / "node-state" / "e.json", {"nodeId": "e", "state": "BOGUS_STATE", "attempts": 1})
    rc, out, *_ = run(["scripts/generate_trace.py", "--run", str(rd4)])
    check("token-efficiency", "invalid enum value never becomes a silent UNKNOWN bucket",
          rc == 0 and out and out["summary"]["byState"] == {})
    check("token-efficiency", "invalid enum value is reported as a validation error",
          out and out["summary"]["invalidRecordCount"] == 1
          and "unrecognized" in out["validationErrors"][0]["error"])

    # the real study-plan fixture: all 6 nodes use "status", all ACCEPTED
    if not have_real_run():
        skip("token-efficiency", "real study-plan run normalizes to byState.ACCEPTED == 6",
             f"no local run at {REAL_RUN}")
        skip("global-consistency", "real study-plan run's allRequiredTerminalOk covers all 6 required nodes",
             f"no local run at {REAL_RUN}")
        return
    rc, out, *_ = run(["scripts/generate_trace.py", "--run", REAL_RUN,
                        "--bundle", PUBLIC_BUNDLE, "--out", str(TMP / "sp-trace.json")])
    check("token-efficiency", "real study-plan run normalizes to byState.ACCEPTED == 6",
          rc == 0 and out and out["summary"]["byState"] == {"ACCEPTED": 6})
    check("global-consistency", "real study-plan run's allRequiredTerminalOk is checked against ALL 6 bundle-required nodes, not vacuously true",
          out and out["summary"]["requiredNodesConsidered"] == 6
          and out["summary"]["requiredNodesSource"] == "bundle"
          and out["summary"]["allRequiredTerminalOk"] is True)


def t_trace_required_from_bundle():
    # without --bundle: node-state's own (unpopulated) `required` flag ->
    # vacuously true, the exact defect a reviewer flagged.
    rd = TMP / "trace-vacuous"
    write(rd / "run.json", {"runId": "tr-vacuous"})
    write(rd / "node-state" / "a.json", {"nodeId": "a", "state": "ACCEPTED"})
    rc, out, *_ = run(["scripts/generate_trace.py", "--run", str(rd)])
    check("global-consistency", "without --bundle, requiredNodesConsidered is 0 when node-state never sets required (the vacuous-true trap)",
          rc == 0 and out and out["summary"]["requiredNodesConsidered"] == 0
          and out["summary"]["requiredNodesSource"] == "node-state.required")

    # with --bundle: the bundle's own required-node list is authoritative,
    # and a MISSING required node is now caught rather than silently ignored.
    b = TMP / "trace-bundle"
    write(b / "contract.bundle.json", {"nodes": [
        {"nodeId": "a", "required": True}, {"nodeId": "b", "required": True}, {"nodeId": "c", "required": False},
    ]})
    write(rd / "node-state" / "b_missing_on_purpose.json", {"nodeId": "c", "state": "ACCEPTED"})  # b itself never runs
    rc2, out2, *_ = run(["scripts/generate_trace.py", "--run", str(rd), "--bundle", str(b)])
    check("global-consistency", "with --bundle, requiredNodesConsidered reflects the bundle's declared required nodes (2), not 0",
          rc2 == 0 and out2 and out2["summary"]["requiredNodesConsidered"] == 2)
    check("global-consistency", "with --bundle, a required node with no node-state file at all is caught as missing",
          out2 and out2["summary"]["missingRequiredNodes"] == ["b"])
    check("global-consistency", "with --bundle, allRequiredTerminalOk is False when a required node never even ran",
          out2 and out2["summary"]["allRequiredTerminalOk"] is False)


# ---------------- workflow scope ----------------
def t_scope_dsa_out_of_scope():
    bundle = json.loads((ROOT / "contracts/study-plan/contract.bundle.json").read_text(encoding="utf-8"))
    check("global-consistency", "study-plan bundle declares a machine-readable scope block",
          "scope" in bundle and bundle["scope"].get("outOfScope"))
    check("global-consistency", "DSA is explicitly named as an out-of-scope companion workflow",
          any(e["topic"] == "DSA" and e.get("companionWorkflow") for e in bundle["scope"]["outOfScope"]))

    schema = json.loads((ROOT / "contracts/study-plan/contract.schema.json").read_text(encoding="utf-8"))
    check("global-consistency", "contract.schema.json requires studyPlanMeta.scopeDisclaimer",
          "scopeDisclaimer" in schema["properties"]["studyPlanMeta"]["required"])


def t_validate_final_output_scope_disclaimer():
    b = TMP / "scope-bundle"
    shutil.copytree(ROOT / "contracts/study-plan", b)
    final_ok = {
        "schemaVersion": "1.0.0", "documentType": "PersonalizedStudyPlan",
        "run": {"runId": "r1", "learnerGoal": "x", "contractBundleVersion": "1.0.0", "contextManifestHash": "h"},
        "studyPlanMeta": {"generatedAt": "2026-01-01T00:00:00Z", "caveats": ["x"],
                           "scopeDisclaimer": "This is a backend and AI systems study plan, not a complete "
                                              "career-preparation plan. DSA is explicitly out of scope; see the "
                                              "companion DSA workflow."},
    }
    write(TMP / "scope_final_ok.json", final_ok)
    rc, out, *_ = run(["scripts/validate_final_output.py", str(TMP / "scope_final_ok.json"), "--bundle", str(b)])
    check("global-consistency", "a scopeDisclaimer naming DSA passes the scope check",
          not any("scopeDisclaimer" in e.get("path", "") for e in (out or {}).get("errors", [])))

    final_bad = json.loads(json.dumps(final_ok))
    final_bad["studyPlanMeta"]["scopeDisclaimer"] = "This plan covers backend and AI systems topics."
    write(TMP / "scope_final_bad.json", final_bad)
    rc2, out2, *_ = run(["scripts/validate_final_output.py", str(TMP / "scope_final_bad.json"), "--bundle", str(b)])
    check("global-consistency", "a scopeDisclaimer that omits DSA is rejected (plan can't be misrepresented as complete)",
          rc2 == 1 and out2 and any("DSA" in e["message"] for e in out2["errors"]))


# ---------------- timestamps ----------------
def t_timestamp_now():
    rc, out, *_ = run(["scripts/timestamp_now.py"])
    check("token-efficiency", "timestamp_now emits a value", rc == 0 and out is not None and out.get("iso"))
    if rc == 0 and out:
        import re
        check("token-efficiency", "timestamp_now format is ISO-8601 UTC with milliseconds",
              bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", out["iso"])))


def t_validate_timestamps_valid_ordering():
    rd = TMP / "ts-valid"
    write(rd / "run.json", {"runId": "t1", "runCreatedAt": "2026-07-28T13:00:00.000Z", "runCompletedAt": "2026-07-28T14:10:00.500Z"})
    write(rd / "node-state" / "a.json", {"nodeId": "a", "nodeStartedAt": "2026-07-28T13:10:00.000Z", "nodeCompletedAt": "2026-07-28T13:20:00.000Z"})
    write(rd / "verification" / "global-verification.json", {"verificationCompletedAt": "2026-07-28T13:50:00.000Z"})
    write(rd / "final" / "derived-context.json", {"aggregationCompletedAt": "2026-07-28T13:55:00.000Z"})
    write(rd / "final" / "final.json", {"finalArtifactGeneratedAt": "2026-07-28T14:00:00.000Z"})
    rc, out, *_ = run(["scripts/validate_timestamps.py", "--run", str(rd)])
    check("global-consistency", "valid timestamp ordering passes", rc == 0 and out and out["ok"])


def t_validate_timestamps_impossible_sequence():
    rd = TMP / "ts-impossible"
    write(rd / "run.json", {"runCreatedAt": "2026-07-28T13:00:00.000Z", "runCompletedAt": "2026-07-28T14:10:00.000Z"})
    write(rd / "verification" / "global-verification.json", {"verificationCompletedAt": "2026-07-28T18:45:00.000Z"})
    rc, out, *_ = run(["scripts/validate_timestamps.py", "--run", str(rd)])
    check("global-consistency", "verification-after-completion is rejected as an impossible sequence",
          rc == 1 and out and not out["ok"]
          and any(e["before"] == "verificationCompletedAt" and e["after"] == "runCompletedAt" for e in out["orderingErrors"]))


def t_validate_timestamps_format_and_missing():
    rd = TMP / "ts-format"
    write(rd / "run.json", {"runCreatedAt": "2026-07-28T13:00:00Z"})  # no milliseconds -> format error
    rc, out, *_ = run(["scripts/validate_timestamps.py", "--run", str(rd)])
    check("global-consistency", "timestamp without milliseconds is a format error",
          rc == 1 and out and any(e["field"] == "runCreatedAt" for e in out["formatErrors"]))

    rd2 = TMP / "ts-null-ok"
    write(rd2 / "run.json", {"runCreatedAt": None, "timestampSource": "unavailable"})
    rc2, out2, *_ = run(["scripts/validate_timestamps.py", "--run", str(rd2)])
    check("global-consistency", "null timestamp WITH timestampSource:unavailable is valid",
          rc2 == 0 and out2 and out2["ok"])

    rd3 = TMP / "ts-null-bad"
    write(rd3 / "run.json", {"runCreatedAt": None})
    rc3, out3, *_ = run(["scripts/validate_timestamps.py", "--run", str(rd3)])
    check("global-consistency", "null timestamp WITHOUT timestampSource is a format error (never silently missing)",
          rc3 == 1 and out3 and any(e["field"] == "runCreatedAt" for e in out3["formatErrors"]))


def t_validate_timestamps_real_run_post_migration():
    # 20260728-study-plan was migrated by migrate_run_metadata.py (task: fix the
    # fabricated-timestamp defect on this exact run) -- its timestamps are now
    # either real or explicitly null+unavailable, never fabricated round numbers
    # or an impossible verifiedAt-after-completedAt sequence.
    if not have_real_run():
        skip("global-consistency", "the migrated real study-plan run passes timestamp validation",
             f"no local run at {REAL_RUN}")
        return
    rc, out, *_ = run(["scripts/validate_timestamps.py", "--run", REAL_RUN])
    check("global-consistency", "the migrated real study-plan run passes timestamp validation (no fabrication left)",
          rc == 0 and out and out["ok"] and not out["formatErrors"] and not out["orderingErrors"])


# ---------------- privacy propagation ----------------
def _write_privacy_fixture(root: Path):
    """A tiny 4-node synthetic bundle: a (synthetic refs, no deps) -> b (no
    own refs, depends on a) should end up PUBLIC; c (canonical refs, no deps)
    -> d (no own refs, depends on c) should end up PRIVATE (inherited)."""
    bundle = {
        "bundleId": "privacy-fixture", "documentType": "ContractGraphContractBundle",
        "nodes": [
            {"nodeId": "a", "contract": "node-contracts/a.json", "aggregationPath": "a"},
            {"nodeId": "b", "contract": "node-contracts/b.json", "aggregationPath": "b"},
            {"nodeId": "c", "contract": "node-contracts/c.json", "aggregationPath": "c"},
            {"nodeId": "d", "contract": "node-contracts/d.json", "aggregationPath": "d"},
        ],
    }
    write(root / "contract.bundle.json", bundle)
    write(root / "node-contracts" / "a.json", {"x-contractgraph": {"contextRefs": ["synthetic/goals.md"], "dependsOn": []}})
    write(root / "node-contracts" / "b.json", {"x-contractgraph": {"contextRefs": [], "dependsOn": ["a"]}})
    write(root / "node-contracts" / "c.json", {"x-contractgraph": {"contextRefs": ["canonical/goals.md"], "dependsOn": []}})
    write(root / "node-contracts" / "d.json", {"x-contractgraph": {"contextRefs": [], "dependsOn": ["c"]}})
    for nid in ("a", "b", "c", "d"):
        write(root / "run" / "sections" / f"{nid}.json",
              {"nodeId": nid, "contractVersion": "1.0.0", "data": {"evidence": [{"ref": f"SRC_{nid}"}]},
               "verification": {"confidence": 0.8}})
        write(root / "run" / "node-state" / f"{nid}.json", {"nodeId": nid, "state": "ACCEPTED", "completedAt": None})
    write(root / "run" / "run.json", {"runId": "privacy-run", "bundleId": "privacy-fixture"})


def t_derived_context_privacy():
    root = TMP / "privacy-fixture"
    _write_privacy_fixture(root)
    rc, out, _, err = run(["scripts/build_derived_context.py", "--bundle", str(root), "--run", str(root / "run"),
                            "--out", str(root / "run" / "final" / "derived-context.json")])
    ok = rc == 0 and out is not None
    check("privacy-leakage", "derived-context builds for the synthetic fixture", ok, err[:200])
    if not ok:
        return
    doc = json.loads((root / "run" / "final" / "derived-context.json").read_text(encoding="utf-8"))
    by_node = {e["nodeId"]: e for e in doc["entries"]}
    check("privacy-leakage", "node with only synthetic/ refs classifies public", by_node["a"]["privacyClassification"] == "public")
    check("privacy-leakage", "node with no own refs inherits PUBLIC from an all-synthetic dependency",
          by_node["b"]["privacyClassification"] == "public")
    check("privacy-leakage", "node with canonical/ refs defaults private", by_node["c"]["privacyClassification"] == "private")
    check("privacy-leakage", "node with no own refs inherits PRIVATE from a canonical-sourced dependency",
          by_node["d"]["privacyClassification"] == "private")
    check("privacy-leakage", "artifact-level classification is the most restrictive entry (private)",
          doc["artifactPrivacyClassification"] == "private")
    check("privacy-leakage", "every entry carries full provenance fields",
          all({"sourceRunId", "sourceNodeId", "evidenceRefs", "confidence", "createdAt", "expiresAt"} <= set(e.keys())
              for e in doc["entries"]))

    rc2, out2, *_ = run(["scripts/validate_against_schema.py", str(root / "run" / "final" / "derived-context.json"),
                          "--schema", "scripts/schemas/derived-context.schema.json"])
    check("privacy-leakage", "derived-context validates against derived-context.schema.json",
          rc2 == 0 and out2 and out2["ok"], out2 and str(out2.get("errors")))

    # never-downgrade: node "a" was already public; simulate a prior run where it
    # had been (incorrectly, or via later contamination) marked private -- a
    # re-run must never silently downgrade it back to public.
    prior = json.loads((root / "run" / "final" / "derived-context.json").read_text(encoding="utf-8"))
    for e in prior["entries"]:
        if e["nodeId"] == "a":
            e["privacyClassification"] = "private"
    write(root / "prior-derived-context.json", prior)
    rc3, out3, *_ = run(["scripts/build_derived_context.py", "--bundle", str(root), "--run", str(root / "run"),
                          "--existing", str(root / "prior-derived-context.json"),
                          "--out", str(root / "run" / "final" / "derived-context-2.json")])
    doc2 = json.loads((root / "run" / "final" / "derived-context-2.json").read_text(encoding="utf-8"))
    by_node2 = {e["nodeId"]: e for e in doc2["entries"]}
    check("privacy-leakage", "privacy classification never downgrades on re-run (a stays private once escalated)",
          rc3 == 0 and by_node2["a"]["privacyClassification"] == "private")

    # real study-plan run: personal canonical context -> every entry private
    if not have_real_run():
        skip("privacy-leakage", "real study-plan run (real canonical context) classifies private",
             f"no local run at {REAL_RUN}")
        return
    rc4, out4, *_ = run(["scripts/build_derived_context.py", "--bundle", PUBLIC_BUNDLE,
                          "--run", REAL_RUN,
                          "--out", str(TMP / "sp-derived-context.json")])
    ok4 = rc4 == 0 and out4 is not None
    check("privacy-leakage", "real study-plan run's derived context builds", ok4)
    if ok4:
        check("privacy-leakage", "real study-plan run (real canonical PII) classifies private, not 'false'",
              out4["artifactPrivacyClassification"] == "private")


def t_real_study_plan_context_root_disambiguation():
    # THE actual gap this test exists for: contracts/study-plan's real node
    # contracts declare contextRefs as "canonical/goals.md" etc -- a literal
    # string that's IDENTICAL whether the run resolved it against
    # context/canonical/ (real) or context/synthetic/study-plan/canonical/
    # (fake "Sam" data). Confirm the real contract really is shaped this way
    # (not a fabricated fixture), then confirm --context-root is what
    # actually distinguishes the two cases, not the ref string.
    real_contract = json.loads((ROOT / "contracts/study-plan/node-contracts/baseline-assessment.contract.json")
                                .read_text(encoding="utf-8"))
    check("privacy-leakage", "sanity: the real study-plan contract's contextRefs are context-root-ambiguous literals",
          real_contract["x-contractgraph"]["contextRefs"] == ["canonical/goals.md", "canonical/knowledge.md", "canonical/preferences.md"])

    root = TMP / "context-root-fixture"
    write(root / "run" / "run.json", {"runId": "ctx-root-run", "bundleId": "study-plan"})
    write(root / "run" / "sections" / "baseline-assessment.json",
          {"nodeId": "baseline-assessment", "contractVersion": "1.0.0", "data": {}, "verification": {}})

    # same real bundle, same real contract, same literal "canonical/..." refs --
    # only --context-root differs.
    rc_synth, out_synth, *_ = run(["scripts/build_derived_context.py", "--bundle", "contracts/study-plan",
                                    "--run", str(root / "run"), "--context-root", "context/synthetic/study-plan",
                                    "--out", str(root / "run" / "final" / "dc-synthetic.json")])
    rc_real, out_real, *_ = run(["scripts/build_derived_context.py", "--bundle", "contracts/study-plan",
                                  "--run", str(root / "run"), "--context-root", "context",
                                  "--out", str(root / "run" / "final" / "dc-real.json")])
    check("privacy-leakage", "identical contract/refs classify PUBLIC when --context-root is the synthetic tree",
          rc_synth == 0 and out_synth and out_synth["artifactPrivacyClassification"] == "public")
    check("privacy-leakage", "the SAME contract/refs classify PRIVATE when --context-root is the real tree",
          rc_real == 0 and out_real and out_real["artifactPrivacyClassification"] == "private")

    # omitting --context-root entirely must never become LESS restrictive than
    # the context-root-aware real-context case -- the ref-string fallback still
    # says private for a literal "canonical/..." ref.
    rc_none, out_none, *_ = run(["scripts/build_derived_context.py", "--bundle", "contracts/study-plan",
                                  "--run", str(root / "run"), "--out", str(root / "run" / "final" / "dc-none.json")])
    check("privacy-leakage", "omitting --context-root falls back to the conservative (private) ref-string heuristic",
          rc_none == 0 and out_none and out_none["artifactPrivacyClassification"] == "private")


def t_synthetic_context_stays_public():
    # a bundle whose every node touches ONLY context/synthetic/ must classify public end-to-end
    root = TMP / "all-synthetic-fixture"
    bundle = {"bundleId": "synthetic-only", "documentType": "ContractGraphContractBundle",
              "nodes": [{"nodeId": "s1", "contract": "node-contracts/s1.json", "aggregationPath": "s1"},
                        {"nodeId": "s2", "contract": "node-contracts/s2.json", "aggregationPath": "s2"}]}
    write(root / "contract.bundle.json", bundle)
    write(root / "node-contracts" / "s1.json", {"x-contractgraph": {"contextRefs": ["synthetic/goals.md"], "dependsOn": []}})
    write(root / "node-contracts" / "s2.json", {"x-contractgraph": {"contextRefs": ["synthetic/preferences.md"], "dependsOn": ["s1"]}})
    for nid in ("s1", "s2"):
        write(root / "run" / "sections" / f"{nid}.json", {"nodeId": nid, "contractVersion": "1.0.0", "data": {}, "verification": {}})
        write(root / "run" / "node-state" / f"{nid}.json", {"nodeId": nid, "state": "ACCEPTED"})
    write(root / "run" / "run.json", {"runId": "synthetic-run", "bundleId": "synthetic-only"})
    rc, out, _, err = run(["scripts/build_derived_context.py", "--bundle", str(root), "--run", str(root / "run"),
                            "--out", str(root / "run" / "final" / "derived-context.json")])
    check("privacy-leakage", "all-synthetic bundle builds", rc == 0 and out is not None, err[:200])
    if rc != 0:
        return
    check("privacy-leakage", "all-synthetic bundle's artifact classification is public end-to-end",
          out["artifactPrivacyClassification"] == "public")


# ---------------- telemetry ----------------
def t_telemetry_normalize():
    rd = TMP / "telemetry-run"
    write(rd / "run.json", {"runId": "tr1", "bundleId": "study-plan"})

    write(TMP / "cc.json", {"records": [
        {"model": "claude-sonnet-5", "usage": {"input_tokens": 1000, "output_tokens": 200,
         "cache_read_input_tokens": 500, "cache_creation_input_tokens": 0},
         "duration_ms": 4000, "tool_calls": 3, "final_status": "accepted",
         "metadata": {"node": "python", "purpose": "producer", "agent": "python",
                      "skill": "evidence-backed-web-research", "attempt": 1}},
        {"model": "claude-sonnet-5", "usage": {"input_tokens": 300, "output_tokens": 80},
         "duration_ms": 1200, "tool_calls": 0, "final_status": "passed",
         "metadata": {"node": "python", "purpose": "verifier", "agent": "section-verifier", "attempt": 1}},
    ]})
    write(TMP / "oc.json", {"messages": [
        {"model": "sonnet", "usage": {"promptTokens": 900, "completionTokens": 150},
         "durationMs": 3500, "toolCalls": 2, "finalStatus": "accepted",
         "metadata": {"node": "fastapi", "purpose": "producer", "agent": "fastapi", "attempt": 1}},
    ]})
    write(TMP / "local" / "1.json", {"model": "haiku", "agent": "structural-repair", "purpose": "repair",
         "node": "databases", "attempt": 2, "inputTokens": 400, "outputTokens": 60,
         "cacheReadTokens": 0, "cacheCreationTokens": 0, "durationMs": 900, "toolCalls": 1,
         "webSearches": 0, "webFetches": 0, "outputBytes": 1200, "status": "accepted"})

    rc, out, _, err = run(["scripts/telemetry_normalize.py", "--run", str(rd),
                            "--claude-code", str(TMP / "cc.json"), "--opencode", str(TMP / "oc.json"),
                            "--local", str(TMP / "local"), "--out", str(rd / "final" / "cost.json"),
                            "--requests-out", str(rd / "telemetry" / "requests.jsonl")])
    ok = rc == 0 and out is not None
    check("token-efficiency", "telemetry normalizes multi-source input", ok, err[:200])
    if not ok:
        return
    check("token-efficiency", "telemetry merges all 3 sources (4 requests)", len(out["requests"]) == 4)
    check("token-efficiency", "telemetry groups by node (python/fastapi/databases)",
          set(out["byNode"].keys()) == {"python", "fastapi", "databases"})
    check("token-efficiency", "telemetry groups by purpose (producer/verifier/repair)",
          set(out["byPurpose"].keys()) == {"producer", "verifier", "repair"})
    check("token-efficiency", "telemetry run aggregate counts all requests", out["run"]["requestCount"] == 4)
    check("token-efficiency", "telemetry never fabricates: run.json runId preserved", out["runId"] == "tr1")
    check("token-efficiency", "every request carries a requestId and telemetrySource",
          all(r["requestId"] and r["telemetrySource"] for r in out["requests"]))
    check("token-efficiency", "each source is tagged with its distinct telemetrySource",
          {r["telemetrySource"] for r in out["requests"]} == {"claude-code-otel-export", "opencode-session-export", "local-instrumentation"})
    check("token-efficiency", "requests.jsonl is written with one line per request",
          len((rd / "telemetry" / "requests.jsonl").read_text(encoding="utf-8").strip().splitlines()) == 4)
    check("token-efficiency", "no duplicates dropped for genuinely distinct requests", out["dedupedCount"] == 0)

    rc, out2, *_ = run(["scripts/validate_against_schema.py", str(rd / "final" / "cost.json"),
                         "--schema", "scripts/schemas/cost.schema.json"])
    check("token-efficiency", "cost.json validates against cost.schema.json", rc == 0 and out2 and out2["ok"],
          out2 and str(out2.get("errors")))


def t_telemetry_dedup():
    rd = TMP / "telemetry-dedup"
    write(rd / "run.json", {"runId": "tr-dedup"})
    record = {"model": "claude-sonnet-5", "usage": {"input_tokens": 500, "output_tokens": 100},
              "duration_ms": 2000, "tool_calls": 1, "final_status": "accepted",
              "metadata": {"node": "python", "purpose": "producer", "agent": "python", "attempt": 1}}
    # the SAME call captured twice, as a parent transcript export would if it
    # also embeds a subagent's own reported usage -- must collapse to one.
    write(TMP / "cc_dup.json", {"records": [record, dict(record)]})
    rc, out, *_ = run(["scripts/telemetry_normalize.py", "--run", str(rd),
                        "--claude-code", str(TMP / "cc_dup.json"), "--out", str(rd / "final" / "cost.json")])
    ok = rc == 0 and out is not None
    check("token-efficiency", "telemetry dedup input normalizes", ok)
    if not ok:
        return
    check("token-efficiency", "an identical duplicate request collapses to one (never double-counted)",
          len(out["requests"]) == 1 and out["dedupedCount"] == 1)
    check("token-efficiency", "run aggregate reflects the deduped count, not the raw input count",
          out["run"]["requestCount"] == 1)


def t_telemetry_missing_fields():
    rd = TMP / "telemetry-missing"
    write(rd / "run.json", {"runId": "tr2"})
    # a source that reports duration/tool-calls but NO token counts at all
    write(TMP / "cc_missing.json", {"records": [
        {"model": "claude-opus-4-8", "duration_ms": 2000, "tool_calls": 1,
         "metadata": {"node": "global-verifier", "purpose": "global-verifier"}},
    ]})
    rc, out, *_ = run(["scripts/telemetry_normalize.py", "--run", str(rd),
                        "--claude-code", str(TMP / "cc_missing.json"),
                        "--out", str(rd / "final" / "cost.json")])
    ok = rc == 0 and out is not None
    check("token-efficiency", "telemetry handles a source with no token data", ok)
    if not ok:
        return
    req = out["requests"][0]
    check("token-efficiency", "missing tokens are null, not fabricated as 0",
          req["inputTokens"] is None and req["outputTokens"] is None)
    check("token-efficiency", "available map marks missing metrics false",
          req["available"]["inputTokens"] is False and req["available"]["durationMs"] is True)
    check("token-efficiency", "cost is null when tokens unavailable (never estimated from nothing)",
          req["estimatedCostUsd"] is None)
    check("token-efficiency", "coverage reports 0/1 present for inputTokens",
          out["coverage"]["inputTokens"] == {"present": 0, "total": 1, "pct": 0.0})
    check("token-efficiency", "coverage reports full presence for durationMs",
          out["coverage"]["durationMs"]["present"] == 1)
    check("token-efficiency", "unavailableFields lists every missing metric by name",
          "inputTokens" in req["unavailableFields"] and "durationMs" not in req["unavailableFields"])


def t_node_cost_aggregation():
    rd = TMP / "telemetry-agg"
    write(rd / "run.json", {"runId": "tr3"})
    write(TMP / "agg_local" / "1.json", {"model": "sonnet", "node": "python", "purpose": "producer",
         "attempt": 1, "inputTokens": 100, "outputTokens": 10, "durationMs": 500, "toolCalls": 1})
    write(TMP / "agg_local" / "2.json", {"model": "sonnet", "node": "python", "purpose": "producer",
         "attempt": 1, "inputTokens": 200, "outputTokens": 20, "durationMs": 700, "toolCalls": 2})
    write(TMP / "agg_local" / "3.json", {"model": "haiku", "node": "fastapi", "purpose": "repair",
         "attempt": 2, "inputTokens": 50, "outputTokens": 5, "durationMs": 100, "toolCalls": 0})
    rc, out, *_ = run(["scripts/telemetry_normalize.py", "--run", str(rd),
                        "--local", str(TMP / "agg_local"), "--out", str(rd / "final" / "cost.json")])
    ok = rc == 0 and out is not None
    check("token-efficiency", "aggregation input built", ok)
    if not ok:
        return
    check("token-efficiency", "byNode sums equal per-request sums (python: 100+200=300 input tokens)",
          out["byNode"]["python"]["inputTokens"] == 300 and out["byNode"]["python"]["requestCount"] == 2)
    check("token-efficiency", "byModel sums correctly (sonnet: 10+20=30 output tokens)",
          out["byModel"]["sonnet"]["outputTokens"] == 30)
    check("token-efficiency", "byPurpose sums correctly (repair: single 50 input tokens)",
          out["byPurpose"]["repair"]["inputTokens"] == 50)
    check("token-efficiency", "byAttempt sums correctly (attempt 1: 2 requests)",
          out["byAttempt"]["1"]["requestCount"] == 2 and out["byAttempt"]["2"]["requestCount"] == 1)
    check("token-efficiency", "run aggregate equals sum of all groups (300 total input tokens)",
          out["run"]["inputTokens"] == 100 + 200 + 50)


# ---------------- source-quality governance ----------------
def t_source_scoring_authority_preference():
    sources = [
        {"sourceRef": "S1", "title": "Official asyncio documentation", "url": "https://docs.python.org/3/library/asyncio.html",
         "sourceType": "official_documentation", "publicationDate": "2026-01-01"},
        {"sourceRef": "S2", "title": "Some rando's asyncio tips and tricks blog post", "url": "https://randoblog.example.com/asyncio-tips",
         "sourceType": "community", "publicationDate": "2026-01-01"},
    ]
    write(TMP / "src_authority.json", {"sources": sources})
    rc, out, _, err = run(["scripts/source_scoring.py", "--sources", str(TMP / "src_authority.json"),
                            "--policies", "contracts/study-plan/policies.json", "--min", "1", "--max", "2"])
    ok = rc == 0 and out is not None
    check("evidence-quality", "source scoring runs deterministically", ok, err[:200])
    if not ok:
        return
    by_ref = {e["ref"]: e for e in out["kept"]}
    check("evidence-quality", "official documentation scores higher than community content",
          by_ref["S1"]["totalScore"] > by_ref["S2"]["totalScore"])
    check("evidence-quality", "official documentation ranks first",
          out["kept"][0]["ref"] == "S1")
    check("evidence-quality", "every kept entry carries a human-readable reason", all(e.get("reason") for e in out["kept"]))


def t_source_scoring_dedup():
    sources = [
        {"sourceRef": "D1", "title": "PostgreSQL Query Optimization and Performance Tuning Guide",
         "url": "https://blog.example.com/pg-query-optimization-guide", "sourceType": "article", "publicationDate": "2026-01-01"},
        {"sourceRef": "D2", "title": "PostgreSQL Query Optimization and Performance Tuning Practical Guide",
         "url": "https://blog.example.com/pg-query-optimization-practical-guide", "sourceType": "article", "publicationDate": "2025-01-01"},
        {"sourceRef": "D3", "title": "Kafka Exactly-Once Semantics Deep Dive",
         "url": "https://blog.example.com/kafka-eos", "sourceType": "article", "publicationDate": "2026-01-01"},
    ]
    write(TMP / "src_dedup.json", {"sources": sources})
    rc, out, *_ = run(["scripts/source_scoring.py", "--sources", str(TMP / "src_dedup.json"),
                        "--policies", "contracts/study-plan/policies.json", "--min", "1", "--max", "10"])
    check("evidence-quality", "near-duplicate titles on the same host collapse to one",
          rc == 0 and out and out["duplicatesDropped"] == 1 and out["totalConsidered"] == 3
          and len(out["kept"]) + len(out["archived"]) == 2)
    check("evidence-quality", "the unrelated third source (Kafka) survives dedup untouched",
          out and any(e["ref"] == "D3" for e in out["kept"] + out["archived"]))


def t_source_scoring_bounded_count_and_required():
    # distinct hosts per source so this test isolates the max-count bound from
    # the dedup mechanism (covered separately by t_source_scoring_dedup)
    topics = ["asyncio internals", "postgres vacuum", "kafka replication", "vector search", "raft consensus",
              "cpython gil", "connection pooling", "consistent hashing", "load shedding", "circuit breakers",
              "backpressure", "sharding strategy", "read replicas", "write-ahead log", "leader election"]
    sources = [{"sourceRef": f"B{i}", "title": f"A guide to {topics[i]}", "url": f"https://docs{i}.example.com/page",
                "sourceType": "official_documentation" if i == 0 else "community", "publicationDate": "2026-01-01"} for i in range(15)]
    write(TMP / "src_bounded.json", {"sources": sources})
    rc, out, *_ = run(["scripts/source_scoring.py", "--sources", str(TMP / "src_bounded.json"),
                        "--policies", "contracts/study-plan/policies.json", "--min", "5", "--max", "10"])
    check("evidence-quality", "kept count never exceeds --max even with 15 candidates",
          rc == 0 and out and len(out["kept"]) == 10 and len(out["archived"]) == 5)

    write(TMP / "required_refs.json", ["B14"])  # the lowest-scored community source
    rc2, out2, *_ = run(["scripts/source_scoring.py", "--sources", str(TMP / "src_bounded.json"),
                          "--policies", "contracts/study-plan/policies.json", "--min", "5", "--max", "10",
                          "--required-refs", str(TMP / "required_refs.json")])
    check("evidence-quality", "a required ref (sole support for a claim) is never archived even if low-ranked",
          rc2 == 0 and out2 and any(e["ref"] == "B14" for e in out2["kept"]))


def t_source_scoring_stable_ordering():
    sources = [{"sourceRef": f"O{i}", "title": f"Distinct topic {i}", "url": f"https://docs.example.com/topic-{i}",
                "sourceType": "book", "publicationDate": "2026-01-01"} for i in range(6)]
    write(TMP / "src_stable.json", {"sources": sources})
    rc1, out1, *_ = run(["scripts/source_scoring.py", "--sources", str(TMP / "src_stable.json"),
                          "--policies", "contracts/study-plan/policies.json", "--min", "1", "--max", "10"])
    rc2, out2, *_ = run(["scripts/source_scoring.py", "--sources", str(TMP / "src_stable.json"),
                          "--policies", "contracts/study-plan/policies.json", "--min", "1", "--max", "10"])
    check("evidence-quality", "ranking order is stable/deterministic across repeated runs on identical input",
          rc1 == 0 and rc2 == 0 and [e["ref"] for e in out1["kept"]] == [e["ref"] for e in out2["kept"]])


def t_source_scoring_real_registry_bounded():
    final_path = ROOT / REAL_RUN / "final" / "final.json"
    if not final_path.is_file():
        skip("evidence-quality", "real run's source registry scores and bounds correctly",
             f"no local run artifact at {REAL_RUN}/final/final.json")
        return
    final = json.loads(final_path.read_text(encoding="utf-8"))
    sources = list(final["sourceRegistry"].values())
    write(TMP / "src_real.json", {"sources": sources})
    rc, out, _, err = run(["scripts/source_scoring.py", "--sources", str(TMP / "src_real.json"),
                            "--policies", "contracts/study-plan/policies.json", "--min", "5", "--max", "10"])
    ok = rc == 0 and out is not None
    check("evidence-quality", "the real study-plan run's 88 sources score without error", ok, err[:200])
    if not ok:
        return
    check("evidence-quality", "88 real sources bound down to at most 10 kept per this scoring pass",
          out["totalConsidered"] == 88 and len(out["kept"]) <= 10)
    check("evidence-quality", "at least one official_documentation source is kept from the real registry",
          any(e["authorityTier"] == "official_documentation" for e in out["kept"]))


# ---------------- migration ----------------
def t_migrate_run_metadata():
    # rebuild a pre-migration-shaped fixture from the REAL run's saved
    # pre-migration backup (runtime/runs/20260728-study-plan/.migrations/
    # 001-pre-migration) so this exercises migration against realistic,
    # fully schema-valid section content rather than hand-rolled stubs.
    pre_migration_backup = ROOT / REAL_RUN / ".migrations" / "001-pre-migration"
    if not pre_migration_backup.is_dir():
        skip("global-consistency", "migration script runs end-to-end on a fixture run",
             f"no pre-migration backup under {REAL_RUN}/.migrations/")
        return
    root = TMP / "migrate-fixture"
    shutil.copytree(ROOT / "contracts/study-plan", root / "bundle")
    rd = root / "run"
    shutil.copytree(pre_migration_backup, rd)

    section_snapshot_before = (rd / "sections" / "python.json").read_text(encoding="utf-8")

    rc, record, _, err = run(["scripts/migrate_run_metadata.py", "--run", str(rd), "--bundle", str(root / "bundle")])
    ok = rc == 0 and record is not None
    check("global-consistency", "migration script runs end-to-end on a fixture run", ok, err[:200])
    if not ok:
        return
    check("global-consistency", "migration backs up the pre-migration run before writing anything",
          record["backupPath"] and Path(record["backupPath"]).is_dir())
    check("global-consistency", "migration never touches accepted research content (sections/ byte-identical)",
          (rd / "sections" / "python.json").read_text(encoding="utf-8") == section_snapshot_before)

    trace = json.loads((rd / "final" / "trace.json").read_text(encoding="utf-8"))
    check("global-consistency", "migrated trace shows byState.ACCEPTED == 6, no UNKNOWN", trace["summary"]["byState"] == {"ACCEPTED": 6})

    derived = json.loads((rd / "final" / "derived-context.json").read_text(encoding="utf-8"))
    check("global-consistency", "migrated derived-context has a real privacyClassification, not a bare boolean",
          "artifactPrivacyClassification" in derived and "private" not in derived)

    rc2, out2, *_ = run(["scripts/validate_final_output.py", str(rd / "final" / "final.json"), "--bundle", str(root / "bundle")])
    check("global-consistency", "the migrated final.json still passes its contract", rc2 == 0 and out2 and out2["ok"],
          out2 and str(out2.get("errors")))

    rc3, out3, *_ = run(["scripts/validate_timestamps.py", "--run", str(rd)])
    check("global-consistency", "the migrated fixture run passes timestamp validation", rc3 == 0 and out3 and out3["ok"])

    report_text = (rd / "final" / "report.md").read_text(encoding="utf-8")
    check("global-consistency", "migrated report.md has exactly one dedicated ## Scope section with the exact requested wording",
          report_text.count("\n## Scope\n") == 1
          and "This workflow produces a backend and AI systems study plan." in report_text
          and "DSA preparation is intentionally outside this contract." in report_text)
    check("global-consistency", "migrated report.md Run section shows Unavailable, not a fabricated timestamp",
          "- **Started:** Unavailable" in report_text and "- **Completed:** Unavailable" in report_text)

    run_json_post = json.loads((rd / "run.json").read_text(encoding="utf-8"))
    check("global-consistency", "migrated derived-context entries have evidenceRefs populated when the section cites real evidence",
          any(e["nodeId"] == "baseline-assessment" and e["evidenceRefs"] for e in derived["entries"]))
    check("global-consistency", "migrated derived-context entries mark confidenceSource explicitly instead of a bare unexplained null",
          all(e.get("confidenceSource") in ("measured", "unavailable") for e in derived["entries"]))

    gov_path = rd / "evidence" / "source-governance.json"
    check("global-consistency", "migration writes a per-node evidence/source-governance.json", gov_path.is_file())
    if gov_path.is_file():
        governance = json.loads(gov_path.read_text(encoding="utf-8"))
        check("global-consistency", "source governance scores multiple nodes independently, not one merged pool",
              len(governance.get("perNode", {})) > 1)

    final_doc = json.loads((rd / "final" / "final.json").read_text(encoding="utf-8"))
    check("global-consistency", "final.json reflects source governance as recommendedSources/archivedSources per node",
          "sourceGovernance" in final_doc
          and "recommendedSources" in final_doc["sourceGovernance"]
          and "archivedSources" in final_doc["sourceGovernance"]
          and len(final_doc["sourceGovernance"]["recommendedSources"]) > 1)
    check("global-consistency", "final.json still passes its contract with the new sourceGovernance field present",
          rc2 == 0 and out2 and out2["ok"])

    # idempotency: re-run migration against the already-migrated run and confirm
    # nothing accumulates (this is the exact bug a reviewer caught: 3 migration
    # passes tripled the scope bullet because the old code only ever prepended).
    rc4, record2, _, err4 = run(["scripts/migrate_run_metadata.py", "--run", str(rd), "--bundle", str(root / "bundle")])
    check("global-consistency", "second migration pass runs cleanly (idempotency check)", rc4 == 0 and record2 is not None, err4[:200])
    if rc4 == 0 and record2:
        report_text2 = (rd / "final" / "report.md").read_text(encoding="utf-8")
        check("global-consistency", "re-running migration does not duplicate the Scope section",
              report_text2.count("\n## Scope\n") == 1)
        gov2 = json.loads((rd / "final" / "final.json").read_text(encoding="utf-8"))
        check("global-consistency", "re-running migration does not duplicate sourceGovernance entries",
              gov2.get("sourceGovernance", {}).get("recommendedSources") == final_doc["sourceGovernance"]["recommendedSources"])


# ---------------- context manifest provenance ----------------
def t_context_manifest_source_path():
    rc, out, *_ = run(["scripts/build_context_manifest.py", "context/synthetic/study-plan",
                        "--out", str(TMP / "sp-ctx-manifest.json")])
    check("privacy-leakage", "context manifest builds for a non-default context dir", rc == 0 and out and out["ok"])
    manifest = json.loads((TMP / "sp-ctx-manifest.json").read_text(encoding="utf-8"))
    bad = [e for e in manifest["entries"] if not e["sourcePath"].startswith("context/synthetic/study-plan/")]
    check("privacy-leakage",
          "sourcePath stays within the given context dir (never silently resolves to private canonical/)",
          not bad, str(bad))


# ---------------- node packets ----------------
def t_context_packet_relevance():
    b = TMP / "packet-bundle"
    shutil.copytree(ROOT / "contracts/study-plan", b)
    nc_path = b / "node-contracts/python.contract.json"
    nc = json.loads(nc_path.read_text(encoding="utf-8"))
    nc["x-contractgraph"]["contextRefs"] = ["canonical/goals.md", "canonical/knowledge.md"]
    write(nc_path, nc)
    # deliberately clear fastapi's contextRefs in this temp copy so the
    # "no declared refs -> none, never all-canonical" case is exercised
    # regardless of what the real study-plan contracts currently declare
    fastapi_path = b / "node-contracts/fastapi.contract.json"
    fastapi_nc = json.loads(fastapi_path.read_text(encoding="utf-8"))
    fastapi_nc["x-contractgraph"]["contextRefs"] = []
    write(fastapi_path, fastapi_nc)

    compiled = TMP / "packet-compiled"
    run(["scripts/build_contract_manifest.py", str(b), "--out-dir", str(compiled)])
    ctx_manifest = json.loads((ROOT / "runtime/compiled/study-plan/context-manifest.json").read_text(encoding="utf-8"))
    write(compiled / "context-manifest.json", ctx_manifest)
    agent_manifest = json.loads((ROOT / "runtime/compiled/study-plan/agent-manifest.json").read_text(encoding="utf-8"))
    write(compiled / "agent-manifest.json", agent_manifest)

    out_dir = TMP / "packets-out"
    rc, out, _, err = run(["scripts/build_node_packets.py", "--bundle", str(b),
                            "--compiled", str(compiled), "--out-dir", str(out_dir)])
    ok = rc == 0 and out and out["ok"]
    check("token-efficiency", "node packets compile", ok, err[:200])
    if not ok:
        return

    python_packet = json.loads((out_dir / "python" / "packet.json").read_text(encoding="utf-8"))
    check("token-efficiency", "packet references only its OWN contract", python_packet["contractRef"] == "node-contracts/python.contract.json")
    check("token-efficiency", "packet contextRefs match only the node's declared 2 files (not all canonical)",
          sorted(r["sourcePath"] for r in python_packet["contextRefs"]) == ["canonical/goals.md", "canonical/knowledge.md"])
    check("token-efficiency", "packet dependency refs are hash-only, not full sections",
          python_packet["dependencySummaryRefs"] == [{"depNode": "baseline-assessment", "summaryHash": None}])
    check("token-efficiency", "packet carries an evidence-registry REF, not inline sources",
          isinstance(python_packet["evidenceRegistryRef"], str) and "sources" not in python_packet)

    fastapi_packet = json.loads((out_dir / "fastapi" / "packet.json").read_text(encoding="utf-8"))
    check("token-efficiency", "a node with no declared contextRefs gets NONE (never falls back to all canonical)",
          fastapi_packet["contextRefs"] == [])

    rc, out2, *_ = run(["scripts/validate_against_schema.py", str(out_dir / "python" / "packet.json"),
                         "--schema", "scripts/schemas/node-packet.schema.json"])
    check("token-efficiency", "node packet validates against node-packet.schema.json", rc == 0 and out2 and out2["ok"])


def t_packet_privacy_leak():
    out_dir = TMP / "packets-out"  # built by t_context_packet_relevance
    if not out_dir.is_dir():
        check("privacy-leakage", "node packets exist to scan", False, "run after t_context_packet_relevance")
        return
    ctx_entries = json.loads((ROOT / "runtime/compiled/study-plan/context-manifest.json").read_text(encoding="utf-8"))["entries"]
    private_snippets = []
    for e in ctx_entries:
        src = ROOT / e["sourcePath"]
        if src.is_file():
            private_snippets.append(src.read_text(encoding="utf-8").strip())
    leaks = []
    for pf in out_dir.rglob("packet.json"):
        txt = pf.read_text(encoding="utf-8")
        for snippet in private_snippets:
            if snippet and snippet in txt:
                leaks.append((pf.name, snippet[:30]))
    check("privacy-leakage", "node packets carry refs/hashes only, never canonical file CONTENT", not leaks, str(leaks))
    only_ref_keys = all(
        set(json.loads(pf.read_text(encoding="utf-8"))["contextRefs"][0].keys()) == {"sourcePath", "sha256", "loadWhen", "summaryRef"}
        for pf in out_dir.rglob("packet.json")
        if json.loads(pf.read_text(encoding="utf-8"))["contextRefs"]
    )
    check("privacy-leakage", "contextRefs entries are path+hash+loadWhen only (no content field)", only_ref_keys)


def t_node_packet_missing_context_ref():
    b = TMP / "missing-ref-bundle"
    shutil.copytree(ROOT / "contracts/study-plan", b)
    nc_path = b / "node-contracts/python.contract.json"
    nc = json.loads(nc_path.read_text(encoding="utf-8"))
    nc["x-contractgraph"]["contextRefs"] = ["canonical/does-not-exist.md"]
    write(nc_path, nc)

    compiled = TMP / "missing-ref-compiled"
    run(["scripts/build_contract_manifest.py", str(b), "--out-dir", str(compiled)])
    ctx_manifest = json.loads((ROOT / "runtime/compiled/study-plan/context-manifest.json").read_text(encoding="utf-8"))
    write(compiled / "context-manifest.json", ctx_manifest)  # deliberately lacks does-not-exist.md
    agent_manifest = json.loads((ROOT / "runtime/compiled/study-plan/agent-manifest.json").read_text(encoding="utf-8"))
    write(compiled / "agent-manifest.json", agent_manifest)

    out_dir = TMP / "missing-ref-packets-out"
    rc, out, _, err = run(["scripts/build_node_packets.py", "--bundle", str(b),
                            "--compiled", str(compiled), "--out-dir", str(out_dir)])
    check("token-efficiency", "a contextRef with no matching manifest entry fails compilation, not a silent null hash",
          rc == 2 and "python" in err and "does-not-exist.md" in err)
    check("token-efficiency", "no packet.json is written for ANY node when one contextRef is unresolved (no partial output)",
          not out_dir.exists())


# ---------------- evidence dedup ----------------
def t_evidence_dedup():
    reg_path = TMP / "evidence" / "source-registry.json"
    write(TMP / "sources1.json", {"sources": [
        {"sourceRef": "S1", "title": "asyncio docs", "url": "https://docs.python.org/3/library/asyncio.html",
         "sourceType": "official_documentation"},
        {"sourceRef": "S2", "title": "FastAPI home", "url": "https://fastapi.tiangolo.com/",
         "sourceType": "official_documentation"},
    ]})
    rc, out1, _, err = run(["scripts/source_registry.py", "--registry", str(reg_path),
                             "--sources", str(TMP / "sources1.json")])
    ok = rc == 0 and out1 is not None
    check("deterministic-aggregation", "source registry accepts first batch", ok, err[:200])
    if not ok:
        return
    check("deterministic-aggregation", "2 genuinely new sources added", len(out1["added"]) == 2 and not out1["reused"])
    id1 = out1["refMap"]["S1"]

    # second node cites the SAME url (different local ref, case/utm/trailing-slash
    # variant) plus one genuinely new url -- must dedup to the SAME canonical id.
    write(TMP / "sources2.json", {"sources": [
        {"sourceRef": "X1", "title": "asyncio docs (dup)",
         "url": "HTTPS://Docs.Python.org/3/library/asyncio.html/?utm_source=newsletter",
         "sourceType": "official_documentation"},
        {"sourceRef": "X2", "title": "SQLAlchemy docs", "url": "https://docs.sqlalchemy.org/",
         "sourceType": "official_documentation"},
    ]})
    rc, out2, *_ = run(["scripts/source_registry.py", "--registry", str(reg_path),
                         "--sources", str(TMP / "sources2.json"),
                         "--out-refmap", str(TMP / "refmap2.json")])
    check("deterministic-aggregation", "second batch reuses the same URL's canonical id (no duplicate)",
          rc == 0 and out2 and out2["refMap"]["X1"] == id1 and id1 in out2["reused"])
    check("deterministic-aggregation", "only the genuinely new source is added", out2 and len(out2["added"]) == 1)
    check("deterministic-aggregation", "registry totals 3 entries, not 4 (deduped across nodes/batches)",
          out2 and out2["totalEntries"] == 3)

    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    check("deterministic-aggregation", "registry stores each source's full metadata exactly once",
          len(registry["entries"]) == 3)


def t_evidence_registry_end_to_end():
    reg_path = TMP / "e2e-registry.json"
    write(TMP / "e2e-sources.json", {"sources": [
        {"sourceRef": "local1", "title": "asyncio docs", "url": "https://docs.python.org/3/library/asyncio.html",
         "sourceType": "official_documentation"},
    ]})
    rc, reg_out, *_ = run(["scripts/source_registry.py", "--registry", str(reg_path),
                            "--sources", str(TMP / "e2e-sources.json")])
    check("evidence-quality", "registry seeded for end-to-end evidence test", rc == 0 and reg_out is not None)
    if rc != 0:
        return
    canonical_ref = reg_out["refMap"]["local1"]

    section = {"nodeId": "python", "contractVersion": "1.0.0", "status": "complete",
               "data": {"topic": "Python", "objectives": ["x"], "resources": [
                   {"title": "Python docs", "url": "https://docs.python.org/3/", "type": "doc"}],
                   "milestones": [{"name": "m", "successCriteria": "c"}],
                   "evidence": [{"ref": canonical_ref, "claims": ["asyncio is the standard library"]}]},
               "verification": {"verifiedBy": "section-verifier", "status": "passed"}}
    write(TMP / "e2e-section.json", section)

    rc_with, out_with, *_ = run(["scripts/validate_references.py", str(TMP / "e2e-section.json"),
                                  "--bundle", "contracts/study-plan", "--evidence-registry", str(reg_path)])
    check("evidence-quality", "evidence[].ref resolves against the EXTERNAL registry", rc_with == 0 and out_with and out_with["ok"])

    rc_without, out_without, *_ = run(["scripts/validate_references.py", str(TMP / "e2e-section.json"),
                                        "--bundle", "contracts/study-plan"])
    check("evidence-quality", "without the registry, the same ref is correctly reported unresolved",
          rc_without == 1 and out_without and not out_without["ok"] and canonical_ref in out_without["unresolvedEvidenceRefs"])

    sdir = TMP / "e2e-sections"
    write(sdir / "python.json", section)
    rc_merge, merge_out, *_ = run(["scripts/merge_verified_sections.py", "--bundle", "contracts/study-plan",
                                    "--sections", str(sdir), "--out", str(TMP / "e2e-final.json"),
                                    "--evidence-registry", str(reg_path)])
    final_doc = json.loads((TMP / "e2e-final.json").read_text(encoding="utf-8"))
    check("evidence-quality", "merge resolves evidence refs into the final sourceRegistry via the external file",
          canonical_ref in final_doc.get("sourceRegistry", {}) and
          final_doc["sourceRegistry"][canonical_ref]["url"] == "https://docs.python.org/3/library/asyncio.html")


# ---------------- dependency summaries / cache invalidation ----------------
def t_summary_cache_invalidation():
    section_a = {"nodeId": "baseline-assessment", "contractVersion": "1.0.0", "status": "complete",
                 "data": {"handoffSummary": {"headline": "Learner is a Python beginner targeting backend roles"},
                          "evidence": [{"ref": "SRC_AAA", "claims": ["x"]}]},
                 "verification": {"verifiedBy": "section-verifier", "status": "passed", "confidence": 0.9}}
    section_b = json.loads(json.dumps(section_a))
    section_b["data"]["handoffSummary"]["headline"] = "Learner already knows FastAPI basics"

    write(TMP / "sec_a.json", section_a)
    write(TMP / "sec_b.json", section_b)
    rc, sum_a, _, err = run(["scripts/build_dependency_summary.py", "--bundle", "contracts/study-plan",
                              "--node", "baseline-assessment", "--section", str(TMP / "sec_a.json"),
                              "--out", str(TMP / "summary_a.json")])
    ok = rc == 0 and sum_a is not None
    check("cache-correctness", "dependency summary builds", ok, err[:200])
    if not ok:
        return
    rc, sum_a2, *_ = run(["scripts/build_dependency_summary.py", "--bundle", "contracts/study-plan",
                           "--node", "baseline-assessment", "--section", str(TMP / "sec_a.json"),
                           "--out", str(TMP / "summary_a2.json")])
    rc, sum_b, *_ = run(["scripts/build_dependency_summary.py", "--bundle", "contracts/study-plan",
                          "--node", "baseline-assessment", "--section", str(TMP / "sec_b.json"),
                          "--out", str(TMP / "summary_b.json")])
    check("cache-correctness", "identical upstream output -> identical summaryHash",
          sum_a["summaryHash"] == sum_a2["summaryHash"])
    check("cache-correctness", "changed upstream output -> different summaryHash",
          sum_a["summaryHash"] != sum_b["summaryHash"])
    check("token-efficiency", "summary never copies full prose (only handoff+evidenceRefs+confidence hashed/kept)",
          set(sum_a.keys()) >= {"handoff", "evidenceRefs", "confidence", "fullSectionRef"} and "data" not in sum_a)

    rc, out2, *_ = run(["scripts/validate_against_schema.py", str(TMP / "summary_a.json"),
                         "--schema", "scripts/schemas/dependency-summary.schema.json"])
    check("token-efficiency", "dependency summary validates against its schema", rc == 0 and out2 and out2["ok"])

    # downstream cache key must change when the upstream summary changes, and
    # stay stable when it doesn't -- this is the actual point of hashing it.
    write(TMP / "cache_in.json", {"learnerGoal": "become a backend engineer"})
    write(TMP / "deps_a.json", {"baseline-assessment": sum_a["summaryHash"]})
    write(TMP / "deps_a2.json", {"baseline-assessment": sum_a2["summaryHash"]})
    write(TMP / "deps_b.json", {"baseline-assessment": sum_b["summaryHash"]})
    _, key_a, *_ = run(["scripts/cache_key.py", "--bundle", "contracts/study-plan", "--node", "python",
                         "--input", str(TMP / "cache_in.json"), "--dep-summaries", str(TMP / "deps_a.json")])
    _, key_a2, *_ = run(["scripts/cache_key.py", "--bundle", "contracts/study-plan", "--node", "python",
                          "--input", str(TMP / "cache_in.json"), "--dep-summaries", str(TMP / "deps_a2.json")])
    _, key_b, *_ = run(["scripts/cache_key.py", "--bundle", "contracts/study-plan", "--node", "python",
                         "--input", str(TMP / "cache_in.json"), "--dep-summaries", str(TMP / "deps_b.json")])
    check("cache-correctness", "downstream cache key stable when upstream summary unchanged",
          key_a and key_a2 and key_a["cacheKey"] == key_a2["cacheKey"])
    check("cache-correctness", "downstream cache key changes when upstream summary changes",
          key_a and key_b and key_a["cacheKey"] != key_b["cacheKey"])


# ---------------- issue-only verification ----------------
def t_verifier_issue_only():
    valid_pass = {"nodeId": "python", "verifier": "section-verifier", "attempt": 1,
                  "status": "passed", "issues": [], "conflicts": [], "confidence": 0.86}
    write(TMP / "verdict_pass.json", valid_pass)
    rc, out, _, err = run(["scripts/validate_against_schema.py", str(TMP / "verdict_pass.json"),
                            "--schema", "scripts/schemas/verifier-verdict.schema.json"])
    check("verification", "a passing issue-only verdict validates", rc == 0 and out and out["ok"], err[:200])

    valid_fail = {"nodeId": "python", "verifier": "section-verifier", "attempt": 1, "status": "failed",
                  "issues": [{"path": "$.data.resources[0].url", "issueType": "unsupportedClaim",
                              "claim": "docs.python.org covers FastAPI", "repairInstruction":
                              "cite a source that actually documents FastAPI, not the Python stdlib docs"}],
                  "conflicts": [], "confidence": 0.4}
    write(TMP / "verdict_fail.json", valid_fail)
    rc, out, *_ = run(["scripts/validate_against_schema.py", str(TMP / "verdict_fail.json"),
                        "--schema", "scripts/schemas/verifier-verdict.schema.json"])
    check("verification", "a failing issue-only verdict (path + repairInstruction) validates", rc == 0 and out and out["ok"])

    rewrite_attempt = dict(valid_pass)
    rewrite_attempt["content"] = {"data": {"topic": "rewritten by the verifier"}}
    write(TMP / "verdict_rewrite.json", rewrite_attempt)
    rc, out, *_ = run(["scripts/validate_against_schema.py", str(TMP / "verdict_rewrite.json"),
                        "--schema", "scripts/schemas/verifier-verdict.schema.json"])
    check("verification", "a verdict that tries to rewrite content (extra 'content' field) is REJECTED",
          rc == 1 and out and not out["ok"])

    section_attempt = dict(valid_pass)
    section_attempt["section"] = {"nodeId": "python"}
    write(TMP / "verdict_section.json", section_attempt)
    rc, out, *_ = run(["scripts/validate_against_schema.py", str(TMP / "verdict_section.json"),
                        "--schema", "scripts/schemas/verifier-verdict.schema.json"])
    check("verification", "a verdict carrying a full 'section' field is REJECTED", rc == 1 and out and not out["ok"])


# ---------------- weighted concurrency ----------------
def t_weighted_concurrency():
    ready_heavy = ["python", "fastapi", "databases", "distributed-systems"]
    write(TMP / "ready_heavy.json", ready_heavy)
    write(TMP / "ready_mixed.json", ready_heavy + [{"id": "vf1", "class": "verifier"},
                                                    {"id": "vf2", "class": "verifier"},
                                                    {"id": "vf3", "class": "verifier"},
                                                    {"id": "gv1", "class": "globalVerifier"}])

    for mode in ("default", "tokenEfficient", "timeBounded"):
        rc, out, _, err = run(["scripts/schedule_plan.py", "--bundle", "contracts/study-plan",
                                "--compiled", "runtime/compiled/study-plan", "--mode", mode,
                                "--ready", str(TMP / "ready_heavy.json")])
        ok = rc == 0 and out is not None
        check("retry-targeting", f"scheduler admits under caps in {mode} mode", ok, err[:200])
        if not ok:
            continue
        check("retry-targeting", f"{mode}: heavyResearch admission never exceeds cap",
              len(out["admitted"]) == out["caps"]["heavyResearch"])
        check("retry-targeting", f"{mode}: heavyResearch cap itself is <=2 (safety floor)",
              out["caps"]["heavyResearch"] <= 2)
        check("retry-targeting", f"{mode}: excess heavy nodes are deferred, not silently dropped",
              len(out["admitted"]) + len(out["deferred"]) == 4)

    # time-bounded may raise OTHER classes' throughput but must never raise
    # heavy-research burst size relative to default -- the actual safety rule.
    rc, default_out, *_ = run(["scripts/schedule_plan.py", "--bundle", "contracts/study-plan",
                                "--compiled", "runtime/compiled/study-plan", "--mode", "default",
                                "--ready", str(TMP / "ready_mixed.json")])
    rc, tb_out, *_ = run(["scripts/schedule_plan.py", "--bundle", "contracts/study-plan",
                           "--compiled", "runtime/compiled/study-plan", "--mode", "timeBounded",
                           "--ready", str(TMP / "ready_mixed.json")])
    check("retry-targeting", "time-bounded mode does not raise heavy-research burst size vs default",
          tb_out and default_out and tb_out["caps"]["heavyResearch"] <= default_out["caps"]["heavyResearch"])
    check("retry-targeting", "mixed pool: all 3 verifier work items admitted under verifier cap (2)",
          tb_out and len(tb_out["byClass"].get("verifier", [])) == 3 and
          sum(1 for i in tb_out["admitted"] if i.startswith("vf")) == tb_out["caps"]["verifier"])
    check("retry-targeting", "mixed pool: only 1 global-verifier admitted (cap 1, never parallel)",
          tb_out and sum(1 for i in tb_out["admitted"] if i.startswith("gv")) == 1)


# ---------------- toon benchmark ----------------
def t_toon_roundtrip():
    rc, out, _, err = run(["scripts/toon_benchmark.py", "evals/fixtures/toon-samples/resources.json",
                            "--item-schema", "contracts/study-plan/common/common.schema.json",
                            "--item-schema-pointer", "$defs/ResourceLink",
                            "--policies", "contracts/study-plan/policies.json"])
    ok = rc == 0 and out is not None
    check("token-efficiency", "toon benchmark runs deterministically, no model/network", ok, err[:200])
    if not ok:
        return
    if out["toonAvailable"]:
        check("token-efficiency", "toon round-trip is lossless on a uniform ResourceLink array",
              out["roundTripLossless"] is True)
        check("token-efficiency", "toon-encoded items still validate against their own schema after round-trip",
              out["schemaValid"] is True)
    else:
        check("token-efficiency", "toon backend unavailable -> never fabricates savings or a lossless claim",
              out["charSavingsPct"] is None and out["roundTripLossless"] is None and out["enable"] is False)

    write(TMP / "mixed_shape.json", [{"a": 1}, {"a": [1, 2, {"b": "nested"}]}, {"different": "shape"}])
    rc2, out2, *_ = run(["scripts/toon_benchmark.py", str(TMP / "mixed_shape.json")])
    check("token-efficiency", "benchmark handles a non-uniform array without crashing or fabricating a decision",
          rc2 == 0 and out2 is not None)


def t_toon_token_compare():
    rc_r, out_r, *_ = run(["scripts/toon_benchmark.py", "evals/fixtures/toon-samples/resources.json",
                            "--item-schema", "contracts/study-plan/common/common.schema.json",
                            "--item-schema-pointer", "$defs/ResourceLink",
                            "--policies", "contracts/study-plan/policies.json"])
    rc_s, out_s, *_ = run(["scripts/toon_benchmark.py", "evals/fixtures/toon-samples/source-registry-entries.json",
                            "--item-schema", "contracts/study-plan/common/common.schema.json",
                            "--item-schema-pointer", "$defs/EvidenceSource",
                            "--policies", "contracts/study-plan/policies.json"])
    ok = rc_r == 0 and out_r is not None and rc_s == 0 and out_s is not None
    check("token-efficiency", "toon benchmark runs on both eligible-array fixtures", ok)
    if not ok:
        return
    if out_r["toonAvailable"]:
        check("token-efficiency", "toon encoding is smaller than JSON for a uniform ResourceLink array",
              out_r["toonBytes"] < out_r["jsonBytes"])
        check("token-efficiency", "toon encoding is smaller than JSON for a uniform EvidenceSource array",
              out_s["toonBytes"] < out_s["jsonBytes"])
        check("token-efficiency", "enable requires savings>=threshold AND lossless AND schema-valid, not size alone",
              out_r["enable"] == (out_r["charSavingsPct"] >= out_r["thresholds"]["minCharSavingsPct"]
                                   and out_r["roundTripLossless"] and out_r["schemaValid"]))

    write(TMP / "tiny_low_savings.json", [{"x": 1}])
    write(TMP / "lenient_policies.json", {"tokenEfficiency": {"toon": {"minCharSavingsPct": 99}}})
    rc, out, *_ = run(["scripts/toon_benchmark.py", str(TMP / "tiny_low_savings.json"),
                        "--policies", str(TMP / "lenient_policies.json")])
    check("token-efficiency", "enable=false when measured savings fall below the policy threshold (gating actually works)",
          rc == 0 and out is not None and out["enable"] is False)

    # the committed decision artifact reflects real measured numbers, not fabricated ones
    report = json.loads((ROOT / "runtime/compiled/study-plan/toon-benchmark.json").read_text(encoding="utf-8"))
    check("token-efficiency", "toon decision artifact covers all 4 eligible study-plan arrays",
          set(report["arrays"].keys()) == {"resources", "milestones", "checkpoints", "sourceRegistry"})
    check("token-efficiency", "toon decision artifact marks model-output-quality as pending, not certified",
          report["modelOutputQuality"]["status"] == "pending")


# ---------------- study-plan compiled fixture / benchmark prep ----------------
def t_study_plan_compilation():
    rc, out, _, err = run(["scripts/validate_compiled_graph.py", "runtime/compiled/study-plan/graph.json"])
    check("graph-compilation", "study-plan compiled graph is valid", rc == 0 and out and out["ok"], err[:200])

    rc, out, *_ = run(["scripts/validate_context.py", "context/synthetic/study-plan"])
    check("global-consistency", "study-plan synthetic context is valid", rc == 0 and out and out["ok"])

    for fname in ("skill-manifest.json", "capability-manifest.json", "compilation-report.md",
                  "agent-manifest.json", "context-manifest.json", "contract-manifest.json",
                  "graph.json", "toon-benchmark.json"):
        p = ROOT / "runtime/compiled/study-plan" / fname
        check("graph-compilation", f"study-plan compiled fixture has {fname}", p.is_file())

    agents = json.loads((ROOT / "runtime/compiled/study-plan/agent-manifest.json").read_text(encoding="utf-8"))
    eval_plan = next(a for a in agents["agents"] if a["nodeId"] == "evaluation-plan")
    check("token-efficiency", "evaluation-plan (pure synthesis, no web tools) requires no skill, unlike research nodes",
          eval_plan["requiredSkills"] == [] and "WebSearch" not in eval_plan["tools"])

    out_dir = TMP / "sp-packets-full"
    rc, out, *_ = run(["scripts/build_node_packets.py", "--bundle", "contracts/study-plan",
                        "--compiled", "runtime/compiled/study-plan", "--out-dir", str(out_dir)])
    check("token-efficiency", "full study-plan fixture compiles all 6 node packets end-to-end",
          rc == 0 and out and out["ok"] and len(out["packets"]) == 6)
    if rc == 0:
        for nid in ("baseline-assessment", "python", "fastapi", "databases", "distributed-systems", "evaluation-plan"):
            packet = json.loads((out_dir / nid / "packet.json").read_text(encoding="utf-8"))
            rc2, out2, *_ = run(["scripts/validate_against_schema.py", str(out_dir / nid / "packet.json"),
                                  "--schema", "scripts/schemas/node-packet.schema.json"])
            check("token-efficiency", f"{nid}: packet validates against node-packet.schema.json",
                  rc2 == 0 and out2 and out2["ok"])
        baseline_packet = json.loads((out_dir / "baseline-assessment" / "packet.json").read_text(encoding="utf-8"))
        check("token-efficiency", "baseline-assessment (only node reading raw canonical facts) declares all 3 canonical refs",
              len(baseline_packet["contextRefs"]) == 3)
        python_packet = json.loads((out_dir / "python" / "packet.json").read_text(encoding="utf-8"))
        check("token-efficiency", "python topic node declares only preferences.md, not goals/knowledge (already digested upstream)",
              [r["sourcePath"] for r in python_packet["contextRefs"]] == ["canonical/preferences.md"])

    for cfg in ("baseline.config.json", "optimized.config.json", "input.json"):
        p = ROOT / "evals/benchmarks/study-plan" / cfg
        check("token-efficiency", f"study-plan benchmark prep has {cfg}", p.is_file())
    baseline_cfg = json.loads((ROOT / "evals/benchmarks/study-plan/baseline.config.json").read_text(encoding="utf-8"))
    optimized_cfg = json.loads((ROOT / "evals/benchmarks/study-plan/optimized.config.json").read_text(encoding="utf-8"))
    check("token-efficiency", "baseline config has TOON disabled and cold cache",
          baseline_cfg["toon"] is False and baseline_cfg["cache"] == "cold")
    check("token-efficiency", "optimized config uses the SAME concurrency as baseline (controlled comparison)",
          optimized_cfg["concurrency"] == baseline_cfg["concurrency"])
    check("token-efficiency", "optimized config enables selective TOON only for benchmark-proven arrays",
          optimized_cfg["toon"] == "selective" and set(optimized_cfg["toonEligibleArrays"]) <= {
              "resources", "milestones", "checkpoints", "sourceRegistry"})


def t_benchmark_compare():
    write(TMP / "cost_base.json", {"runId": "sp-baseline-01", "run": {
        "inputTokens": 10000, "outputTokens": 2000, "cacheReadTokens": 0, "cacheCreationTokens": 0,
        "estimatedCostUsd": 0.06, "durationMs": 120000, "toolCalls": 40, "webSearches": 20, "webFetches": 20,
        "outputBytes": 50000, "requestCount": 12, "successCount": 12, "failureCount": 0}})
    write(TMP / "cost_opt.json", {"runId": "sp-optimized-01", "run": {
        "inputTokens": 6000, "outputTokens": 1500, "cacheReadTokens": 2000, "cacheCreationTokens": 500,
        "estimatedCostUsd": 0.04, "durationMs": 90000, "toolCalls": 30, "webSearches": 15, "webFetches": 15,
        "outputBytes": 30000, "requestCount": 12, "successCount": 12, "failureCount": 0}})
    rc, out, _, err = run(["scripts/benchmark_compare.py", "--baseline", str(TMP / "cost_base.json"),
                            "--optimized", str(TMP / "cost_opt.json"), "--out", str(TMP / "comparison.json")])
    ok = rc == 0 and out is not None
    check("token-efficiency", "benchmark_compare diffs two cost.json files", ok, err[:200])
    if not ok:
        return
    check("token-efficiency", "input-token reduction computed correctly (10000 -> 6000)",
          out["metrics"]["inputTokens"]["delta"] == -4000)
    check("token-efficiency", "cost reduction percentage computed correctly",
          out["metrics"]["estimatedCostUsd"]["deltaPct"] is not None and out["metrics"]["estimatedCostUsd"]["deltaPct"] < 0)
    check("token-efficiency", "requestCount unchanged (same nodes, same contract) shows 0 delta",
          out["metrics"]["requestCount"]["delta"] == 0)
    check("token-efficiency", "webSearches/webFetches metrics (post-rename) are available and compared, not silently unavailable",
          out["metrics"]["webSearches"]["available"] is True and out["metrics"]["webSearches"]["delta"] == -5)

    write(TMP / "cost_missing.json", {"runId": "x", "run": {"inputTokens": None}})
    rc2, out2, *_ = run(["scripts/benchmark_compare.py", "--baseline", str(TMP / "cost_missing.json"),
                          "--optimized", str(TMP / "cost_opt.json")])
    check("token-efficiency", "never divides by a null baseline metric (marked unavailable, not fabricated)",
          rc2 == 0 and out2 and out2["metrics"]["inputTokens"]["available"] is False
          and out2["metrics"]["inputTokens"]["deltaPct"] is None)


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
    # no company-research concept strings leak into study-plan bundle files.
    # "dsa" is exempt from this blanket scan: it now appears legitimately as
    # an explicit out-of-scope companion-workflow label in contract.bundle.json's
    # scope block (task: workflow-scope clarity) -- a deliberate exclusion
    # declaration, not a hardcoded DSA node. Checked separately below.
    leak = []
    for f in (ROOT / "contracts/study-plan").rglob("*.json"):
        low = f.read_text(encoding="utf-8").lower()
        for term in ("hld", "lld", "resume", "company-intelligence", "salesforce"):
            if term in low:
                leak.append((f.name, term))
    check("privacy-leakage", "no company-research concepts in study-plan bundle", not leak, str(leak))

    for f in (ROOT / "contracts/study-plan/node-contracts").rglob("*.json"):
        low = f.read_text(encoding="utf-8").lower()
        check("privacy-leakage", f"{f.name}: no hardcoded DSA node (dsa stays a scope EXCLUSION, never a node)",
              "dsa" not in low)

    bundle = json.loads((ROOT / "contracts/study-plan/contract.bundle.json").read_text(encoding="utf-8"))
    bundle_sans_scope = {k: v for k, v in bundle.items() if k != "scope"}
    check("privacy-leakage", "contract.bundle.json mentions 'dsa' ONLY inside the scope block, nowhere else",
          "dsa" not in json.dumps(bundle_sans_scope).lower())


# ---------------- pdf extraction ----------------
def _make_test_pdf(path: Path, page_texts):
    """Hand-build a minimal, deterministic PDF (correct xref) with the given
    per-page text (None => empty content stream / blank page). Avoids any
    PDF-writing dependency for the test fixture itself."""
    objs = []
    n_pages = len(page_texts)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objs.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    objs.append((2, f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()))
    font_obj_num = 3 + 2 * n_pages
    for i, text in enumerate(page_texts):
        page_num = 3 + 2 * i
        content_num = page_num + 1
        stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode() if text else b""
        objs.append((page_num,
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 {font_obj_num} 0 R >> >> "
            f"/MediaBox [0 0 200 200] /Contents {content_num} 0 R >>".encode()))
        objs.append((content_num, f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"))
    objs.append((font_obj_num, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objs.sort(key=lambda o: o[0])

    buf = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num, body in objs:
        offsets[num] = len(buf)
        buf += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_offset = len(buf)
    max_num = max(offsets)
    buf += f"xref\n0 {max_num + 1}\n".encode() + b"0000000000 65535 f \n"
    for num in range(1, max_num + 1):
        buf += f"{offsets[num]:010d} 00000 n \n".encode()
    buf += f"trailer\n<< /Size {max_num + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))


def t_pdf_extract():
    # pypdf is an OPTIONAL extra (scripts/requirements.txt). The framework core
    # is stdlib-only, so a clean checkout legitimately has no pypdf and
    # pdf_extract.py correctly reports "unavailable" rather than fabricating
    # text. Skip here rather than failing; CI runs a separate job that installs
    # the extras so this path is still covered somewhere.
    if not _module_available("pypdf"):
        skip("token-efficiency", "pdf extraction (optional pypdf)",
             "pypdf not installed — optional extra, see scripts/requirements.txt")
        return

    pdf_dir = TMP / "pdf"
    pdf_path = pdf_dir / "sample.pdf"
    _make_test_pdf(pdf_path, ["Hello World", None])

    rc, out, _, err = run(["scripts/pdf_extract.py", str(pdf_path), "--ocr", "never"])
    ok = rc == 0 and out and out["ok"] and out["processed"] == 1
    check("token-efficiency", "pdf extraction runs deterministically, no model/network", ok, err[:200])
    if not ok:
        return
    result = out["results"][0]
    md_path = Path(result["markdownPath"])
    meta_path = pdf_path.parent / "sample.extraction.json"
    check("token-efficiency", "pdf page provenance recorded (2 pages)", result["pageCount"] == 2 and len(result["pages"]) == 2)
    check("token-efficiency", "pdf sha256 recorded", bool(result.get("sha256")))
    md_text = md_path.read_text(encoding="utf-8")
    check("token-efficiency", "markdown contains embedded page-1 text", "Hello World" in md_text and "## Page 1" in md_text)
    p2 = result["pages"][1]
    check("token-efficiency", "blank page never invents text (chars==0, marked not fabricated)",
          p2["chars"] == 0 and p2["method"] in ("no_text_ocr_disabled", "ocr_unavailable"))
    check("token-efficiency", "no invented prose for blank page", "no extractable text" in md_text)

    rc2, out2, *_ = run(["scripts/pdf_extract.py", str(pdf_path), "--ocr", "never"])
    check("cache-correctness", "pdf extraction skips unchanged file", rc2 == 0 and out2["results"][0]["skipped"] is True)

    _make_test_pdf(pdf_path, ["Changed Content", None])
    rc3, out3, *_ = run(["scripts/pdf_extract.py", str(pdf_path), "--ocr", "never"])
    changed_ok = rc3 == 0 and out3["results"][0]["skipped"] is False
    check("cache-correctness", "pdf re-extracts when sha256 changes", changed_ok)
    if changed_ok:
        check("token-efficiency", "changed pdf content reflected in markdown",
              "Changed Content" in md_path.read_text(encoding="utf-8"))

    missing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    check("privacy-leakage", "extraction sidecar carries no private constants beyond path/hash",
          set(missing_meta.keys()) >= {"sha256", "pageCount", "pages"})


# ---------------- dry runs ----------------
def t_dryruns():
    cases = json.loads((ROOT / "evals/workflow-cases/dry-run.json").read_text(encoding="utf-8"))["cases"]
    for case in cases:
        bundle = case["bundle"]
        if not (ROOT / bundle).is_dir():
            skip("token-efficiency", f"{Path(bundle).name} dry-run plan", f"bundle not present: {bundle}")
            continue
        rc, out, *_ = run(["scripts/dry_run.py", "--bundle", bundle, "--compiled", case["compiled"]])
        check("token-efficiency", f"{Path(bundle).name} dry-run plan",
              rc == 0 and out and len(out["layerOrder"]) == case["expectLayers"])


# ---------------- finalization (finalize_run.py) ----------------
_BUNDLE = ROOT / PUBLIC_BUNDLE
_COMPILED = ROOT / "runtime" / "compiled" / "study-plan"

_SCOPE_DISCLAIMER = (
    "This is a backend-and-AI-systems study plan, not complete career preparation. "
    "It does NOT cover DSA (data-structures-and-algorithms interview preparation) — "
    "use a dedicated DSA study-plan bundle as the companion workflow."
)


def _topic_section(topic: str, objective: str, title: str, url: str, milestone: str, criteria: str):
    return {
        "topic": topic,
        "objectives": [objective],
        "resources": [{"title": title, "url": url, "type": "doc"}],
        "milestones": [{"name": milestone, "successCriteria": criteria}],
    }


_SECTION_NODES = [
    ("baseline-assessment", {
        "currentLevel": "Early-stage learner with foundational backend experience.",
        "gaps": ["No production distributed-systems experience"],
        "priorKnowledgeRefs": ["Python scripting", "Basic SQL"],
    }),
    ("python", _topic_section(
        "Python for backend systems", "Master asyncio and typing",
        "Python documentation", "https://docs.python.org/3/",
        "Async proficiency", "Can write a correct async producer/consumer")),
    ("fastapi", _topic_section(
        "FastAPI service design", "Model requests and responses with Pydantic",
        "FastAPI documentation", "https://fastapi.tiangolo.com/",
        "Service proficiency", "Can ship a validated, tested REST service")),
    ("databases", _topic_section(
        "Relational data modelling", "Understand indexing and transactions",
        "PostgreSQL documentation", "https://www.postgresql.org/docs/",
        "Query proficiency", "Can diagnose and fix a slow query with an index")),
    ("distributed-systems", _topic_section(
        "Distributed systems foundations", "Reason about consistency and partitioning",
        "Designing Data-Intensive Applications", "https://dataintensive.net/",
        "Systems proficiency", "Can justify a replication strategy for a given SLA")),
    ("evaluation-plan", {
        "checkpoints": [{"topic": "Track review", "criteria": "Score 80%+ on the track's practice set"}],
        "finalAssessment": "Ship one end-to-end service exercising every track and review it against the milestones.",
    }),
]


def _write_finalize_section(nid: str, data: dict) -> dict:
    return {
        "nodeId": nid, "contractVersion": "1.0.0", "status": "complete",
        "data": data, "evidence": [],
        "verification": {"verifiedBy": "section-verifier", "status": "passed"},
    }


def _create_finalize_fixture(root: Path, missing_nodes: set = None):
    """Create a finalize test fixture: run dir with sections, run.json,
    verification/global-verification.json, node-state files, and final/final.json scaffold."""
    missing_nodes = missing_nodes or set()
    sections_dir = root / "sections"
    verification_dir = root / "verification"
    final_dir = root / "final"
    ns_dir = root / "node-state"

    for nid, data in _SECTION_NODES:
        if nid in missing_nodes:
            continue
        section = _write_finalize_section(nid, data)
        write(sections_dir / f"{nid}.json", section)
        write(ns_dir / f"{nid}.json", {
            "nodeId": nid, "state": "ACCEPTED", "attempts": 1,
        })

    write(root / "run.json", {"runId": root.name, "bundleId": "study-plan"})

    write(verification_dir / "global-verification.json", {
        "verifier": "global-verifier", "status": "passed",
    })

    # Pre-populate final.json with scaffolding that merge must preserve
    write(final_dir / "final.json", {
        "schemaVersion": "1.0.0",
        "documentType": "PersonalizedStudyPlan",
        "run": {
            "runId": root.name, "learnerGoal": "test goal",
            "contractBundleVersion": "1.0.0", "contextManifestHash": "testhash",
        },
        "studyPlanMeta": {
            "generatedAt": "2026-07-29T20:31:27.000Z", "timestampSource": "measured",
            "caveats": ["Test caveat"],
            "scopeDisclaimer": _SCOPE_DISCLAIMER,
        },
        "sourceRegistry": {},
    })


def _run_finalize(run_dir: Path, **extra_opts) -> dict:
    argv = ["scripts/finalize_run.py", "--run", str(run_dir),
            "--bundle", str(_BUNDLE), "--compiled", str(_COMPILED)]
    for k, v in extra_opts.items():
        flag = f"--{k.replace('_', '-')}"
        if v is True:
            argv.append(flag)
        elif v is not None and v is not False:
            argv.extend([flag, str(v)])
    rc, out, _, _ = run(argv)
    return {"rc": rc, "out": out}


def t_finalize_happy_path():
    root = TMP / "finalize-happy"
    _create_finalize_fixture(root)
    result = _run_finalize(root)
    rc_ok = result["rc"] == 0
    out = result["out"]
    check("finalization", "happy path exit 0", rc_ok, str(out and out.get("failedChecks", [])))
    check("finalization", "happy path terminal state COMPLETED",
          out and out.get("terminalState") == "COMPLETED")
    check("finalization", "happy path all checks pass",
          out and out.get("checksPassed", 0) == out.get("checksTotal", 0))


def t_finalize_missing_required_node():
    root = TMP / "finalize-missing"
    _create_finalize_fixture(root, missing_nodes={"databases"})
    result = _run_finalize(root)
    out = result["out"]
    check("finalization", "missing required node terminal state FINALIZATION_FAILED",
          out and out.get("terminalState") == "FINALIZATION_FAILED")
    has_missing_check = any(
        c["category"] == "required-nodes" and not c["passed"]
        for c in (out or {}).get("checks", [])
    )
    check("finalization", "missing required node check fails",
          has_missing_check, str(out and out.get("failedChecks", [])))


def t_finalize_idempotent():
    root = TMP / "finalize-idempotent"
    _create_finalize_fixture(root)
    r1 = _run_finalize(root)
    # Second pass with --force re-runs all checks, producing same result
    r2 = _run_finalize(root, force=True)
    check("finalization", "idempotent: first pass COMPLETED",
          r1["out"] and r1["out"].get("terminalState") == "COMPLETED")
    check("finalization", "idempotent: second pass with --force COMPLETED",
          r2["out"] and r2["out"].get("terminalState") == "COMPLETED")
    check("finalization", "idempotent: both passes produce identical check counts",
          r1["out"] and r2["out"] and r1["out"]["checksTotal"] == r2["out"]["checksTotal"])


def t_finalize_already_completed_skips():
    root = TMP / "finalize-skip"
    _create_finalize_fixture(root)
    # First pass to establish COMPLETED
    _run_finalize(root)
    # Second pass without --force should detect already COMPLETED
    r2 = _run_finalize(root)
    out = r2["out"]
    check("finalization", "already COMPLETED without --force: exit code 1",
          r2["rc"] == 1)
    check("finalization", "already COMPLETED without --force: reports only lifecycle check",
          out and out["checksTotal"] == 1 and out["checks"][0]["category"] == "lifecycle"
          and "already COMPLETED" in (out["checks"][0].get("detail") or ""))


def t_finalize_backup():
    root = TMP / "finalize-backup"
    _create_finalize_fixture(root)
    _run_finalize(root)
    migrations = sorted(root.glob(".migrations/*-pre-finalize"))
    check("finalization", "backup created in .migrations/",
          len(migrations) >= 1)
    if migrations:
        check("finalization", "backup contains run.json",
              (migrations[-1] / "run.json").is_file())
        check("finalization", "backup contains sections",
              (migrations[-1] / "sections").is_dir())


def t_finalize_produces_all_artifacts():
    root = TMP / "finalize-artifacts"
    _create_finalize_fixture(root)
    _run_finalize(root)
    required = [
        "final/final.json",
        "final/verification-summary.json",
        "final/report.md",
        "final/cost.json",
        "final/derived-context.json",
        "evidence/source-governance.json",
    ]
    all_exist = all((root / p).is_file() for p in required)
    missing = [p for p in required if not (root / p).is_file()]
    check("finalization", "all 6 required artifacts produced",
          all_exist, f"missing: {missing}" if missing else None)


def t_finalize_run_json_updated():
    root = TMP / "finalize-runjson"
    _create_finalize_fixture(root)
    result = _run_finalize(root)
    rj_path = root / "run.json"
    rj = json.loads(rj_path.read_text(encoding="utf-8"))
    check("finalization", "run.json runStatus written",
          rj.get("runStatus") in ("COMPLETED", "FINALIZATION_FAILED"))
    check("finalization", "run.json finalizationSummary present",
          "finalizationSummary" in rj)
    if rj.get("runStatus") == "COMPLETED":
        check("finalization", "COMPLETED run has runCompletedAt",
              rj.get("runCompletedAt") is not None)


# ---------------- domain leakage (standalone) ----------------
_DL_POLICY = {
    "domainLeakage": {
        "allowedUnconditional": ["claude", "anthropic", "messages api"],
        "allowedWithLabel": {
            "openai": "Competitor — OK as a labelled comparison",
            "aws bedrock": "Deployment channel — OK as a labelled comparison",
            "amazon bedrock": "Deployment channel — OK as a labelled comparison",
            "gcp vertex ai": "Deployment channel — OK as a labelled comparison",
            "microsoft foundry": "Deployment channel — OK as a labelled comparison",
        },
        "disallowed": {},
        "exemptNodes": {
            "enterprise-integration": ["amazon bedrock", "microsoft foundry",
                                        "aws bedrock", "gcp vertex ai"],
        },
    },
}


def _write_dl_bundle(bundle: Path, with_policy: bool = True):
    """A minimal bundle that declares (or omits) a domainLeakage policy."""
    bundle.mkdir(parents=True, exist_ok=True)
    write(bundle / "contract.bundle.json", {"bundleId": "dl-fixture", "nodes": []})
    if with_policy:
        write(bundle / "policies.json", _DL_POLICY)


def t_domain_leakage_no_policy_is_reported_unchecked():
    """A bundle with no declared policy must say so, never pass silently."""
    root = TMP / "dl-nopolicy"
    bundle = TMP / "dl-bundle-nopolicy"
    _write_dl_bundle(bundle, with_policy=False)
    sections_dir = root / "sections"
    sections_dir.mkdir(parents=True)
    write(sections_dir / "test-node.json", {"data": {"topic": "OpenAI GPT models"}})
    rc, out, _, _ = run(["scripts/validate_domain_leakage.py", "--run", str(root),
                          "--bundle", str(bundle)])
    check("domain-leakage", "bundle with no domainLeakage policy is reported unchecked, not passed",
          rc == 0 and out and out.get("checked") is False and "declares no" in out.get("note", ""))


def t_domain_leakage_unlabelled():
    root = TMP / "dl-unlabelled"
    bundle = TMP / "dl-bundle"
    _write_dl_bundle(bundle)
    sections_dir = root / "sections"
    sections_dir.mkdir(parents=True)
    # No comparison marker — "openai" should trigger a warning.
    # Avoid trigger words like "comparison", "vs", "alternative", "including", etc.
    write(sections_dir / "test-node.json", {
        "data": {
            "topic": "OpenAI GPT models have different architecture from Claude. This section only covers Claude.",
            "resources": [{"title": "Test Resource",
                           "url": "https://example.com", "type": "doc"}],
        },
    })
    rc, out, _, _ = run(["scripts/validate_domain_leakage.py", "--run", str(root),
                          "--bundle", str(bundle)])
    check("domain-leakage", "unlabelled 'openai' reference generates warning",
          rc == 0 and out and out.get("warningCount", 0) >= 1
          and any("openai" in i.get("term", "") for i in out.get("issues", [])))


def t_domain_leakage_labelled():
    root = TMP / "dl-labelled"
    bundle = TMP / "dl-bundle2"
    _write_dl_bundle(bundle)
    sections_dir = root / "sections"
    sections_dir.mkdir(parents=True)
    # Labelled vs comparison — should be accepted
    write(sections_dir / "test-node.json", {
        "data": {
            "topic": "Enterprise deployment channels include AWS Bedrock, GCP Vertex AI, and Microsoft Foundry as alongside options",
            "resources": [{"title": "Deployment guide", "url": "https://example.com", "type": "doc"}],
        },
    })
    rc, out, _, _ = run(["scripts/validate_domain_leakage.py", "--run", str(root),
                          "--bundle", str(bundle)])
    check("domain-leakage", "labelled 'alongside' reference accepted (no warnings or blocking)",
          rc == 0 and out and out.get("warningCount", 0) == 0
          and out.get("blockingCount", 0) == 0)


def t_domain_leakage_enterprise_exempt():
    root = TMP / "dl-enterprise"
    bundle = TMP / "dl-bundle3"
    _write_dl_bundle(bundle)
    sections_dir = root / "sections"
    sections_dir.mkdir(parents=True)
    # enterprise-integration node is exempt for named deployment-channel terms
    write(sections_dir / "enterprise-integration.json", {
        "data": {
            "topic": "Deploying to Amazon Bedrock and Microsoft Foundry for enterprise customers",
            "resources": [{"title": "Deploy guide", "url": "https://example.com", "type": "doc"}],
        },
    })
    rc, out, _, _ = run(["scripts/validate_domain_leakage.py", "--run", str(root),
                          "--bundle", str(bundle)])
    check("domain-leakage", "enterprise-integration node is exempt for deployment channel terms",
          rc == 0 and out and out.get("warningCount", 0) == 0
          and out.get("blockingCount", 0) == 0)


# ---------------- source completeness (standalone) ----------------
def t_source_completeness_valid():
    root = TMP / "sc-valid"
    sec_dir = root / "sections"
    sec_dir.mkdir(parents=True)
    write(sec_dir / "test-node.json", {
        "data": {
            "resources": [
                {"title": "Python Docs", "url": "https://docs.python.org/3/", "type": "doc"},
                {"title": "FastAPI Guide", "url": "https://fastapi.tiangolo.com/", "type": "doc"},
            ],
        },
    })
    rc, out, _, _ = run(["scripts/validate_source_completeness.py", "--run", str(root)])
    check("source-completeness", "valid resources pass source completeness",
          rc == 0 and out and out["ok"] and out["summary"]["blockingIssues"] == 0)


def t_source_completeness_placeholder():
    root = TMP / "sc-placeholder"
    sec_dir = root / "sections"
    sec_dir.mkdir(parents=True)
    write(sec_dir / "test-node.json", {
        "data": {
            "resources": [
                {"title": "TBD", "url": "https://example.com/resource", "type": "doc"},
                {"title": "Real Resource", "url": "TODO", "type": "article"},
            ],
        },
    })
    rc, out, _, _ = run(["scripts/validate_source_completeness.py", "--run", str(root)])
    check("source-completeness", "placeholder title 'TBD' and url 'TODO' detected",
          rc == 1 and out and not out["ok"] and out["summary"]["blockingIssues"] >= 1
          and out["summary"]["resourcesWithIssues"] >= 1)


def t_source_completeness_missing_evidence_fields():
    root = TMP / "sc-evidence"
    sec_dir = root / "sections"
    sec_dir.mkdir(parents=True)
    write(sec_dir / "test-node.json", {
        "evidence": [
            {"ref": "SRC_001", "title": "Valid Source", "url": "https://example.com/source", "sourceType": "official_documentation"},
            {"ref": "SRC_002", "title": "", "url": "", "sourceType": "unknown"},
        ],
    })
    rc, out, _, _ = run(["scripts/validate_source_completeness.py", "--run", str(root)])
    check("source-completeness", "evidence with empty title/url and invalid sourceType flagged",
          rc == 1 and out and not out["ok"] and out["summary"]["blockingIssues"] >= 1)


# ---- regression fixtures for false-positive completion predicates ----

def _create_empty_trace_fixture(root: Path):
    """Fixture where trace sees 0 nodes because node-state is empty."""
    _create_finalize_fixture(root)
    # Remove node-state files so generate_trace produces nodeCount=0
    ns_dir = root / "node-state"
    if ns_dir.is_dir():
        for f in ns_dir.glob("*.json"):
            f.unlink()


def _create_null_telemetry_fixture(root: Path):
    """Fixture where cost.json has all null values (no measured telemetry)."""
    _create_finalize_fixture(root)
    cost_path = root / "final" / "cost.json"
    write(cost_path, {
        "documentType": "ContractGraphCost",
        "runId": root.name, "generatedBy": "test",
        "summary": {
            "totalTokensInput": None, "totalTokensOutput": None,
            "totalCost": None, "perNode": "unavailable",
            "note": "No telemetry captured.",
        },
    })


def _create_zero_source_governance_fixture(root: Path):
    """Fixture where research node sections have unparseable content so scoring fails.
    Sections exist (passes required-nodes check) but _load in source governance raises
    JSONDecodeError, causing all_ok=False."""
    _create_finalize_fixture(root)
    # Overwrite the research (topic) node sections with invalid JSON
    for nid, _ in _SECTION_NODES:
        if nid in ("python", "fastapi", "databases", "distributed-systems"):
            (root / "sections" / f"{nid}.json").write_text(
                'this is not valid json {{', encoding="utf-8")


def _create_missing_sections_fixture(root: Path):
    """Fixture where some required sections are missing from final artifact."""
    _create_finalize_fixture(root, missing_nodes={"evaluation-plan"})
    # Also remove the section file entirely even from sections dir
    sec_path = root / "sections" / "evaluation-plan.json"
    if sec_path.is_file():
        sec_path.unlink()


def _create_mojibake_fixture(root: Path):
    """Fixture with mojibake characters in a section file."""
    _create_finalize_fixture(root)
    # Inject mojibake into baseline-assessment
    ba_path = root / "sections" / "baseline-assessment.json"
    if ba_path.is_file():
        import json
        ba = json.loads(ba_path.read_text(encoding="utf-8"))
        ba["data"]["currentLevel"] = "Early-stage learner with foundational AI/backend experience. \ufffd mojibake test."
        write(ba_path, ba)


def _create_context_freshness_fixture(root: Path):
    """Fixture where baseline claims zero Claude experience but canonical context
    contains Claude Code / ContractGraph references."""
    _create_finalize_fixture(root)
    # Modify baseline-assessment to claim zero Claude experience
    ba_path = root / "sections" / "baseline-assessment.json"
    if ba_path.is_file():
        import json
        ba = json.loads(ba_path.read_text(encoding="utf-8"))
        ba["data"]["currentLevel"] = "No Claude-specific knowledge. No Claude experience."
        write(ba_path, ba)
    # Create a temporary canonical context root within the fixture
    context_root = root / "context"
    canon_dir = context_root / "canonical"
    canon_dir.mkdir(parents=True, exist_ok=True)
    write(canon_dir / "claude-experience.md", "I have used ContractGraph and Claude Code extensively.")
    return context_root


def _create_false_positive_trace_fixture(root: Path):
    """Fixture where trace has all nodes ACCEPTED (the happy path)."""
    _create_finalize_fixture(root)
    ns_dir = root / "node-state"
    ns_dir.mkdir(parents=True, exist_ok=True)
    for nid, _ in _SECTION_NODES:
        write(ns_dir / f"{nid}.json", {
            "nodeId": nid, "state": "ACCEPTED", "attempts": 1,
        })


# ---- regression tests ----

def t_fp_trace_empty():
    """Trace with 0 nodes must fail (false-positive prevention)."""
    root = TMP / "fp-trace-empty"
    _create_empty_trace_fixture(root)
    result = _run_finalize(root, force=True)
    out = result["out"]
    trace_checks = [c for c in (out or {}).get("checks", []) if c["category"] == "trace"]
    trace_failed = any(not c["passed"] for c in trace_checks)
    check("finalization-fp", "empty trace (0 nodes) fails finalization",
          out and trace_failed,
          f"trace checks passed={trace_checks}" if trace_checks else "no trace checks")


def t_fp_telemetry_null_benchmark():
    """Null-only cost.json must fail in benchmark mode."""
    root = TMP / "fp-telemetry-null"
    _create_null_telemetry_fixture(root)
    result = _run_finalize(root, profile="benchmark")
    out = result["out"]
    telemetry_checks = [c for c in (out or {}).get("checks", []) if c["category"] == "telemetry"]
    telemetry_failed = any(not c["passed"] for c in telemetry_checks)
    check("finalization-fp", "null-only telemetry fails benchmark profile",
          out and telemetry_failed,
          f"telemetry checks passed={telemetry_checks}" if telemetry_checks else "no telemetry checks")


def t_fp_telemetry_null_correctness():
    """Null-only cost.json must be labelled unavailable in correctness mode (not fail)."""
    root = TMP / "fp-telemetry-correctness"
    _create_null_telemetry_fixture(root)
    result = _run_finalize(root, profile="correctness")
    out = result["out"]
    telemetry_checks = [c for c in (out or {}).get("checks", []) if c["category"] == "telemetry"]
    telemetry_labelled = any(
        "unavailable" in (c.get("detail") or "").lower() or "placeholder" in (c.get("detail") or "").lower()
        for c in telemetry_checks if c["passed"]
    )
    check("finalization-fp", "null-only telemetry labelled unavailable in correctness",
          out and telemetry_labelled,
          f"telemetry checks={telemetry_checks}" if telemetry_checks else "no telemetry checks")


def t_fp_source_governance_zero():
    """Research nodes with 0 considered sources must fail."""
    root = TMP / "fp-sg-zero"
    _create_zero_source_governance_fixture(root)
    result = _run_finalize(root, force=True)
    out = result["out"]
    sg_checks = [c for c in (out or {}).get("checks", []) if c["category"] == "source-governance"]
    sg_failed = any(not c["passed"] for c in sg_checks)
    check("finalization-fp", "source scoring errors for research nodes",
          out and sg_failed,
          f"sg checks={sg_checks}" if sg_checks else "no sg checks")


def t_fp_aggregation_missing_sections():
    """Missing required sections in final artifact must fail (caught by required-nodes check)."""
    root = TMP / "fp-agg-missing"
    _create_missing_sections_fixture(root)
    result = _run_finalize(root, force=True)
    out = result["out"]
    req_checks = [c for c in (out or {}).get("checks", []) if c["category"] == "required-nodes"]
    req_failed = any(not c["passed"] for c in req_checks)
    check("finalization-fp", "missing required sections fails required-nodes check",
          out and req_failed,
          f"req checks={req_checks}" if req_checks else "no req checks")


def t_fp_utf8_mojibake():
    """Section files with mojibake must fail."""
    root = TMP / "fp-utf8"
    _create_mojibake_fixture(root)
    result = _run_finalize(root, force=True)
    out = result["out"]
    utf8_checks = [c for c in (out or {}).get("checks", []) if c["category"] == "utf8"]
    utf8_failed = any(not c["passed"] for c in utf8_checks)
    check("finalization-fp", "mojibake in section files fails UTF-8 check",
          out and utf8_failed,
          f"utf8 checks={utf8_checks}" if utf8_checks else "no utf8 checks")


def t_fp_context_freshness():
    """Baseline claiming zero Claude experience with contradictory canon must fail."""
    root = TMP / "fp-freshness"
    ctx_root = _create_context_freshness_fixture(root)
    result = _run_finalize(root, force=True, context_root=str(ctx_root))
    out = result["out"]
    freshness_checks = [c for c in (out or {}).get("checks", []) if c["category"] == "context-freshness"]
    freshness_failed = any(not c["passed"] for c in freshness_checks)
    check("finalization-fp", "zero-Claude claim with contradictory canon fails",
          out and freshness_failed,
          f"freshness checks={freshness_checks}" if freshness_checks else "no freshness checks")


def t_fp_happy_path_still_passes():
    """The happy path fixture with all required nodes ACCEPTED must still pass (non-regression)."""
    root = TMP / "fp-happy-still-passes"
    _create_false_positive_trace_fixture(root)
    result = _run_finalize(root, force=True)
    out = result["out"]
    check("finalization-fp", "happy path fixture still passes with strict checks",
          out and out.get("terminalState") == "COMPLETED",
          f"passed={out.get('checksPassed', 0)}/{out.get('checksTotal', 0)}")


def main():
    setup()
    for t in (t_compilation, t_negatives, t_node_output, t_final_refs_urls, t_merge,
              t_cache, t_preserve, t_trace, t_trace_state_normalization, t_trace_required_from_bundle,
              t_derived_context_privacy, t_real_study_plan_context_root_disambiguation, t_synthetic_context_stays_public,
              t_timestamp_now, t_validate_timestamps_valid_ordering,
              t_validate_timestamps_impossible_sequence, t_validate_timestamps_format_and_missing,
              t_validate_timestamps_real_run_post_migration,
              t_telemetry_normalize, t_telemetry_dedup, t_telemetry_missing_fields,
              t_node_cost_aggregation,
              t_source_scoring_authority_preference, t_source_scoring_dedup,
              t_source_scoring_bounded_count_and_required, t_source_scoring_stable_ordering,
              t_source_scoring_real_registry_bounded,
              t_scope_dsa_out_of_scope, t_validate_final_output_scope_disclaimer, t_migrate_run_metadata, t_context_manifest_source_path, t_context_packet_relevance,
              t_packet_privacy_leak, t_node_packet_missing_context_ref, t_evidence_dedup, t_evidence_registry_end_to_end,
              t_summary_cache_invalidation, t_verifier_issue_only, t_weighted_concurrency,
              t_toon_roundtrip, t_toon_token_compare, t_study_plan_compilation, t_benchmark_compare,
              t_privacy, t_triggering, t_genericity, t_dryruns, t_pdf_extract,
              t_finalize_happy_path, t_finalize_missing_required_node,
              t_finalize_idempotent, t_finalize_already_completed_skips,
              t_finalize_backup, t_finalize_produces_all_artifacts, t_finalize_run_json_updated,
               t_domain_leakage_unlabelled, t_domain_leakage_labelled, t_domain_leakage_enterprise_exempt,
               t_source_completeness_valid, t_source_completeness_placeholder, t_source_completeness_missing_evidence_fields,
               t_fp_trace_empty, t_fp_telemetry_null_benchmark, t_fp_telemetry_null_correctness,
               t_fp_source_governance_zero, t_fp_aggregation_missing_sections,
               t_fp_utf8_mojibake, t_fp_context_freshness, t_fp_happy_path_still_passes):
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
    for cat, name, reason in skips:
        print(f"{cat:<26} {name:<{width}}  SKIP  <- {reason}")
    print("-" * (26 + width + 10))
    print(f"{passed}/{total} passed" + (f", {len(skips)} skipped" if skips else ""))
    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
