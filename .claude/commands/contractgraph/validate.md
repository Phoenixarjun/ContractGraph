---
description: Run the deterministic structural validators over a contract bundle, canonical context, and (if present) the compiled graph. Reports machine-readable pass/fail.
argument-hint: [optional: bundle dir, default contracts/study-plan] [--context <dir>]
allowed-tools: Read, Bash, Glob
---

Bundle directory from the user (may be empty): $ARGUMENTS
Default bundle: `contracts/study-plan`
Default context root: `context` — override with `--context <dir>` (the shipped study-plan example uses `--context context/synthetic/study-plan`).

Steps:
1. Resolve the bundle directory (argument, else default) and read its `bundleId` from `contract.bundle.json`.
2. Run `python scripts/validate_contract_bundle.py <bundleDir>`. Capture stdout/stderr and exit code.
3. Run `python scripts/validate_context.py <context-root>`. Capture stdout/stderr and exit code.
4. If `runtime/compiled/<bundleId>/graph.json` exists, run `python scripts/validate_compiled_graph.py runtime/compiled/<bundleId>/graph.json`. Capture stdout/stderr and exit code. If it does not exist, note that the bundle has not been compiled yet — this is not a failure.
5. **Optional artifact checks** (when the user passes a target file):
   - `--node-output <file> --node <id>` → `python scripts/validate_node_output.py <file> --bundle <bundleDir> --node <id>` (structural, against the exact node contract).
   - `--final <file>` → `python scripts/validate_final_output.py <file> --bundle <bundleDir>` then `python scripts/validate_references.py <file> --bundle <bundleDir>`.
   - add `--check-urls` to also run `python scripts/validate_source_urls.py <file> --check-network` (reachability; otherwise URLs are only format-checked).
6. Report a short pass/fail table, one row per check run, with exit code. For any failure, quote the exact validator error lines (do not paraphrase them) and identify the specific file and field they point to.

Do not modify any contract, context, or compiled file — this command only reports. Never redesign or regenerate a bundle's contracts here; that is `/contractgraph:contract`.
