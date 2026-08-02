#!/usr/bin/env python3
"""telemetry_normalize - normalize token/cost telemetry from one or more
runtime-specific sources into the canonical shapes:
  runtime/runs/<id>/telemetry/requests.jsonl  (one RequestRecord per line, raw)
  runtime/runs/<id>/final/cost.json           (the same records + aggregates)

Sources (any combination, all optional):
  --claude-code FILE  Claude Code / OTEL usage export (JSON: {"records":[...]}
                       or a bare list). Fields read (all optional, aliases ok):
                       model, usage.{input_tokens,output_tokens,
                       cache_read_input_tokens,cache_creation_input_tokens},
                       duration_ms, tool_calls, searches/webSearches,
                       fetches/webFetches, output_bytes, final_status/status,
                       started_at/completed_at, session_id,
                       metadata.{node,purpose,agent,skill,attempt}.
  --opencode FILE      OpenCode session export/stats/message-usage JSON
                       ({"messages":[...]} or a bare list). Same shape, plus
                       OpenAI-style usage.{promptTokens,completionTokens}.
  --local DIR          Directory of local per-call JSON records already close
                       to the canonical RequestRecord shape -- the only source
                       that reliably knows ContractGraph node/purpose/agent/
                       skill/attempt without a metadata passthrough.

Never fabricates a missing metric: any field a source did not provide is
written as null and marked false in that record's `available` map (and named
in `unavailableFields`). Purpose defaults to "unknown" (a true statement)
rather than a guessed category.

`requestId` is a deterministic content hash (runtime+model+node+purpose+
attempt+agent+skill+every numeric metric+status) -- re-running the normalizer
over the same inputs is idempotent, AND the exact same underlying event
captured twice (e.g. a parent transcript export and a subagent-local record
both reporting the identical call) collapses to one record instead of double-
counting. Exact-duplicate requestIds are dropped after the first occurrence;
`dedupedCount` in the output reports how many were dropped.

Aggregates (byNode/byModel/byPurpose/byAttempt/run) sum only non-null values;
`coverage` reports how many requests actually carried each metric.

Cost is ESTIMATED from scripts/model_prices.json (static reference prices,
not fetched live) only when both a recognizable model tier and token counts
are available; otherwise estimatedCostUsd stays null -- and is always a
provider-list-price estimate, never a provider-reported actual charge.

Usage:
  python scripts/telemetry_normalize.py --run <run-dir>
      [--claude-code FILE] [--opencode FILE] [--local DIR]
      [--prices scripts/model_prices.json] [--out <run-dir>/final/cost.json]
      [--requests-out <run-dir>/telemetry/requests.jsonl]
Output: the written cost.json (also printed). Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from hash_content import sha256_json

NUMERIC_FIELDS = [
    "inputTokens", "outputTokens", "cacheReadTokens", "cacheCreationTokens",
    "durationMs", "toolCalls", "webSearches", "webFetches", "outputBytes",
]
TIMESTAMP_FIELDS = ["startedAt", "completedAt"]


def _get(d, *paths):
    """Return the first present, non-null value among dotted-path aliases."""
    for path in paths:
        cur = d
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


def _tier(model):
    if not model:
        return None
    m = str(model).lower()
    for tier in ("haiku", "sonnet", "opus"):
        if tier in m:
            return tier
    return None


def _cost(prices, tier, input_tokens, output_tokens, cache_read, cache_creation):
    if tier is None or tier not in prices.get("models", {}):
        return None
    if input_tokens is None and output_tokens is None:
        return None
    p = prices["models"][tier]
    total = 0.0
    if input_tokens is not None:
        total += (input_tokens / 1_000_000) * p["input"]
    if output_tokens is not None:
        total += (output_tokens / 1_000_000) * p["output"]
    if cache_read is not None:
        total += (cache_read / 1_000_000) * p.get("cacheRead", 0)
    if cache_creation is not None:
        total += (cache_creation / 1_000_000) * p.get("cacheWrite", 0)
    return round(total, 6)


def _record(run_id, runtime, telemetry_source, model, session_id, agent, skill, purpose, node, attempt,
            input_tokens, output_tokens, cache_read, cache_creation,
            duration_ms, tool_calls, web_searches, web_fetches, output_bytes,
            started_at, completed_at, status, prices):
    tier = _tier(model)
    cost = _cost(prices, tier, input_tokens, output_tokens, cache_read, cache_creation)
    values = {
        "inputTokens": input_tokens, "outputTokens": output_tokens,
        "cacheReadTokens": cache_read, "cacheCreationTokens": cache_creation,
        "estimatedCostUsd": cost, "durationMs": duration_ms,
        "toolCalls": tool_calls, "webSearches": web_searches, "webFetches": web_fetches,
        "outputBytes": output_bytes,
    }
    available = {k: v is not None for k, v in values.items()}
    unavailable_fields = sorted(k for k, ok in available.items() if not ok)
    request_id = "REQ_" + sha256_json({
        "runtime": runtime, "model": model, "agent": agent, "skill": skill,
        "purpose": purpose or "unknown", "node": node, "attempt": attempt,
        "status": status, **values,
    })[:16].upper()
    return {
        "requestId": request_id, "runId": run_id, "nodeId": node, "attempt": attempt,
        "runtime": runtime, "sessionId": session_id, "agent": agent, "skill": skill,
        "model": model, "purpose": purpose or "unknown",
        **values,
        "startedAt": started_at, "completedAt": completed_at,
        "status": status, "telemetrySource": telemetry_source,
        "unavailableFields": unavailable_fields, "available": available,
    }


def _from_claude_code(path: Path, run_id, prices) -> list:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("records", raw.get("requests", []))
    out = []
    for r in items:
        meta = r.get("metadata", {}) or {}
        out.append(_record(
            run_id, "claude-code", "claude-code-otel-export", _get(r, "model"),
            _get(r, "session_id", "sessionId"),
            meta.get("agent"), meta.get("skill"), meta.get("purpose"), meta.get("node"), meta.get("attempt"),
            _get(r, "usage.input_tokens", "usage.inputTokens", "inputTokens"),
            _get(r, "usage.output_tokens", "usage.outputTokens", "outputTokens"),
            _get(r, "usage.cache_read_input_tokens", "usage.cacheReadTokens", "cacheReadTokens"),
            _get(r, "usage.cache_creation_input_tokens", "usage.cacheCreationTokens", "cacheCreationTokens"),
            _get(r, "duration_ms", "durationMs"),
            _get(r, "tool_calls", "toolCalls"),
            _get(r, "web_searches", "webSearches", "searches"), _get(r, "web_fetches", "webFetches", "fetches"),
            _get(r, "output_bytes", "outputBytes"),
            _get(r, "started_at", "startedAt"), _get(r, "completed_at", "completedAt"),
            _get(r, "final_status", "finalStatus", "status"),
            prices,
        ))
    return out


def _from_opencode(path: Path, run_id, prices) -> list:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("messages", raw.get("records", []))
    out = []
    for r in items:
        meta = r.get("metadata", {}) or {}
        out.append(_record(
            run_id, "opencode", "opencode-session-export", _get(r, "model"),
            _get(r, "session_id", "sessionId"),
            meta.get("agent"), meta.get("skill"), meta.get("purpose"), meta.get("node"), meta.get("attempt"),
            _get(r, "usage.input_tokens", "usage.inputTokens", "usage.promptTokens", "inputTokens"),
            _get(r, "usage.output_tokens", "usage.outputTokens", "usage.completionTokens", "outputTokens"),
            _get(r, "usage.cache_read_input_tokens", "usage.cacheReadTokens", "cacheReadTokens"),
            _get(r, "usage.cache_creation_input_tokens", "usage.cacheCreationTokens", "cacheCreationTokens"),
            _get(r, "duration_ms", "durationMs"),
            _get(r, "tool_calls", "toolCalls"),
            _get(r, "web_searches", "webSearches", "searches"), _get(r, "web_fetches", "webFetches", "fetches"),
            _get(r, "output_bytes", "outputBytes"),
            _get(r, "started_at", "startedAt"), _get(r, "completed_at", "completedAt"),
            _get(r, "final_status", "finalStatus", "status"),
            prices,
        ))
    return out


def _from_local(dir_path: Path, run_id, prices) -> list:
    out = []
    for f in sorted(dir_path.glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        out.append(_record(
            run_id, "local", "local-instrumentation", _get(r, "model"),
            _get(r, "sessionId", "session_id"),
            _get(r, "agent"), _get(r, "skill"), _get(r, "purpose"), _get(r, "node"), _get(r, "attempt"),
            _get(r, "inputTokens"), _get(r, "outputTokens"),
            _get(r, "cacheReadTokens"), _get(r, "cacheCreationTokens"),
            _get(r, "durationMs"), _get(r, "toolCalls"),
            _get(r, "webSearches", "searches"), _get(r, "webFetches", "fetches"), _get(r, "outputBytes"),
            _get(r, "startedAt"), _get(r, "completedAt"),
            _get(r, "status", "finalStatus"),
            prices,
        ))
    return out


def _dedupe(records: list) -> tuple:
    seen = set()
    kept = []
    dropped = 0
    for r in records:
        if r["requestId"] in seen:
            dropped += 1
            continue
        seen.add(r["requestId"])
        kept.append(r)
    return kept, dropped


def _sum_group(records):
    agg = {}
    for field in NUMERIC_FIELDS + ["estimatedCostUsd"]:
        vals = [r[field] for r in records if r[field] is not None]
        if not vals:
            agg[field] = None
        elif field == "estimatedCostUsd":
            agg[field] = round(sum(vals), 6)
        else:
            agg[field] = sum(vals)
    agg["requestCount"] = len(records)
    agg["successCount"] = sum(1 for r in records if r["status"] in ("accepted", "passed", "success"))
    agg["failureCount"] = sum(1 for r in records if r["status"] in ("failed", "rejected", "error"))
    return agg


def _group_by(records, key_fn):
    groups = {}
    for r in records:
        groups.setdefault(key_fn(r), []).append(r)
    return {k: _sum_group(v) for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))}


def normalize(run_dir: Path, sources: dict, prices: dict) -> dict:
    run_json = {}
    rj = run_dir / "run.json"
    if rj.is_file():
        run_json = json.loads(rj.read_text(encoding="utf-8"))
    run_id = run_json.get("runId")

    records = []
    used_sources = []
    if sources.get("claude_code"):
        records += _from_claude_code(Path(sources["claude_code"]), run_id, prices)
        used_sources.append("claude-code")
    if sources.get("opencode"):
        records += _from_opencode(Path(sources["opencode"]), run_id, prices)
        used_sources.append("opencode")
    if sources.get("local"):
        records += _from_local(Path(sources["local"]), run_id, prices)
        used_sources.append("local")

    records, deduped_count = _dedupe(records)

    by_node = _group_by(records, lambda r: r["nodeId"] or "unknown")
    by_model = _group_by(records, lambda r: r["model"] or "unknown")
    by_purpose = _group_by(records, lambda r: r["purpose"])
    by_attempt = _group_by(records, lambda r: str(r["attempt"]) if r["attempt"] is not None else "unknown")
    run_agg = _sum_group(records)

    coverage = {}
    for field in NUMERIC_FIELDS + ["estimatedCostUsd"]:
        present = sum(1 for r in records if r[field] is not None)
        coverage[field] = {
            "present": present, "total": len(records),
            "pct": round(100 * present / len(records), 1) if records else 0.0,
        }

    return {
        "documentType": "ContractGraphCost",
        "runId": run_id,
        "generatedBy": "telemetry_normalize.py",
        "sources": used_sources,
        "dedupedCount": deduped_count,
        "requests": records,
        "byNode": by_node, "byModel": by_model, "byPurpose": by_purpose, "byAttempt": by_attempt,
        "run": run_agg, "coverage": coverage,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--run": None, "--claude-code": None, "--opencode": None, "--local": None,
            "--prices": "scripts/model_prices.json", "--out": None, "--requests-out": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--run"]:
        print("usage: telemetry_normalize.py --run <run-dir> [--claude-code F] [--opencode F] "
              "[--local DIR] [--prices F] [--out F] [--requests-out F]", file=sys.stderr)
        return 2
    run_dir = Path(opts["--run"])
    try:
        prices = json.loads(Path(opts["--prices"]).read_text(encoding="utf-8"))
    except OSError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    sources = {"claude_code": opts["--claude-code"], "opencode": opts["--opencode"], "local": opts["--local"]}
    try:
        cost = normalize(run_dir, sources, prices)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    out_path = Path(opts["--out"]) if opts["--out"] else (run_dir / "final" / "cost.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cost, indent=2) + "\n", encoding="utf-8")

    requests_out = Path(opts["--requests-out"]) if opts["--requests-out"] else (run_dir / "telemetry" / "requests.jsonl")
    requests_out.parent.mkdir(parents=True, exist_ok=True)
    with requests_out.open("w", encoding="utf-8") as fh:
        for r in cost["requests"]:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

    print(json.dumps({**cost, "requestsOut": requests_out.as_posix(), "costOut": out_path.as_posix()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
