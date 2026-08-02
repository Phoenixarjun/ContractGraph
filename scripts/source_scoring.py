#!/usr/bin/env python3
"""source_scoring - deterministic source-quality governance.

Scores a list of sources (a learning track's resources[], a section's
sourceRegistry entries, or any array with at least a `url`) on six
dimensions and returns a bounded, ranked keep/archive split -- the
mechanism the study-plan run needed but never had (it registered 88
undifferentiated sources with no scoring or bound).

Dimensions (each 0.0-1.0):
  authority     - tier rank against AUTHORITY_TIERS below (official docs >
                  papers > official engineering > books/courses > technical
                  publications/blogs > community), matched from a `type` or
                  `sourceType` field via TYPE_ALIASES. An unrecognized type
                  defaults to the middle tier ("technical_publication"), not
                  the best or worst -- absence of a signal is not evidence.
  freshness     - from `publicationDate` (parsed YYYY-MM-DD or full
                  date-time) against real "now"; missing/unparseable dates
                  are NEVER guessed -- freshness defaults to a flagged
                  neutral 0.5 ("freshnessUnknown": true) instead.
  uniqueness    - 1.0 unless another kept source has a near-duplicate title
                  (token-Jaccard > 0.6) on the same host, in which case the
                  lower-scored of the pair is marked a duplicate and dropped
                  from the ranking entirely (it never even competes for a
                  kept slot -- true duplicates aren't "lower quality", they're
                  redundant).
  accessibility - 1.0/0.0 from a well-formed-URI check by default; if
                  --reachability-report is given (e.g. validate_source_urls.py
                  --check-network output), the measured reachability wins.
  actionability - passed through from the source's own `relevanceScore` or
                  `confidence` if present (a judgment call this script can't
                  invent), else a flagged neutral 0.5 ("relevanceUnscored").

Every dimension that used a neutral default (not a measured value) is named
in that entry's `unscoredDimensions` -- the total score is never presented
as fully measured when it partly isn't.

Ranking is stable and deterministic: score desc, then url asc. Keeps up to
--max (default 10; never fewer than what actually exists), archives the
rest -- UNLESS a source's ref/url appears in --required-refs (it is the
sole support for some claim), in which case it is always kept regardless
of rank.

Usage:
  python scripts/source_scoring.py --sources <sources.json> --policies <policies.json>
      [--min 5] [--max 10] [--required-refs <refs.json>]
      [--reachability-report <report.json>] [--out <ranked.json>]
Output: JSON {ok, asOf, kept, archived, duplicatesDropped}. Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

AUTHORITY_TIERS = [
    "official_documentation", "research_paper", "official_engineering",
    "book", "course", "technical_publication", "community",
]
TYPE_ALIASES = {
    "doc": "official_documentation", "docs": "official_documentation",
    "documentation": "official_documentation", "official_documentation": "official_documentation",
    "official_regulatory": "official_documentation", "official": "official_documentation",
    "paper": "research_paper", "research_paper": "research_paper",
    "official_engineering": "official_engineering", "engineering_blog": "official_engineering",
    "book": "book",
    "course": "course",
    "article": "technical_publication", "blog": "technical_publication",
    "publication": "technical_publication", "reputable_news": "technical_publication",
    "candidate_report": "technical_publication",
    "community": "community", "forum": "community", "job_posting": "community",
}
DEFAULT_TIER = "technical_publication"
_URI = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$")
_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ")
_WEIGHTS = {"authority": 0.35, "freshness": 0.20, "uniqueness": 0.15, "accessibility": 0.15, "actionability": 0.15}
_STOPWORDS = {"the", "a", "an", "for", "of", "and", "to", "in", "on", "with", "by"}


def _load(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _load_sources(path) -> list:
    raw = _load(path)
    if isinstance(raw, list):
        return raw
    sources = raw.get("sources", raw.get("entries"))
    if sources is not None:
        return sources
    # Fallback: section files store sources under data.resources
    data = raw.get("data", {}) or {}
    return data.get("resources", [])


def _authority_tier(source: dict) -> str:
    raw_type = str(source.get("sourceType") or source.get("type") or "").strip().lower()
    return TYPE_ALIASES.get(raw_type, DEFAULT_TIER)


def _authority_score(tier: str) -> float:
    idx = AUTHORITY_TIERS.index(tier)
    return round(1 - idx / (len(AUTHORITY_TIERS) - 1), 4)


def _parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def _freshness(source: dict, now: datetime, freshness_days: int):
    pub = _parse_date(source.get("publicationDate"))
    if pub is None:
        return 0.5, True
    age_days = max(0, (now - pub).days)
    return round(max(0.0, 1 - age_days / freshness_days), 4), False


def _accessibility(url: str, reachability: dict):
    if url in reachability:
        return (1.0 if reachability[url] else 0.0), False
    return (1.0 if _URI.match(url or "") else 0.0), True


def _actionability(source: dict):
    val = source.get("relevanceScore")
    if not isinstance(val, (int, float)):
        val = source.get("confidence")
    if isinstance(val, (int, float)) and 0 <= val <= 1:
        return round(float(val), 4), False
    return 0.5, True


def _title_tokens(title: str) -> set:
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def score_sources(sources: list, policies: dict, reachability: dict, now: datetime, required_refs: set = frozenset()) -> list:
    freshness_days = policies.get("freshnessDays", {}).get("foundationalEngineeringMaterial", 1825)
    scored = []
    for s in sources:
        url = s.get("url") or s.get("canonicalUrl") or ""
        tier = _authority_tier(s)
        authority = _authority_score(tier)
        freshness, fresh_unknown = _freshness(s, now, freshness_days)
        accessibility, access_unknown = _accessibility(url, reachability)
        actionability, action_unknown = _actionability(s)
        unscored = []
        if fresh_unknown:
            unscored.append("freshness")
        if access_unknown:
            unscored.append("accessibility")
        if action_unknown:
            unscored.append("actionability")
        scored.append({
            "ref": s.get("sourceRef") or s.get("ref"),
            "title": s.get("title"),
            "url": url,
            "host": urlsplit(url).netloc.lower() if url else "",
            "authorityTier": tier,
            "dimensions": {"authority": authority, "freshness": freshness,
                           "uniqueness": 1.0, "accessibility": accessibility, "actionability": actionability},
            "unscoredDimensions": unscored,
            "_titleTokens": _title_tokens(s.get("title", "")),
        })

    # dedup near-duplicate titles on the same host: keep the higher (pre-uniqueness)
    # weighted score of the pair, drop the other from ranking entirely.
    def prelim_score(e):
        d = e["dimensions"]
        return sum(d[k] * w for k, w in _WEIGHTS.items())

    def is_required(e):
        return e["ref"] in required_refs or e["url"] in required_refs

    dropped_as_duplicate = set()
    for i, a in enumerate(scored):
        if id(a) in dropped_as_duplicate:
            continue
        for b in scored[i + 1:]:
            if id(b) in dropped_as_duplicate or a["host"] != b["host"] or not a["host"]:
                continue
            if _jaccard(a["_titleTokens"], b["_titleTokens"]) > 0.6:
                a_req, b_req = is_required(a), is_required(b)
                if a_req and b_req:
                    continue  # never drop either -- both are the sole support for some claim
                if a_req:
                    loser = b
                elif b_req:
                    loser = a
                else:
                    loser = a if prelim_score(a) < prelim_score(b) else b
                dropped_as_duplicate.add(id(loser))

    duplicates = [e for e in scored if id(e) in dropped_as_duplicate]
    kept_pool = [e for e in scored if id(e) not in dropped_as_duplicate]

    for e in kept_pool:
        d = e["dimensions"]
        e["totalScore"] = round(sum(d[k] * w for k, w in _WEIGHTS.items()), 4)
        e["reason"] = (f"tier={e['authorityTier']}, authority={d['authority']}, freshness={d['freshness']}, "
                        f"uniqueness={d['uniqueness']}, accessibility={d['accessibility']}, "
                        f"actionability={d['actionability']}")
        del e["_titleTokens"]
    for e in duplicates:
        del e["_titleTokens"]

    kept_pool.sort(key=lambda e: (-e["totalScore"], e["url"]))
    return kept_pool, duplicates


def rank(sources: list, policies: dict, min_n: int, max_n: int,
         required_refs: set, reachability: dict, now: datetime) -> dict:
    ranked, duplicates = score_sources(sources, policies, reachability, now, required_refs)

    required = [e for e in ranked if e["ref"] in required_refs or e["url"] in required_refs]
    required_ids = {id(e) for e in required}
    rest = [e for e in ranked if id(e) not in required_ids]
    kept = required + rest[:max(0, max_n - len(required))]
    kept.sort(key=lambda e: (-e["totalScore"], e["url"]))
    kept_ids = {id(e) for e in kept}
    archived = [e for e in ranked if id(e) not in kept_ids]

    return {
        "ok": True,
        "asOf": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        "totalConsidered": len(sources),
        "duplicatesDropped": len(duplicates),
        "duplicates": duplicates,
        "kept": kept,
        "archived": archived,
        "targetRange": {"min": min_n, "max": max_n},
        "belowTarget": len(kept) < min_n,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--sources": None, "--policies": None, "--min": "5", "--max": "10",
            "--required-refs": None, "--reachability-report": None, "--out": None}
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--sources"] or not opts["--policies"]:
        print("usage: source_scoring.py --sources <sources.json> --policies <policies.json> "
              "[--min N] [--max N] [--required-refs <file>] [--reachability-report <file>] [--out <path>]",
              file=sys.stderr)
        return 2
    try:
        sources = _load_sources(opts["--sources"])
        policies = _load(opts["--policies"])
        required_refs = set(_load(opts["--required-refs"])) if opts["--required-refs"] else set()
        reach_raw = _load(opts["--reachability-report"]) if opts["--reachability-report"] else {}
        reachability = {r["url"]: r["reachable"] for r in reach_raw.get("results", [])} if reach_raw else {}
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    report = rank(sources, policies, int(opts["--min"]), int(opts["--max"]), required_refs, reachability, now)

    if opts["--out"]:
        out_path = Path(opts["--out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
