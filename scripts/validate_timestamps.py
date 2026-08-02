#!/usr/bin/env python3
"""validate_timestamps - check a run directory's real-time provenance.

Validates two independent things about every timestamp ContractGraph writes
(runCreatedAt/runCompletedAt in run.json; nodeStartedAt/nodeCompletedAt per
node-state file; verificationCompletedAt in verification/global-verification.json;
aggregationCompletedAt in final/derived-context.json; finalArtifactGeneratedAt
anywhere under final/final.json):

1. Format: every non-null timestamp must be ISO-8601 UTC with millisecond
   precision (`YYYY-MM-DDTHH:MM:SS.mmmZ`). A round-second value with no
   milliseconds is a format error -- real wall-clock reads have sub-second
   precision; a value that doesn't is a signal it was hand-typed, not
   measured. A null timestamp is fine ONLY when paired with a sibling
   `timestampSource: "unavailable"` in the same record -- a null with no
   explanation is also a violation ("missing timestamp" vs "explicitly
   unavailable" must be distinguishable).

2. Ordering: the pipeline runs nodes -> global verification -> aggregation
   -> final-artifact write -> run completion, so (wherever both sides of a
   comparison are non-null) nodeStartedAt <= nodeCompletedAt per node,
   runCreatedAt <= every nodeStartedAt, max(nodeCompletedAt) <=
   verificationCompletedAt <= aggregationCompletedAt <= finalArtifactGeneratedAt
   <= runCompletedAt. A verificationCompletedAt found AFTER runCompletedAt
   (the study-plan run's actual defect) is reported directly, not only via
   the transitive chain, so it still gets caught even when the intermediate
   aggregation/final-artifact fields are absent.

Usage:  python scripts/validate_timestamps.py --run <run-dir>
Output: JSON {ok, formatErrors, orderingErrors, fields}. Exit 0 ok, 1 violations, 2 IO/usage.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STRICT_MS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _get(d: dict, *keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _find_nested_with_container(doc, key, depth=4):
    """Return (value, containing_dict) for the first match of `key`, searched
    recursively -- the containing dict (not the root doc) is what carries a
    sibling `timestampSource` marker when the value is null."""
    if depth < 0 or not isinstance(doc, dict):
        return None, None
    if key in doc:
        return doc[key], doc
    for v in doc.values():
        if isinstance(v, dict):
            found, container = _find_nested_with_container(v, key, depth - 1)
            if container is not None:
                return found, container
    return None, None


def _format_error(name: str, value, raw: dict) -> dict | None:
    if value is None:
        source = raw.get("timestampSource") if isinstance(raw, dict) else None
        if source != "unavailable":
            return {"field": name, "value": None,
                    "error": "null timestamp without sibling timestampSource: 'unavailable'"}
        return None
    if not isinstance(value, str) or not STRICT_MS.match(value):
        return {"field": name, "value": value,
                "error": "not ISO-8601 UTC with millisecond precision (YYYY-MM-DDTHH:MM:SS.mmmZ)"}
    return None


def gather(run_dir: Path) -> dict:
    fields = {"runCreatedAt": None, "runCompletedAt": None, "verificationCompletedAt": None,
              "aggregationCompletedAt": None, "finalArtifactGeneratedAt": None, "nodes": {}}
    raw_docs = {}

    rj = run_dir / "run.json"
    if rj.is_file():
        d = _load(rj)
        raw_docs["run"] = d
        fields["runCreatedAt"] = _get(d, "runCreatedAt", "startedAt")
        fields["runCompletedAt"] = _get(d, "runCompletedAt", "completedAt")

    ns_dir = run_dir / "node-state"
    if ns_dir.is_dir():
        for f in sorted(ns_dir.glob("*.json")):
            d = _load(f)
            nid = d.get("nodeId", f.stem)
            fields["nodes"][nid] = {
                "nodeStartedAt": _get(d, "nodeStartedAt", "startedAt"),
                "nodeCompletedAt": _get(d, "nodeCompletedAt", "completedAt"),
                "raw": d,
            }

    gv = run_dir / "verification" / "global-verification.json"
    if gv.is_file():
        d = _load(gv)
        raw_docs["verification"] = d
        fields["verificationCompletedAt"] = _get(d, "verificationCompletedAt", "verifiedAt")

    dc = run_dir / "final" / "derived-context.json"
    if dc.is_file():
        d = _load(dc)
        raw_docs["derivedContext"] = d
        fields["aggregationCompletedAt"] = _get(d, "aggregationCompletedAt", "generatedAt")

    fj = run_dir / "final" / "final.json"
    if fj.is_file():
        d = _load(fj)
        value, container = _find_nested_with_container(d, "finalArtifactGeneratedAt")
        if container is None:
            value, container = _find_nested_with_container(d, "generatedAt")
        fields["finalArtifactGeneratedAt"] = value
        raw_docs["final"] = container if container is not None else d

    return fields, raw_docs


def validate(run_dir: Path) -> dict:
    fields, raw_docs = gather(run_dir)
    format_errors = []

    # only validate a field when the file it lives in actually exists -- a
    # stage that hasn't run yet (e.g. no verification/ output on a still-in-
    # -progress run) is absence, not a malformed null that needs explaining.
    if "run" in raw_docs:
        for name in ("runCreatedAt", "runCompletedAt"):
            err = _format_error(name, fields[name], raw_docs["run"])
            if err:
                format_errors.append(err)
    if "verification" in raw_docs:
        err = _format_error("verificationCompletedAt", fields["verificationCompletedAt"], raw_docs["verification"])
        if err:
            format_errors.append(err)
    if "derivedContext" in raw_docs:
        err = _format_error("aggregationCompletedAt", fields["aggregationCompletedAt"], raw_docs["derivedContext"])
        if err:
            format_errors.append(err)
    if "final" in raw_docs:
        err = _format_error("finalArtifactGeneratedAt", fields["finalArtifactGeneratedAt"], raw_docs["final"])
        if err:
            format_errors.append(err)
    for nid, n in fields["nodes"].items():
        for name in ("nodeStartedAt", "nodeCompletedAt"):
            err = _format_error(f"nodes.{nid}.{name}", n[name], n.get("raw", {}))
            if err:
                format_errors.append(err)

    ordering_errors = []

    def before(name_a, val_a, name_b, val_b):
        if val_a is not None and val_b is not None and val_a > val_b:
            ordering_errors.append({
                "before": name_a, "beforeValue": val_a, "after": name_b, "afterValue": val_b,
                "error": f"'{name_a}' ({val_a}) is after '{name_b}' ({val_b}) -- impossible sequence",
            })

    for nid, n in fields["nodes"].items():
        before(f"nodes.{nid}.nodeStartedAt", n["nodeStartedAt"], f"nodes.{nid}.nodeCompletedAt", n["nodeCompletedAt"])
        before("runCreatedAt", fields["runCreatedAt"], f"nodes.{nid}.nodeStartedAt", n["nodeStartedAt"])

    node_completed = [n["nodeCompletedAt"] for n in fields["nodes"].values() if n["nodeCompletedAt"] is not None]
    max_node_completed = max(node_completed) if node_completed else None
    before("max(nodeCompletedAt)", max_node_completed, "verificationCompletedAt", fields["verificationCompletedAt"])
    before("verificationCompletedAt", fields["verificationCompletedAt"], "aggregationCompletedAt", fields["aggregationCompletedAt"])
    before("aggregationCompletedAt", fields["aggregationCompletedAt"], "finalArtifactGeneratedAt", fields["finalArtifactGeneratedAt"])
    before("finalArtifactGeneratedAt", fields["finalArtifactGeneratedAt"], "runCompletedAt", fields["runCompletedAt"])
    # direct check -- must hold even when the intermediate aggregation/final-artifact
    # fields are absent, which is exactly the shape of the real study-plan defect.
    before("verificationCompletedAt", fields["verificationCompletedAt"], "runCompletedAt", fields["runCompletedAt"])

    fields_out = dict(fields)
    return {
        "ok": not format_errors and not ordering_errors,
        "formatErrors": format_errors,
        "orderingErrors": ordering_errors,
        "fields": fields_out,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    run_dir = None
    i = 0
    while i < len(argv):
        if argv[i] == "--run":
            run_dir = Path(argv[i + 1]); i += 2
        else:
            i += 1
    if not run_dir or not run_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"run dir not found: {run_dir}"}), file=sys.stderr)
        return 2
    try:
        report = validate(run_dir)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
