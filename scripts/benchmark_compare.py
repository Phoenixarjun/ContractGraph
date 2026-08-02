#!/usr/bin/env python3
"""benchmark_compare - diff two runs' cost.json (telemetry_normalize.py output)
into a token/cost/duration/requests comparison.

For every metric in the `run` aggregate, reports baseline, optimized, delta
(optimized - baseline), and deltaPct. Never divides by a null/zero baseline
(deltaPct stays null in that case, not a fabricated infinity/0). Metrics
absent from EITHER side are reported as unavailable rather than compared.

Usage:
  python scripts/benchmark_compare.py --baseline <cost.json> --optimized <cost.json>
      [--out <comparison.json>]
Output: JSON comparison (also written to --out if given). Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

METRICS = [
    "inputTokens", "outputTokens", "cacheReadTokens", "cacheCreationTokens",
    "estimatedCostUsd", "durationMs", "toolCalls", "webSearches", "webFetches",
    "outputBytes", "requestCount", "successCount", "failureCount",
]


def compare(baseline: dict, optimized: dict) -> dict:
    b_run = baseline.get("run", {})
    o_run = optimized.get("run", {})
    metrics = {}
    for m in METRICS:
        b, o = b_run.get(m), o_run.get(m)
        if b is None or o is None:
            metrics[m] = {"baseline": b, "optimized": o, "delta": None, "deltaPct": None, "available": False}
            continue
        delta = o - b
        delta_pct = round(100 * delta / b, 2) if b else None
        metrics[m] = {"baseline": b, "optimized": o, "delta": delta, "deltaPct": delta_pct, "available": True}
    return {
        "documentType": "ContractGraphBenchmarkComparison",
        "baselineRunId": baseline.get("runId"),
        "optimizedRunId": optimized.get("runId"),
        "metrics": metrics,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--baseline": None, "--optimized": None, "--out": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--baseline"] or not opts["--optimized"]:
        print("usage: benchmark_compare.py --baseline <cost.json> --optimized <cost.json> [--out <path>]",
              file=sys.stderr)
        return 2
    try:
        baseline = json.loads(Path(opts["--baseline"]).read_text(encoding="utf-8"))
        optimized = json.loads(Path(opts["--optimized"]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    result = compare(baseline, optimized)
    if opts["--out"]:
        out_path = Path(opts["--out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
