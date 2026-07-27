# Verification rubric (model-graded dimensions)

For dimensions a script cannot decide, a verifier subagent grades each node and
returns {status, issues[], repairInstructions[], unsupportedClaims[], staleClaims[], conflicts[], confidence{}}.

| Dimension | Pass condition |
|-----------|----------------|
| contract completeness | every required section/claim substantively present |
| evidence-to-claim support | each public claim has a source that actually supports it |
| source quality | material claims backed by official/primary tiers, anecdotes labelled |
| freshness | time-sensitive claims within policies.json freshnessDays |
| candidate truth boundaries | no invented/overstated experience |
| contradiction detection | no unresolved cross-section conflicts |
| ranking justification | every ranked item cites its rationale |
| project evidence mapping | project claims trace to canonical evidence |
| resume truthfulness | enhancements never assert unproven experience |
