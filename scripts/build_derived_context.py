#!/usr/bin/env python3
"""build_derived_context - deterministically build runtime/runs/<run-id>/final/derived-context.json
from accepted sections, with provenance-aware privacy metadata.

Privacy is never a bare boolean. Every entry gets a `privacyClassification` of
public | internal | private, computed from the node's own declared contextRefs
(contracts/<bundle>/node-contracts/<id>.contract.json x-contractgraph.contextRefs)
and inherited (dominant/"stickiest" wins) from its dependsOn chain.

IMPORTANT: a node contract's contextRefs are contract-relative literals like
"canonical/goals.md" -- IDENTICAL whether a run actually resolved that against
context/canonical/ (real personal data) or context/synthetic/<bundle>/canonical/
(synthetic demo data); the string alone cannot distinguish them, since both
context trees use the same "canonical/" subfolder convention. So:

  - when --context-root (or run.json's own "contextDir") is known: a node's
    OWN classification is "public" if that root's path contains a "synthetic"
    segment, "private" otherwise -- this is the AUTHORITATIVE signal.
  - when neither is available (legacy calls, or a caller that genuinely
    doesn't know which context tree was used): fall back to the more
    conservative ref-string heuristic -- any contextRef under canonical/ or
    private/, or matching a sensitive-content keyword (resume, goal, employ,
    compensation, skill, project, preference, experience, knowledge, certif)
    -> "private"; refs ALL under synthetic/ -> "public". This fallback is
    NEVER less restrictive than the context-root-aware path.
  - a node with no declared refs and no dependencies to inherit from -> "private"
    (fail-closed default; nothing on record proves it's safe to call public)
  - a node's FINAL classification is the most restrictive of its own classification
    and every dependency's final classification (private > internal > public):
    a synthesis node inherits privacy from whatever it was built on, even if it
    declares no canonical refs of its own.

Re-running against a prior derived-context.json (--existing) never downgrades a
classification that was already private/internal back to something less
restrictive -- only escalation is allowed.

Usage:
  python scripts/build_derived_context.py --bundle <dir> --run <run-dir>
      --out <run-dir>/final/derived-context.json [--existing <prior.json>]
      [--context-root <the --context dir the run actually used>]
Output: JSON summary (also written to --out). Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RANK = {"public": 0, "internal": 1, "private": 2}
_SENSITIVE_KEYWORDS = (
    "resume", "goal", "employ", "compensation", "skill", "project",
    "preference", "experience", "knowledge", "certif",
)


def _load(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _own_classification(context_refs: list, context_root: str = None) -> str | None:
    """A node contract's contextRefs are contract-relative literals like
    "canonical/goals.md" -- IDENTICAL whether the run actually resolved that
    against context/canonical/ (real data) or context/synthetic/<bundle>/canonical/
    (synthetic data). The string alone cannot tell them apart, so the actual
    --context-root the run used at runtime is the authoritative signal when
    given; the ref-string heuristic below is a secondary, more conservative
    fallback for callers that don't pass one (never LESS restrictive)."""
    if not context_refs:
        return None
    if context_root is not None:
        root_parts = Path(context_root).parts
        return "public" if "synthetic" in root_parts else "private"
    if all(r.startswith("synthetic/") for r in context_refs):
        return "public"
    for r in context_refs:
        low = r.lower()
        if r.startswith("canonical/") or r.startswith("private/"):
            return "private"
        if any(kw in low for kw in _SENSITIVE_KEYWORDS):
            return "private"
    return "internal"


def _classify_all(node_defs: dict, context_root: str = None) -> dict:
    """node_defs: {nodeId: {"contextRefs": [...], "dependsOn": [...]}}. Returns {nodeId: classification}."""
    cache = {}

    def classify(node_id, stack=frozenset()):
        if node_id in cache:
            return cache[node_id]
        if node_id in stack or node_id not in node_defs:
            return "private"  # cycle/unknown dep: fail closed, never crash
        node = node_defs[node_id]
        own = _own_classification(node.get("contextRefs", []), context_root)
        dep_classes = [classify(d, stack | {node_id}) for d in node.get("dependsOn", [])]
        candidates = ([own] if own else []) + dep_classes
        if not candidates:
            result = "private"
        else:
            result = max(candidates, key=lambda c: _RANK[c])
        cache[node_id] = result
        return result

    for nid in node_defs:
        classify(nid)
    return cache


def _evidence_refs(section: dict) -> list:
    # evidence[] is a TOP-LEVEL sibling of data (common.schema.json's node
    # contract shape: {nodeId, contractVersion, status, data, evidence,
    # verification}) -- looking inside data.evidence (a prior version of this
    # function did) always finds nothing and silently reports no evidence
    # even when the section cites plenty. A data.evidence fallback is kept
    # only for a hypothetical differently-shaped caller; the real path is top-level.
    top_level = section.get("evidence") or []
    nested = (section.get("data", {}) or {}).get("evidence") or []
    refs = top_level if top_level else nested
    return sorted({e.get("ref") for e in refs if isinstance(e, dict) and e.get("ref")})


def _confidence(section: dict) -> tuple:
    """Returns (confidence, confidenceSource) -- confidenceSource distinguishes
    a genuinely measured value from one that's absent because the upstream
    verification block never recorded one (these sections' verification is
    {verifiedBy, status, notes}, no numeric confidence field at all)."""
    ver = section.get("verification", {}) or {}
    conf = ver.get("confidence")
    if isinstance(conf, (int, float, str)):
        return conf, "measured"
    return None, "unavailable"


def _summary(section: dict, node_id: str) -> str:
    handoff = (section.get("data", {}) or {}).get("handoffSummary") or {}
    headline = handoff.get("headline")
    if isinstance(headline, str) and headline.strip():
        return headline.strip()
    return f"See sections/{node_id}.json for full detail."


def build(bundle_dir: Path, run_dir: Path, existing: dict | None, context_root: str = None) -> dict:
    bundle = _load(bundle_dir / "contract.bundle.json")
    node_defs = {}
    for n in bundle["nodes"]:
        contract = _load(bundle_dir / n["contract"])
        xc = contract.get("x-contractgraph", {})
        node_defs[n["nodeId"]] = {
            "contextRefs": xc.get("contextRefs", []),
            "dependsOn": xc.get("dependsOn", []),
            "aggregationPath": n["aggregationPath"],
        }

    run_json = {}
    rj = run_dir / "run.json"
    if rj.is_file():
        run_json = _load(rj)
    run_id = run_json.get("runId")
    # explicit --context-root wins; otherwise trust run.json's own record of
    # which context dir this run actually used, if it recorded one. Neither
    # present -> classification falls back to the conservative (always-private
    # for a "canonical/..." ref) literal-string heuristic in _own_classification.
    context_root = context_root or run_json.get("contextDir")
    classifications = _classify_all(node_defs, context_root)

    prior_by_node = {}
    if existing:
        for e in existing.get("entries", []):
            prior_by_node[e["nodeId"]] = e

    entries = []
    sections_dir = run_dir / "sections"
    node_state_dir = run_dir / "node-state"
    for node_id, ndef in sorted(node_defs.items()):
        sec_path = sections_dir / f"{node_id}.json"
        if not sec_path.is_file():
            continue  # not accepted / not produced -- no derived entry
        section = _load(sec_path)

        ns_path = node_state_dir / f"{node_id}.json"
        node_state = _load(ns_path) if ns_path.is_file() else {}
        created_at = node_state.get("completedAt")
        timestamp_source = "measured" if created_at else "unavailable"

        classification = classifications.get(node_id, "private")
        prior = prior_by_node.get(node_id)
        if prior and prior.get("privacyClassification") in _RANK:
            classification = max(classification, prior["privacyClassification"], key=lambda c: _RANK[c])

        confidence, confidence_source = _confidence(section)
        entries.append({
            "nodeId": node_id,
            "aggregationPath": ndef["aggregationPath"],
            "privacyClassification": classification,
            "sourceContextRefs": sorted(ndef["contextRefs"]),
            "sourceRunId": run_id,
            "sourceNodeId": node_id,
            "evidenceRefs": _evidence_refs(section),
            "confidence": confidence,
            "confidenceSource": confidence_source,
            "createdAt": created_at,
            "timestampSource": timestamp_source,
            "expiresAt": None,
            "freshnessBasis": None,
            "contractVersion": section.get("contractVersion"),
            "summary": _summary(section, node_id),
        })

    artifact_classification = "public"
    if entries:
        artifact_classification = max((e["privacyClassification"] for e in entries), key=lambda c: _RANK[c])

    generated_at = run_json.get("completedAt") or run_json.get("runCompletedAt")
    return {
        "documentType": "ContractGraphDerivedContext",
        "version": "2.0.0",
        "runId": run_id,
        "bundleId": bundle.get("bundleId"),
        "generatedAt": generated_at,
        "timestampSource": "measured" if generated_at else "unavailable",
        "generatedBy": "build_derived_context.py",
        "entries": entries,
        "artifactPrivacyClassification": artifact_classification,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--bundle": None, "--run": None, "--out": None, "--existing": None, "--context-root": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--bundle"] or not opts["--run"]:
        print("usage: build_derived_context.py --bundle <dir> --run <run-dir> "
              "--out <path> [--existing <prior-derived-context.json>] [--context-root <dir>]", file=sys.stderr)
        return 2
    existing = None
    if opts["--existing"] and Path(opts["--existing"]).is_file():
        existing = _load(opts["--existing"])
    try:
        doc = build(Path(opts["--bundle"]), Path(opts["--run"]), existing, opts["--context-root"])
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    out_path = Path(opts["--out"]) if opts["--out"] else (Path(opts["--run"]) / "final" / "derived-context.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": out_path.as_posix(), "entryCount": len(doc["entries"]),
                       "artifactPrivacyClassification": doc["artifactPrivacyClassification"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
