#!/usr/bin/env python3
"""validate_source_urls - check that URLs in a section/final artifact are
well-formed, and (only when explicitly permitted) reachable.

Reachability uses the Python stdlib (urllib) with a bounded timeout. It is OFF by
default; pass --check-network to enable it. No third-party or paid search API is
ever used (CLAUDE.md). In agent execution, prefer Claude Code's WebFetch for
reachability; this script is the deterministic local fallback.

Usage:
  python scripts/validate_source_urls.py <file.json> [--check-network] [--timeout 8]
Output: JSON report. Exit 0 ok, 1 malformed/unreachable, 2 IO/usage.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_URI = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$")
_URL_KEYS = ("url", "canonicalUrl", "problemUrl", "link", "href", "sourceUrl")


def _collect_urls(obj):
    urls = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and (k in _URL_KEYS or _URI.match(v)):
                    urls.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)
    walk(obj)
    # unique, stable order
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u); out.append(u)
    return out


def _reachable(url, timeout):
    import urllib.request
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "ContractGraph-url-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400, resp.status
    except Exception as exc:  # noqa: BLE001 - any network error is "unreachable"
        return False, str(exc)


def run(path: Path, check_network: bool, timeout: int) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    urls = _collect_urls(doc)
    malformed = [u for u in urls if not _URI.match(u)]
    results = []
    unreachable = []
    if check_network:
        for u in urls:
            if not _URI.match(u):
                continue
            ok, info = _reachable(u, timeout)
            results.append({"url": u, "reachable": ok, "info": info})
            if not ok:
                unreachable.append(u)
    ok = not malformed and (not check_network or not unreachable)
    return {"ok": ok, "file": path.as_posix(), "urlCount": len(urls),
            "malformed": malformed, "networkChecked": check_network,
            "unreachable": unreachable, "results": results}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: validate_source_urls.py <file.json> [--check-network] [--timeout N]", file=sys.stderr)
        return 2
    path = Path(argv[0])
    check_network = "--check-network" in argv
    timeout = 8
    if "--timeout" in argv:
        timeout = int(argv[argv.index("--timeout") + 1])
    if not path.is_file():
        print(json.dumps({"ok": False, "error": f"file not found: {path}"}), file=sys.stderr)
        return 2
    try:
        report = run(path, check_network, timeout)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
