---
description: Run the deterministic structural validators over a contract bundle, canonical context, and (if present) the compiled graph. Reports machine-readable pass/fail.
argument-hint: [optional: bundle dir, default contracts/company-research]
allowed-tools: Read, Bash, Glob
---

Bundle directory from the user (may be empty): $ARGUMENTS
Default bundle: `contracts/company-research`

Steps:
1. Resolve the bundle directory (argument, else default).
2. Run `python scripts/validate_contract_bundle.py <bundleDir>`. Capture stdout/stderr and exit code.
3. Run `python scripts/validate_context.py context`. Capture stdout/stderr and exit code.
4. If `runtime/compiled/graph.json` exists, run `python scripts/validate_compiled_graph.py runtime/compiled/graph.json`. Capture stdout/stderr and exit code. If it does not exist, note that the graph has not been compiled yet — this is not a failure.
5. Report a short pass/fail table, one row per check run, with exit code. For any failure, quote the exact validator error lines (do not paraphrase them) and identify the specific file and field they point to.

Do not modify any contract, context, or compiled file — this command only reports. If the target is `contracts/company-research`, only validate it; never redesign or regenerate its contracts here.
