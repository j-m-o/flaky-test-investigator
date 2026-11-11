# Output contract

Orchestrators depend on these fields. Changing them is a breaking change and needs a major version bump.

```json
{
  "specialist": "flaky-test-investigator",
  "version": "1.0.0",
  "scope": "string",
  "summary": {"APP_REGRESSION": 1, "TIMING_RACE": 1},
  "real_regressions": ["T-101"],
  "noise": ["T-103", "T-105"],
  "results": [
    {
      "test_id": "T-101",
      "name": "checkout: apply promo code",
      "runs": 6,
      "flake_rate": 0.67,
      "classification": "APP_REGRESSION",
      "confidence": "High | Medium | Low",
      "evidence": ["human-readable evidence lines"],
      "alternative_hypotheses": [],
      "first_failing_commit": "b2 (when commit-correlated)",
      "affected_environment": "ci-west (when environment-concentrated)",
      "recommended_next_step": "string",
      "real_regression": true,
      "owner_decision_needed": true
    }
  ],
  "note": "Advisory. Quarantine and remediation decisions belong to the QE owner."
}
```

## How callers should use it

- `real_regressions` non-empty: a quality blocker candidate. Release Readiness Council treats it as evidence for a hold.
- `noise`: route to the owner named by class (platform for environment, QE for data and timing, product team for selector churn).
- `INSUFFICIENT_EVIDENCE` or `UNCLASSIFIED`: report as unknown. Never count as passing.
