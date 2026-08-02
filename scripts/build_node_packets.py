#!/usr/bin/env python3
"""build_node_packets - compile a minimal per-node execution packet for every
node in a bundle: this node's own contract only, declared canonical-context
refs (path + sha256, never full content), dependency-summary refs (hash only,
never a full upstream section), an evidence-registry ref, required skills, a
token/search budget, and output instructions. Backs the "node-specific context
packets" step CLAUDE.md's init flow is missing today.

Reuses the same compiled artifacts as dry_run.py (graph.json, agent-manifest,
context-manifest) plus each node contract's own `x-contractgraph.contextRefs`
-- an explicit list of canonical-context paths (relative to the context
manifest's contextDir) this node actually needs. Absent means NO canonical
context, never "all canonical" as a fallback -- a node that truly needs no
canonical file simply gets an empty contextRefs list. Deterministic; no model,
no network.

Usage:
  python scripts/build_node_packets.py --bundle <dir> [--compiled runtime/compiled/study-plan]
      [--out-dir <compiled>/node-packets]
Output: JSON summary {ok, packets: [{nodeId, path, packetHash}, ...]}.
Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from hash_content import sha256_file, sha256_json
from dry_run import TIER_TOKENS  # same per-tier budget assumptions dry_run uses


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _concurrency_class(node_id: str, agent: dict) -> str:
    if "global-verifier" in node_id:
        return "globalVerifier"
    if "verifier" in node_id:
        return "verifier"
    tools = set(agent.get("tools", []))
    if {"WebSearch", "WebFetch"} & tools:
        return "heavyResearch"
    return "lightSynthesis"


def build(bundle_dir: Path, compiled: Path, out_dir: Path) -> dict:
    bundle = _load(bundle_dir / "contract.bundle.json")
    graph = _load(compiled / "graph.json")
    agents = _load(compiled / "agent-manifest.json") or {"agents": []}
    ctx_manifest = _load(compiled / "context-manifest.json") or {"entries": []}
    policies = _load(bundle_dir / "policies.json") or {}
    if bundle is None:
        raise FileNotFoundError(f"no contract bundle at {bundle_dir/'contract.bundle.json'}")
    if graph is None:
        raise FileNotFoundError(f"no compiled graph at {compiled/'graph.json'} -- run /contractgraph:init first")

    ctx_by_path = {e["path"]: e for e in ctx_manifest.get("entries", [])}
    agent_by_node = {a["nodeId"]: a for a in agents.get("agents", [])}
    deps = graph.get("dependencies", {})
    evidence_rules = sorted(k for k, v in policies.get("evidence", {}).items() if v is True)

    node_contracts = {}
    unresolved = []
    for node in bundle.get("nodes", []):
        nid = node["nodeId"]
        contract_path = bundle_dir / node["contract"]
        contract = _load(contract_path)
        if contract is None:
            raise FileNotFoundError(f"node contract missing for '{nid}': {contract_path}")
        node_contracts[nid] = contract
        for path in contract.get("x-contractgraph", {}).get("contextRefs", []):
            if path not in ctx_by_path:
                unresolved.append({"nodeId": nid, "contextRef": path})

    if unresolved:
        lines = "\n".join(f"  - node '{u['nodeId']}' declares contextRefs entry '{u['contextRef']}', "
                           f"which is not in the indexed canonical context" for u in unresolved)
        raise FileNotFoundError(
            "node packet compilation blocked -- these declared canonical-context files are "
            "missing or not yet indexed (add the file under the context directory, then re-run "
            f"build_context_manifest.py before retrying):\n{lines}"
        )

    packets = []
    for node in bundle.get("nodes", []):
        nid = node["nodeId"]
        contract_path = bundle_dir / node["contract"]
        contract = node_contracts[nid]
        xc = contract.get("x-contractgraph", {})
        agent = agent_by_node.get(nid, {})
        model = agent.get("model", "sonnet")

        context_refs = [
            {
                "sourcePath": path,
                "sha256": ctx_by_path[path]["sha256"],
                "loadWhen": "summary",
                "summaryRef": None,
            }
            for path in xc.get("contextRefs", [])
        ]

        dependency_summary_refs = [
            {"depNode": d, "summaryHash": None} for d in sorted(deps.get(nid, []))
        ]

        packet = {
            "documentType": "ContractGraphNodePacket",
            "nodeId": nid,
            "contractRef": node["contract"],
            "contractHash": sha256_file(contract_path),
            "policySummary": {
                "model": model,
                "concurrencyClass": _concurrency_class(nid, agent),
                "freshnessDaysRelevant": policies.get("freshnessDays", {}),
                "evidenceRules": evidence_rules,
                "retry": {
                    "max": policies.get("execution", {}).get("maxRetriesPerNode", 2),
                    "failedOnly": policies.get("execution", {}).get("retryFailedNodesOnly", True),
                },
            },
            "contextRefs": context_refs,
            "dependencySummaryRefs": dependency_summary_refs,
            "evidenceRegistryRef": "runtime/runs/<run-id>/evidence/source-registry.json",
            "skills": agent.get("requiredSkills", []),
            "budget": {
                "tokenBudget": TIER_TOKENS.get(model, 25000),
                "searchBudget": agent.get("searchBudget"),
            },
            "outputInstructions": {
                "outputPath": f"sections/{nid}.json",
                "schemaRef": node["contract"],
                "requiredEvidence": "claim-level" if policies.get("evidence", {}).get("requireClaimLevelEvidence") else None,
                "stopConditions": xc.get("completionRules", []),
            },
        }
        packet["packetHash"] = sha256_json(packet)

        out_path = out_dir / nid / "packet.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        packets.append({"nodeId": nid, "path": out_path.as_posix(), "packetHash": packet["packetHash"]})

    return {"ok": True, "bundle": bundle_dir.as_posix(), "outDir": out_dir.as_posix(), "packets": packets}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--bundle": "contracts/study-plan", "--compiled": "runtime/compiled/study-plan", "--out-dir": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    compiled = Path(opts["--compiled"])
    out_dir = Path(opts["--out-dir"]) if opts["--out-dir"] else compiled / "node-packets"
    try:
        out = build(Path(opts["--bundle"]), compiled, out_dir)
    except (OSError, json.JSONDecodeError, FileNotFoundError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
