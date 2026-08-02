#!/usr/bin/env python3
"""timestamp_now - print the real current UTC time in the one canonical
ISO-8601-with-milliseconds format ContractGraph uses everywhere.

The orchestrator (Claude Code executing run.md) calls this at each event
boundary (node start/complete, verification complete, aggregation complete,
final artifact write, run complete) instead of writing an estimated or
rounded timestamp by hand. There is no other source of truth for "now" in
this framework -- no script previously called a clock at all, which is how
the study-plan run ended up with hand-typed, round-number timestamps.

Usage:  python scripts/timestamp_now.py
Output: {"iso": "2026-07-28T18:35:39.217Z"}. Exit 0 always (a clock read
        cannot fail in a way worth a non-zero exit).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

ISO_SECONDS_FORMAT = "%Y-%m-%dT%H:%M:%S"  # milliseconds appended manually below (strftime has no %3f)


def utc_now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime(ISO_SECONDS_FORMAT) + f".{now.microsecond // 1000:03d}Z"


def main(argv=None) -> int:
    print(json.dumps({"iso": utc_now_iso()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
