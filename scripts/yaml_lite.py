#!/usr/bin/env python3
"""yaml_lite - a tiny, dependency-free reader for the restricted YAML subset
ContractGraph uses in graph.yaml.

Why this exists: PyYAML is not guaranteed to be installed and CLAUDE.md forbids
non-essential dependencies. graph.yaml is machine-authored and uses only a small,
predictable subset of YAML, so a purpose-built loader is safe and testable here.

Supported subset (and ONLY this subset):
  - 2-space indentation
  - mappings:            key: value   |   key:  (then an indented block)
  - sequences:           - scalar     |   - key: value  (block-mapping items)
  - scalars:             strings, "quoted", true/false, null, integers, floats
  - full-line comments starting with '#', and blank lines

Explicit limitations: no flow collections ([], {}), no multi-line scalars, no
anchors/aliases, and scalars must not contain ':'. These never appear in our
generated graph.yaml. For anything richer, emit/consume JSON instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


class YamlLiteError(ValueError):
    pass


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _scalar(token: str):
    t = token.strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        return t[1:-1]
    low = t.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~", ""):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


class _Cursor:
    def __init__(self, lines):
        self.lines = lines
        self.i = 0

    def peek(self):
        return self.lines[self.i] if self.i < len(self.lines) else None


def _parse_block(cur: _Cursor, indent: int):
    line = cur.peek()
    if line is None:
        return None
    if line.strip().startswith("- "):
        return _parse_seq(cur, indent)
    return _parse_map(cur, indent)


def _parse_seq(cur: _Cursor, indent: int):
    seq = []
    while True:
        line = cur.peek()
        if line is None:
            break
        cind = _indent(line)
        if cind != indent or not line.strip().startswith("- "):
            break
        content = line.strip()[2:].strip()
        cur.i += 1
        if content == "":
            nxt = cur.peek()
            seq.append(_parse_block(cur, _indent(nxt)) if nxt is not None else None)
        elif ":" in content:
            item_indent = indent + 2
            sub_lines = [(" " * item_indent) + content]
            while True:
                nl = cur.peek()
                if nl is None or _indent(nl) <= indent:
                    break
                sub_lines.append(nl)
                cur.i += 1
            seq.append(_parse_map(_Cursor(sub_lines), item_indent))
        else:
            seq.append(_scalar(content))
    return seq


def _parse_map(cur: _Cursor, indent: int):
    d = {}
    while True:
        line = cur.peek()
        if line is None:
            break
        cind = _indent(line)
        if cind != indent:
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            break
        if ":" not in stripped:
            raise YamlLiteError(f"expected 'key:' but got: {stripped!r}")
        key, _, val = stripped.partition(":")
        key = key.strip()
        val = val.strip()
        cur.i += 1
        if val == "":
            nxt = cur.peek()
            if nxt is not None and _indent(nxt) > indent:
                d[key] = _parse_block(cur, _indent(nxt))
            else:
                d[key] = None
        else:
            d[key] = _scalar(val)
    return d


def loads(text: str):
    lines = []
    for raw in text.splitlines():
        if raw.strip() == "" or raw.lstrip().startswith("#"):
            continue
        lines.append(raw.rstrip())
    if not lines:
        return None
    cur = _Cursor(lines)
    base = _indent(lines[0])
    return _parse_block(cur, base)


def load_file(path) -> object:
    return loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python yaml_lite.py <file.yaml>", file=sys.stderr)
        return 2
    try:
        data = load_file(argv[0])
    except (OSError, YamlLiteError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
