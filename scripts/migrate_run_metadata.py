#!/usr/bin/env python3
"""migrate_run_metadata - repair a run's METADATA (trace state, privacy
classification, timestamp honesty, source-registry shape/ranking, scope
wording) in place, without touching accepted research content.

This is the remediation for a run produced before the trace/privacy/
timestamp/telemetry/source-governance/scope fixes existed (the
20260728-study-plan run). It does NOT re-run any node, re-verify any
section, or regenerate researched content (topics/objectives/resources/
milestones stay byte-identical) -- that would require re-running the
workflow, which this task explicitly does not do.

Steps (each recorded in the migration record):
  1. Back up the entire run directory to
     runtime/runs/<run-id>/.migrations/<NNN>-pre-migration/ BEFORE any write.
  2. Normalize every node-state/<id>.json: canonical `state` key (from
     legacy `status`), and null out `nodeStartedAt`/`nodeCompletedAt` with
     `timestampSource: "unavailable"` -- the existing values are round-number
     fabrications (see docs/time-and-provenance.md), never presented as real.
  3. Regenerate final/trace.json via generate_trace.py's fixed normalization.
  4. Rebuild final/derived-context.json via build_derived_context.py,
     passing the existing file as --existing so classification can only
     escalate, never downgrade.
  5. Repair evidence/source-registry.json into the schema shape
     source_registry.py expects ({documentType, version, entries}) from
     whatever shape it was in (a flat SRC_xxxx dict for this run), then run
     source_scoring.py over it and write evidence/source-ranking.json (kept
     + archived) -- an ADDITIONAL governance artifact; the sections'
     resources[] arrays (declared researchOwnedFields in contract.bundle.json)
     are left untouched.
  6. Flag verification/global-verification.json as describing a stale
     snapshot (it disagrees with the current final.json) via a
     `migrationNote`, and null its timestamp the same way as step 2 --
     the verdict CONTENT is not rewritten (that needs a real re-verification
     run, out of scope here).
  7. Rewrite final/final.json's studyPlanMeta: null `generatedAt` with
     `generatedAtSource: "unavailable"` (its one non-round timestamp
     disagrees with the rest of the run's timeline enough that its
     authenticity can't be confirmed -- honesty over a plausible guess),
     add `scopeDisclaimer` naming every contract.bundle.json scope.outOfScope
     topic. Also null run.json's timestamps the same way, replacing the
     legacy startedAt/completedAt keys with runCreatedAt/runCompletedAt.
  8. Rewrite final/report.md's Caveats section with the same scope wording.

Usage:
  python scripts/migrate_run_metadata.py --run <run-dir> --bundle <bundle-dir> [--dry-run]
Output: JSON migration record (also written under .migrations/). Exit 0 ok, 2 IO/usage.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_trace import build as build_trace  # noqa: E402
from build_derived_context import build as build_derived  # noqa: E402
from source_scoring import rank as rank_sources  # noqa: E402


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _write(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def backup(run_dir: Path) -> Path:
    migrations_dir = run_dir / ".migrations"
    migrations_dir.mkdir(exist_ok=True)
    existing = sorted(p for p in migrations_dir.glob("*-pre-migration") if p.is_dir())
    seq = len(existing) + 1
    dest = migrations_dir / f"{seq:03d}-pre-migration"
    shutil.copytree(run_dir, dest, ignore=shutil.ignore_patterns(".migrations"))
    return dest


def normalize_node_states(run_dir: Path) -> list:
    from generate_trace import normalize_node_state
    changes = []
    ns_dir = run_dir / "node-state"
    if not ns_dir.is_dir():
        return changes
    for f in sorted(ns_dir.glob("*.json")):
        record = _load(f)
        normalized, _source_field, err = normalize_node_state(record)
        new_record = {
            "nodeId": record.get("nodeId", f.stem),
            "state": normalized if not err else record.get("state", record.get("status")),
            "attempts": record.get("attempts"),
            "verificationStatus": record.get("verificationStatus"),
            "error": record.get("error"),
            "nodeStartedAt": None,
            "nodeCompletedAt": None,
            "timestampSource": "unavailable",
        }
        if err:
            new_record["stateNormalizationError"] = err
        _write(f, new_record)
        changes.append(f"node-state/{f.name}: normalized to canonical 'state' key, nulled fabricated timestamps")
    return changes


def _compact_ranked_entries(ranked_list: list) -> list:
    return [{"title": e.get("title"), "url": e.get("url"), "authorityTier": e.get("authorityTier"),
              "score": e.get("totalScore"), "reason": e.get("reason")} for e in ranked_list]


def repair_source_governance(run_dir: Path, bundle_dir: Path, bundle: dict) -> tuple:
    """Score each node's OWN resources[] (not the merged 88-entry global
    registry as one pool -- that undercounted per-node coverage down to a
    single global top-10) and write BOTH a standalone
    evidence/source-governance.json (per node: kept/archived, full detail)
    AND a compact recommendedSources/archivedSources view directly into
    final/final.json, so the ranking is actually reflected in the artifact a
    reader would open -- not only in a side file nobody looks at. Section
    resources[] arrays (researchOwnedFields) are never rewritten."""
    changes = []
    policies_path = bundle_dir / "policies.json"
    if not policies_path.is_file():
        return changes, None
    policies = _load(policies_path)
    sections_dir = run_dir / "sections"
    now = datetime.now(timezone.utc)

    per_node = {}
    for node in bundle.get("nodes", []):
        nid = node["nodeId"]
        sec_path = sections_dir / f"{nid}.json"
        if not sec_path.is_file():
            continue
        section = _load(sec_path)
        resources = (section.get("data", {}) or {}).get("resources")
        if not resources:
            continue
        per_node[nid] = rank_sources(resources, policies, min_n=5, max_n=10,
                                       required_refs=set(), reachability={}, now=now)
        changes.append(f"evidence/source-governance.json[{nid}]: scored {per_node[nid]['totalConsidered']} "
                        f"resources, kept {len(per_node[nid]['kept'])}, archived {len(per_node[nid]['archived'])}")

    if not per_node:
        return changes, None

    governance = {
        "documentType": "ContractGraphSourceGovernance",
        "generatedBy": "migrate_run_metadata.py (scores via source_scoring.py)",
        "perNode": per_node,
    }
    _write(run_dir / "evidence" / "source-governance.json", governance)
    changes.append(f"evidence/source-governance.json written: per-node recommended/archived split for {len(per_node)} nodes")

    # legacy flat evidence/source-registry.json: repair shape only if present
    reg_path = run_dir / "evidence" / "source-registry.json"
    if reg_path.is_file():
        raw = _load(reg_path)
        if isinstance(raw, dict) and "entries" in raw and "documentType" in raw:
            changes.append("evidence/source-registry.json: already in canonical shape, left as-is")
        else:
            entries = raw if isinstance(raw, dict) else {}
            wrapped = {"documentType": "ContractGraphSourceRegistry", "version": "1.0.0", "entries": entries}
            _write(reg_path, wrapped)
            changes.append(f"evidence/source-registry.json: wrapped {len(entries)} flat entries into the canonical "
                            "{documentType, version, entries} shape expected by source_registry.py")

    final_path = run_dir / "final" / "final.json"
    if final_path.is_file():
        final_doc = _load(final_path)
        final_doc["sourceGovernance"] = {
            "recommendedSources": {nid: _compact_ranked_entries(g["kept"]) for nid, g in per_node.items()},
            "archivedSources": {nid: _compact_ranked_entries(g["archived"]) for nid, g in per_node.items()},
        }
        _write(final_path, final_doc)
        changes.append("final/final.json: added top-level sourceGovernance.{recommendedSources,archivedSources} "
                        "per node -- the ranking is now reflected in the artifact itself, not only a side file "
                        "(sections' own resources[] arrays left untouched)")

    return changes, governance


def repair_global_verification(run_dir: Path) -> list:
    gv_path = run_dir / "verification" / "global-verification.json"
    changes = []
    if not gv_path.is_file():
        return changes
    doc = _load(gv_path)
    doc["verificationCompletedAt"] = None
    doc["timestampSource"] = "unavailable"
    doc.pop("verifiedAt", None)
    doc["migrationNote"] = (
        "This verdict describes an earlier snapshot of the run (it reports run.json status "
        "'running' and an empty final.json sourceRegistry, neither true of the run as it "
        "currently stands) and its own verifiedAt postdated the run's completedAt -- an "
        "impossible sequence. The verdict CONTENT is preserved unedited for audit; it was not "
        "re-run as part of this metadata migration (that requires a real re-verification pass, "
        "out of scope here). Treat this file's `checks`/`summary` as stale pending re-verification."
    )
    _write(gv_path, doc)
    changes.append("verification/global-verification.json: nulled timestamp, flagged as a stale snapshot "
                    "(verdict content preserved, not re-run)")
    return changes


def repair_run_json(run_dir: Path) -> list:
    rj = run_dir / "run.json"
    changes = []
    if not rj.is_file():
        return changes
    doc = _load(rj)
    doc.pop("startedAt", None)
    doc.pop("completedAt", None)
    doc["runCreatedAt"] = None
    doc["runCompletedAt"] = None
    doc["timestampSource"] = "unavailable"
    _write(rj, doc)
    changes.append("run.json: replaced fabricated startedAt/completedAt with null runCreatedAt/runCompletedAt "
                    "+ timestampSource: unavailable")
    return changes


def build_scope_disclaimer(bundle: dict) -> str:
    out_of_scope = (bundle.get("scope") or {}).get("outOfScope") or []
    description = (bundle.get("scope") or {}).get("description", "")
    parts = [description] if description else []
    for entry in out_of_scope:
        parts.append(f"{entry['topic']} is explicitly out of scope: {entry['reason']} "
                      f"See {entry['companionWorkflow']} instead.")
    return " ".join(parts)


def repair_final_json(run_dir: Path, bundle: dict) -> list:
    final_path = run_dir / "final" / "final.json"
    changes = []
    if not final_path.is_file():
        return changes
    doc = _load(final_path)
    meta = doc.setdefault("studyPlanMeta", {})
    meta["generatedAt"] = None
    meta["timestampSource"] = "unavailable"
    meta["scopeDisclaimer"] = build_scope_disclaimer(bundle)
    _write(final_path, doc)
    changes.append("final/final.json: studyPlanMeta.generatedAt nulled (its microsecond-precision value "
                    "disagreed with the rest of the run's timeline and could not be confirmed authentic) "
                    "+ timestampSource: unavailable; added scopeDisclaimer naming every out-of-scope topic")
    return changes


_SCOPE_LEFTOVER_MARKERS = ("**Scope:**", "DSA preparation is not covered", "DSA preparation not included")


def repair_report_md(run_dir: Path, bundle: dict, run_json: dict) -> list:
    """Idempotent by construction: every step first REMOVES whatever a prior
    migration pass left behind (an existing "## Scope" section, any
    "**Scope:**" bullet, the original raw DSA-scope caveat line) before
    inserting exactly one fresh copy -- re-running this against an
    already-migrated report.md must never accumulate duplicates (the bug a
    reviewer caught: 3 runs produced 3 "**Scope:**" bullets, because the
    original version only ever prepended, never deduplicated)."""
    report_path = run_dir / "final" / "report.md"
    changes = []
    if not report_path.is_file():
        return changes
    text = report_path.read_text(encoding="utf-8")

    # 1. Run-section timestamps must match run.json's own (now-nulled) values,
    #    never leave the old fabricated Started/Completed strings in place.
    started = run_json.get("runCreatedAt") or "Unavailable"
    completed = run_json.get("runCompletedAt") or "Unavailable"
    text = re.sub(r"- \*\*Started:\*\* .*", f"- **Started:** {started}", text)
    text = re.sub(r"- \*\*Completed:\*\* .*", f"- **Completed:** {completed}", text)

    # 2. Remove any existing "## Scope" section entirely (idempotency).
    text = re.sub(r"\n## Scope\n.*?(?=\n## |\Z)", "\n", text, flags=re.DOTALL)

    # 3. Strip any leftover scope-duplicating lines wherever they appear
    #    (buggy "**Scope:**" bullets from a prior migration; the original
    #    raw DSA-scope caveat that the new dedicated section supersedes).
    text = "\n".join(l for l in text.splitlines()
                      if not any(marker in l for marker in _SCOPE_LEFTOVER_MARKERS))

    # 4. Insert exactly one fresh, dedicated Scope section (per the requested
    #    format), right after ## Run / before ## Nodes.
    scope_section = ("\n## Scope\n\n"
                      "This workflow produces a backend and AI systems study plan.\n"
                      "DSA preparation is intentionally outside this contract.\n")
    if "\n## Nodes" in text:
        text = text.replace("\n## Nodes", scope_section + "\n## Nodes", 1)
    else:
        text = text.rstrip("\n") + "\n" + scope_section

    report_path.write_text(text, encoding="utf-8")
    changes.append("final/report.md: Run-section Started/Completed set to Unavailable (matching run.json), "
                    "duplicate scope mentions collapsed into one dedicated ## Scope section")
    return changes


def migrate(run_dir: Path, bundle_dir: Path, dry_run: bool, context_root: str = None) -> dict:
    changes = []
    backup_path = None
    if not dry_run:
        backup_path = backup(run_dir)
        changes.append(f"backed up pre-migration run to {backup_path.as_posix()}")

    changes += normalize_node_states(run_dir) if not dry_run else ["[dry-run] would normalize node-state files"]
    bundle = _load(bundle_dir / "contract.bundle.json")
    if not dry_run:
        # run.json's timestamps must be repaired BEFORE derived-context is
        # rebuilt below -- it reads run.json's completedAt for its own
        # generatedAt, and node-state must already be normalized (done above)
        # before derived-context reads each node's completedAt.
        changes += repair_run_json(run_dir)
        changes += repair_global_verification(run_dir)
    else:
        changes.append("[dry-run] would repair run.json/global-verification timestamps first")

    trace = build_trace(run_dir, bundle_dir)
    if not dry_run:
        _write(run_dir / "final" / "trace.json", trace)
    changes.append(f"final/trace.json regenerated: byState={trace['summary']['byState']}, "
                   f"invalidRecordCount={trace['summary']['invalidRecordCount']}")

    existing_derived = run_dir / "final" / "derived-context.json"
    prior = _load(existing_derived) if existing_derived.is_file() else None
    derived = build_derived(bundle_dir, run_dir, prior, context_root=context_root)
    if not dry_run:
        _write(run_dir / "final" / "derived-context.json", derived)
    changes.append(f"final/derived-context.json rebuilt: artifactPrivacyClassification="
                    f"{derived['artifactPrivacyClassification']} ({len(derived['entries'])} entries)")

    if not dry_run:
        changes += repair_final_json(run_dir, bundle)
        post_run_json = _load(run_dir / "run.json")
        changes += repair_report_md(run_dir, bundle, post_run_json)
        gov_changes, governance = repair_source_governance(run_dir, bundle_dir, bundle)
        changes += gov_changes
    else:
        changes.append("[dry-run] would repair final.json/report.md/source-governance")
        governance = None

    run_json = _load(run_dir / "run.json") if (run_dir / "run.json").is_file() else {}
    record = {
        "documentType": "ContractGraphMigrationRecord",
        "migrationScript": "migrate_run_metadata.py",
        "runId": run_json.get("runId"),
        "bundleId": bundle.get("bundleId"),
        "runDir": run_dir.as_posix(),
        "appliedAt": _now_iso(),
        "dryRun": dry_run,
        "backupPath": backup_path.as_posix() if backup_path else None,
        "changes": changes,
        "notModified": ["sections/*.json (accepted research content: topics, objectives, resources, milestones)"],
    }
    if not dry_run:
        migrations_dir = run_dir / ".migrations"
        seq = len(list(migrations_dir.glob("*-migration-record.json"))) + 1
        _write(migrations_dir / f"{seq:03d}-migration-record.json", record)
    return record


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"--run": None, "--bundle": None, "--context-root": None}
    dry_run = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]; i += 2
        else:
            i += 1
    if not opts["--run"] or not opts["--bundle"]:
        print("usage: migrate_run_metadata.py --run <run-dir> --bundle <bundle-dir> "
              "[--context-root <dir the run actually used>] [--dry-run]", file=sys.stderr)
        return 2
    run_dir, bundle_dir = Path(opts["--run"]), Path(opts["--bundle"])
    if not run_dir.is_dir() or not bundle_dir.is_dir():
        print(json.dumps({"ok": False, "error": "run or bundle dir not found"}), file=sys.stderr)
        return 2
    try:
        record = migrate(run_dir, bundle_dir, dry_run, opts["--context-root"])
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
