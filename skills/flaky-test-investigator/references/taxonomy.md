# Triage taxonomy and decision order

Rules apply in this order. The first that matches wins; everything else that also matched is recorded as an alternative hypothesis.

1. **Fewer than 3 runs:** `INSUFFICIENT_EVIDENCE`, Low.
2. **No failures:** `STABLE`, High.
3. **Commit-correlated** (every run passes before commit X, every run fails from X on):
   - dominant error class `locator`: `SELECTOR_CHURN`
   - anything else: `APP_REGRESSION`. If failures also concentrate on one environment, confidence drops to Medium and both hypotheses are reported.
4. **Infra errors dominate, or failures concentrate on one environment** (that env at least 60 percent failing, all others at most 10 percent): `ENVIRONMENT_INSTABILITY`.
5. **Conflict or duplicate errors dominate:** `TEST_DATA_COLLISION`. High confidence when a failing run shared a `data_key` with another run in the same `window`.
6. **Timeout errors dominate, or the same commit both passes and fails with a meaningful error:** `TIMING_RACE`.
7. **Otherwise:** `UNCLASSIFIED`, Low, with a logging-gap note when errors are generic.

## Error classes

Matched case-insensitively against the first line of the failure.

| Class | Patterns |
| --- | --- |
| locator | element not found, no such element, locator, selector, not attached to the DOM, strict mode violation |
| data_conflict | 409, duplicate, unique constraint, already exists, conflict |
| infra | ECONNRESET, ECONNREFUSED, 502, 503, 504, DNS, out of memory, OOM, runner lost, no space left, certificate |
| timeout | timeout, timed out, exceeded N ms |
| assertion | expected, assert, to equal, to be, mismatch |

Extend the patterns for your stack, then add a fixture and expected result to keep the rules honest.

## Confidence

- **High:** signals agree and there are at least 6 runs.
- **Medium:** fewer runs, or a second signal partly disagrees.
- **Low:** insufficient or contradictory evidence.

Confidence describes the strength of the evidence supplied, not a measured accuracy rate.
