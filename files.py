from pathlib import Path

# Root directory (current working directory)
ROOT = Path.cwd()

# Folder structure
folders = [
    ".claude/commands",
    ".claude/agents",
    ".claude/skills/contract-compilation",
    ".claude/skills/evidence-research",
    ".claude/skills/source-verification",
    ".claude/skills/profile-alignment",
    ".claude/skills/skill-optimization",
    ".claude/hooks",
    "contracts/company-research/node-contracts",
    "context/private",
    "context/synthetic",
    "scripts",
    "runtime/cache",
    "runtime/runs",
    "runtime/sections",
    "runtime/traces",
    "runtime/outputs",
    "evals/cases",
    "evals/rubrics",
    "docs",
]

# Files to create
files = [
    "CLAUDE.md",
    "README.md",
    ".gitignore",

    ".claude/settings.json",

    ".claude/commands/contractgraph-init.md",
    ".claude/commands/contractgraph-run.md",
    ".claude/commands/contractgraph-validate.md",

    ".claude/agents/graph-planner.md",
    ".claude/agents/company-intelligence.md",
    ".claude/agents/company-initiatives.md",
    ".claude/agents/dsa-researcher.md",
    ".claude/agents/hld-researcher.md",
    ".claude/agents/lld-researcher.md",
    ".claude/agents/behavioral-researcher.md",
    ".claude/agents/profile-fit-evaluator.md",
    ".claude/agents/section-verifier.md",
    ".claude/agents/global-verifier.md",

    ".claude/skills/contract-compilation/SKILL.md",
    ".claude/skills/evidence-research/SKILL.md",
    ".claude/skills/source-verification/SKILL.md",
    ".claude/skills/profile-alignment/SKILL.md",
    ".claude/skills/skill-optimization/SKILL.md",

    ".claude/hooks/hooks.json",

    "contracts/company-research/contract.schema.json",
    "contracts/company-research/graph.yaml",

    "context/context-manifest.json",

    "scripts/validate_json.py",
    "scripts/merge_sections.py",
    "scripts/context_index.py",
    "scripts/toon_codec.py",

    "docs/architecture.md",
]

def create_structure():
    # Create directories
    for folder in folders:
        path = ROOT / folder
        path.mkdir(parents=True, exist_ok=True)
        print(f"Created: {path.relative_to(ROOT)}")

    # Create files
    for file in files:
        path = ROOT / file
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            path.touch()
            print(f"📄 Created: {path.relative_to(ROOT)}")
        else:
            print(f"⏭️ Exists:  {path.relative_to(ROOT)}")

    print("\n✅ ContractGraph project structure created successfully!")

if __name__ == "__main__":
    create_structure()