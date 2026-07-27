#!/usr/bin/env python3
"""toon_codec - optional TOON (Token-Oriented Object Notation) codec.

Backend: the `python-toon` package (https://github.com/xaviviro/python-toon),
`from toon import encode, decode`. Install with:  pip install python-toon
(It is an OPTIONAL dependency, needed only for the TOON path; the framework core
never requires it and JSON remains canonical.)

TOON stays DISABLED BY DEFAULT per CLAUDE.md: it may be enabled only after a
measured benchmark shows token savings that do not reduce correctness. So:
  - encode/decode default to compact JSON (a stable interface for callers);
  - the TOON path is reached only with enable_toon=True (or CLI --toon);
  - if TOON is requested but python-toon is not installed, we fail loudly with
    an install hint rather than silently degrading.

  encode(obj, enable_toon=False) -> str
  decode(text, enable_toon=False) -> obj

CLI:
  python scripts/toon_codec.py --status
  python scripts/toon_codec.py --encode FILE [--toon]
  python scripts/toon_codec.py --decode FILE [--toon]
  python scripts/toon_codec.py --benchmark FILE   # JSON vs TOON size, if installed
Exit 0 ok, 2 IO/usage, 3 TOON requested but backend unavailable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOON_ENABLED_DEFAULT = False  # do not flip without a benchmark proving parity

_INSTALL_HINT = "TOON backend unavailable. Install it with: pip install python-toon"


def _toon():
    """Import the python-toon backend, or raise a clear ImportError."""
    try:
        from toon import encode as _enc, decode as _dec  # type: ignore
        return _enc, _dec
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ImportError(_INSTALL_HINT) from exc


def toon_available() -> bool:
    try:
        _toon()
        return True
    except ImportError:
        return False


def encode(obj, enable_toon: bool = TOON_ENABLED_DEFAULT) -> str:
    if enable_toon:
        enc, _ = _toon()
        return enc(obj)
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def decode(text: str, enable_toon: bool = TOON_ENABLED_DEFAULT):
    if enable_toon:
        _, dec = _toon()
        return dec(text)
    return json.loads(text)


def benchmark(obj) -> dict:
    """Compare compact-JSON vs TOON character size (a proxy to gate enablement)."""
    json_str = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    result = {"jsonChars": len(json_str), "toonAvailable": toon_available()}
    if result["toonAvailable"]:
        enc, dec = _toon()
        toon_str = enc(obj)
        result["toonChars"] = len(toon_str)
        result["charSavingsPct"] = round(100 * (1 - len(toon_str) / max(1, len(json_str))), 2)
        try:
            result["roundTripLossless"] = dec(toon_str) == obj
        except Exception as exc:  # noqa: BLE001
            result["roundTripLossless"] = False
            result["roundTripError"] = str(exc)
    return result


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "--status":
        print(json.dumps({
            "toonEnabledByDefault": TOON_ENABLED_DEFAULT,
            "mode": "json-passthrough",
            "backend": "python-toon (from toon import encode, decode)",
            "backendInstalled": toon_available(),
            "note": "TOON disabled until a benchmark proves lossless token savings",
        }, indent=2))
        return 0

    use_toon = "--toon" in argv
    args = [a for a in argv if a != "--toon"]

    if args[0] == "--benchmark" and len(args) >= 2:
        try:
            obj = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        except OSError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 2
        print(json.dumps(benchmark(obj), indent=2))
        return 0

    if args[0] in ("--encode", "--decode") and len(args) >= 2:
        try:
            raw = Path(args[1]).read_text(encoding="utf-8")
        except OSError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 2
        try:
            if args[0] == "--encode":
                print(encode(json.loads(raw), enable_toon=use_toon))
            else:
                out = decode(raw, enable_toon=use_toon)
                print(json.dumps(out, indent=2))
        except ImportError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 3
        return 0

    print("usage: toon_codec.py [--status | --encode FILE | --decode FILE | --benchmark FILE] [--toon]",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
