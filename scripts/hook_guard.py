#!/usr/bin/env python3
"""hook_guard - lightweight PreToolUse guard for Write/Edit.

Purpose (Step 8, kept deliberately minimal and non-noisy): stop obvious private
PII from being written into reusable, publishable artifacts — generated skills
and agent definitions under .claude/skills/ and .claude/agents/. It only inspects
writes to those paths; every other write is passed through instantly.

Signals it blocks: email addresses and phone-like digit runs (10+ digits). It does
NOT try to detect names (brittle, and hard-coding personal identifiers into a repo
file would itself leak them) — name-level privacy is enforced by the skill/agent
authoring rules and the graph-plan-reviewer privacy check.

FAIL-OPEN: any parsing/IO error allows the write (exit 0). It must never block the
user's normal work by accident. It blocks (exit 2) only on a definite PII hit.

Protocol: reads the Claude Code hook payload as JSON on stdin. Exit 0 = allow;
exit 2 = block (reason on stderr).
"""
from __future__ import annotations

import json
import re
import sys

GUARDED = (".claude/skills/", ".claude/agents/")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+\d[\d ().-]{8,}\d|\d{10,})(?!\d)")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open: never block on a malformed/absent payload

    try:
        tool_input = payload.get("tool_input", {}) or {}
        path = (tool_input.get("file_path") or "").replace("\\", "/")
        if not any(seg in path for seg in GUARDED):
            return 0
        content = tool_input.get("content") or tool_input.get("new_string") or ""
        hits = []
        if EMAIL.search(content):
            hits.append("email address")
        if PHONE.search(content):
            hits.append("phone-like digit sequence")
        if hits:
            sys.stderr.write(
                "hook_guard: refusing to write private PII (" + ", ".join(hits) + ") into a "
                "reusable skill/agent (" + path + "). Skills and agents must be publishable — "
                "keep personal data in context/private/ and reference it by path.\n"
            )
            return 2
    except Exception:
        return 0  # fail-open on any unexpected error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
