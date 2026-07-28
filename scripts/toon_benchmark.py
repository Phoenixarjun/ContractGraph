#!/usr/bin/env python3
"""toon_benchmark - measure whether TOON encoding is worth enabling for a
specific uniform-array payload shape (resources, milestones, checkpoints,
source-registry entries, ...).

Reports jsonBytes/toonBytes/charSavingsPct, an estTokenSavingsPct (marked
estimated:true -- a char-count proxy, not a real tokenizer; no model is
available to count tokens deterministically), roundTripLossless
(decode(encode(x)) == x), schemaValid (each item still validates against its
own schema after the round trip), and a final `enable` verdict gated on the
thresholds in policies.json's tokenEfficiency.toon block.

TOON stays disabled in normal runtime regardless of this result (CLAUDE.md;
scripts/toon_codec.py's encode/decode still default to JSON passthrough).
This script only produces the DECISION ARTIFACT an optimized benchmark
config may act on. If the python-toon backend is not installed, reports
toonAvailable=false and enable=false -- never fabricates savings.

Usage:
  python scripts/toon_benchmark.py <array.json>
      [--item-schema <schema.json>] [--item-schema-pointer /$defs/ResourceLink]
      [--policies <policies.json>]
Output: JSON benchmark + decision. Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema_lite import validate_instance, validate_subschema
from toon_codec import benchmark as _codec_benchmark


def evaluate(array: list, policies: dict, item_schema_path: Path = None, item_schema_pointer: str = None) -> dict:
    bench = _codec_benchmark(array)

    schema_valid = None
    if item_schema_path is not None:
        errors = []
        for item in array:
            if item_schema_pointer:
                errors.extend(validate_subschema(item, item_schema_path, item_schema_pointer))
            else:
                errors.extend(validate_instance(item, item_schema_path))
        schema_valid = not errors

    toon_policy = (policies.get("tokenEfficiency", {}) or {}).get("toon", {}) or {}
    min_savings = toon_policy.get("minCharSavingsPct", 15)
    require_lossless = toon_policy.get("requireRoundTripLossless", True)
    require_schema_valid = toon_policy.get("requireSchemaValid", True)

    char_savings = bench.get("charSavingsPct")
    lossless = bench.get("roundTripLossless")

    enable = bool(
        bench.get("toonAvailable")
        and char_savings is not None and char_savings >= min_savings
        and (lossless if require_lossless else True)
        and (schema_valid if (require_schema_valid and schema_valid is not None) else True)
    )

    return {
        "documentType": "ContractGraphToonBenchmark",
        "itemCount": len(array),
        "jsonBytes": bench.get("jsonChars"),
        "toonBytes": bench.get("toonChars"),
        "toonAvailable": bench.get("toonAvailable", False),
        "charSavingsPct": char_savings,
        "estTokenSavingsPct": char_savings,
        "estimated": True,
        "roundTripLossless": lossless,
        "schemaValid": schema_valid,
        "thresholds": {
            "minCharSavingsPct": min_savings,
            "requireRoundTripLossless": require_lossless,
            "requireSchemaValid": require_schema_valid,
        },
        "enable": enable,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: toon_benchmark.py <array.json> [--item-schema <schema.json>] "
              "[--item-schema-pointer /$defs/X] [--policies <policies.json>]", file=sys.stderr)
        return 2
    array_path = Path(argv[0])
    item_schema = None
    item_schema_pointer = None
    policies_path = None
    i = 1
    while i < len(argv):
        if argv[i] == "--item-schema":
            item_schema = Path(argv[i + 1]); i += 2
        elif argv[i] == "--item-schema-pointer":
            item_schema_pointer = argv[i + 1]; i += 2
        elif argv[i] == "--policies":
            policies_path = Path(argv[i + 1]); i += 2
        else:
            i += 1
    try:
        array = json.loads(array_path.read_text(encoding="utf-8"))
        if not isinstance(array, list):
            raise ValueError("input must be a JSON array")
        policies = json.loads(policies_path.read_text(encoding="utf-8")) if policies_path else {}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    result = evaluate(array, policies, item_schema, item_schema_pointer)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
