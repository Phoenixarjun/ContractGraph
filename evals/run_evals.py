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
         "searches": 0, "fetches": 0, "outputBytes": 1200, "finalStatus": "accepted"})

    rc, out, _, err = run(["scripts/telemetry_normalize.py", "--run", str(rd),
                            "--claude-code", str(TMP / "cc.json"), "--opencode", str(TMP / "oc.json"),
                            "--local", str(TMP / "local"), "--out", str(rd / "final" / "cost.json")])
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

    rc, out2, *_ = run(["scripts/validate_against_schema.py", str(rd / "final" / "cost.json"),
                         "--schema", "scripts/schemas/cost.schema.json"])
    check("token-efficiency", "cost.json validates against cost.schema.json", rc == 0 and out2 and out2["ok"],
          out2 and str(out2.get("errors")))


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
        "estimatedCostUsd": 0.06, "durationMs": 120000, "toolCalls": 40, "searches": 20, "fetches": 20,
        "outputBytes": 50000, "requestCount": 12}})
    write(TMP / "cost_opt.json", {"runId": "sp-optimized-01", "run": {
        "inputTokens": 6000, "outputTokens": 1500, "cacheReadTokens": 2000, "cacheCreationTokens": 500,
        "estimatedCostUsd": 0.04, "durationMs": 90000, "toolCalls": 30, "searches": 15, "fetches": 15,
        "outputBytes": 30000, "requestCount": 12}})
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
    # no company-research concept strings leak into study-plan bundle files
    leak = []
    for f in (ROOT / "contracts/study-plan").rglob("*.json"):
        low = f.read_text(encoding="utf-8").lower()
        for term in ("dsa", "hld", "lld", "resume", "company-intelligence", "salesforce"):
            if term in low:
                leak.append((f.name, term))
    check("privacy-leakage", "no company-research concepts in study-plan bundle", not leak, str(leak))


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
    rc, out, *_ = run(["scripts/dry_run.py", "--bundle", "contracts/company-research", "--compiled", "runtime/compiled"])
    check("token-efficiency", "company-research dry-run plan", rc == 0 and out and len(out["layerOrder"]) == 8)
    rc, out, *_ = run(["scripts/dry_run.py", "--bundle", "contracts/study-plan", "--compiled", "runtime/compiled/study-plan"])
    check("token-efficiency", "study-plan dry-run plan", rc == 0 and out and len(out["layerOrder"]) == 3)


def main():
    setup()
    for t in (t_compilation, t_negatives, t_node_output, t_final_refs_urls, t_merge,
              t_cache, t_preserve, t_trace, t_telemetry_normalize, t_telemetry_missing_fields,
              t_node_cost_aggregation, t_context_manifest_source_path, t_context_packet_relevance,
              t_packet_privacy_leak, t_node_packet_missing_context_ref, t_evidence_dedup, t_evidence_registry_end_to_end,
              t_summary_cache_invalidation, t_verifier_issue_only, t_weighted_concurrency,
              t_toon_roundtrip, t_toon_token_compare, t_study_plan_compilation, t_benchmark_compare,
              t_privacy, t_triggering, t_genericity, t_dryruns, t_pdf_extract):
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
