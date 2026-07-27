# Generated Subagents — company-research

Generated from `contracts/company-research/contract.bundle.json` (bundle v1.0.0), `graph.yaml`, `policies.json`, and each node's `node-contracts/*.contract.json`. All agent files live in this directory (`.claude/agents/generated/`).

| nodeId | model | tools | dependsOn | output path |
|---|---|---|---|---|
| company-intelligence | sonnet | WebSearch, WebFetch, Read, Write | (none — foundation) | `runtime/sections/company-intelligence.json` |
| role-intelligence | sonnet | WebSearch, WebFetch, Read, Write | company-intelligence | `runtime/sections/role-intelligence.json` |
| company-initiatives | sonnet | WebSearch, WebFetch, Read, Write | company-intelligence, role-intelligence | `runtime/sections/company-initiatives.json` |
| interview-process | sonnet | WebSearch, WebFetch, Read, Write | company-intelligence, role-intelligence | `runtime/sections/interview-process.json` |
| dsa | sonnet | WebSearch, WebFetch, Read, Write | role-intelligence, interview-process | `runtime/sections/dsa.json` |
| cs-fundamentals | sonnet | WebSearch, WebFetch, Read, Write | role-intelligence, interview-process | `runtime/sections/cs-fundamentals.json` |
| domain-knowledge | sonnet | WebSearch, WebFetch, Read, Write | company-intelligence, company-initiatives, role-intelligence | `runtime/sections/domain-knowledge.json` |
| hld | sonnet | WebSearch, WebFetch, Read, Write | company-intelligence, company-initiatives, role-intelligence, interview-process | `runtime/sections/hld.json` |
| lld | sonnet | WebSearch, WebFetch, Read, Write | company-intelligence, company-initiatives, role-intelligence, interview-process | `runtime/sections/lld.json` |
| behavioral | sonnet | WebSearch, WebFetch, Read, Write | company-intelligence, role-intelligence, interview-process | `runtime/sections/behavioral.json` |
| profile-alignment | sonnet | Read, Write | company-intelligence, company-initiatives, role-intelligence, domain-knowledge | `runtime/sections/profile-alignment.json` |
| project-deep-dive | sonnet | Read, Write | company-initiatives, role-intelligence, profile-alignment | `runtime/sections/project-deep-dive.json` |
| resume-analysis | sonnet | Read, Write | role-intelligence, profile-alignment, project-deep-dive | `runtime/sections/resume-analysis/<roleId>.json` (fragment; merged into `runtime/sections/resume-analysis.json`) |
| compensation-location | sonnet | WebSearch, WebFetch, Read, Write | company-intelligence, role-intelligence | `runtime/sections/compensation-location.json` |
| networking-referral | sonnet | WebSearch, WebFetch, Read, Write | company-intelligence, role-intelligence, profile-alignment | `runtime/sections/networking-referral.json` |
| application-strategy | sonnet | Read, Write | profile-alignment, resume-analysis, interview-process, compensation-location | `runtime/sections/application-strategy.json` |
| resources | haiku | Read, Write | company-intelligence, company-initiatives, dsa, cs-fundamentals, domain-knowledge, hld, lld, behavioral | `runtime/sections/resources.json` |
| section-verifier | sonnet | Read | (the node under review + its dependencies) | none — returns a verdict, no file written |
| global-verifier | opus | Read | (all required nodes, post-aggregation) | none — returns a verdict, no file written |

## Notes

- `dependsOn` is taken from each node contract's `x-contractgraph.dependsOn` (authoritative per task instructions), which matches `graph.yaml`'s `dependencies` block exactly for all 17 nodes.
- `resume-analysis` is the one mapped node (`graph.yaml` `resume-map` layer, `over: configuredRoles`): it is invoked once per configured role, each invocation writing a per-role fragment. A deterministic merge (outside any agent) combines fragments into the single schema-valid `resume-analysis.json` the node contract actually describes (`roleAnalyses` minItems 5, one `crossResumeRecommendation`).
- Model routing follows `policies.json.models`: `resources` is pure dedup/categorization over already-verified data → haiku (triage tier); every other producer node is sonnet (research/primary tier); `section-verifier` is sonnet (verification.section); `global-verifier` is opus (verification.global).
- Every producer agent is prohibited from self-certifying its own `verification` block — `policies.json.execution.workerCannotSelfApprove` — and none may declare any node other than its own, or the overall workflow, complete. Only `global-verifier` adjudicates overall completion.
- No agent reads `context/private/`.
