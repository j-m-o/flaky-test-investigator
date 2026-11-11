#!/usr/bin/env python3
"""Flaky Test Investigator: deterministic triage of rerun evidence.

Separates application regressions from environment instability, selector
churn, test-data collisions and timing races, using only the run evidence it
is handed. It never reruns, quarantines or edits tests.

Read-only. Standard library only. No network access.

Flaky Test Investigator, created by Jessica Mosley | LinkedIn: https://www.linkedin.com/in/jessmosley/ | GitHub: https://github.com/j-m-o/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

VERSION = "1.0.0"
ERROR_CLASSES = [
    ("locator", r"element not found|no such element|locator|selector|not attached to the dom|strict mode violation"),
    ("data_conflict", r"\b409\b|duplicate|unique constraint|already exists|conflict"),
    ("infra", r"econnreset|econnrefused|\b50[234]\b|dns|out of memory|oom|runner lost|no space left|certificate"),
    ("timeout", r"timeout|timed out|exceeded \d+ ?ms"),
    ("assertion", r"expected|assert|to equal|to be|mismatch"),
]
NEXT_STEP = {
    "APP_REGRESSION": "Treat as a real defect. Link the first failing commit to the owning team; do not quarantine.",
    "SELECTOR_CHURN": "Confirm whether the UI change was intended. If so, update the locator to a stable test id; if not, it is a defect.",
    "ENVIRONMENT_INSTABILITY": "Route to the platform owner for the affected runner or dependency. Test code is likely fine.",
    "TEST_DATA_COLLISION": "Isolate test data per run (unique keys or per-worker fixtures) before rerunning in parallel.",
    "TIMING_RACE": "Replace fixed waits with condition waits on the awaited state; review async ordering.",
    "STABLE": "No action.",
    "INSUFFICIENT_EVIDENCE": "Collect at least 3 runs, ideally across 2 environments and 2 commits, before classifying.",
    "UNCLASSIFIED": "Signals do not agree. Hand to a QE engineer with the evidence below.",
}


def classify_error(sig: str | None) -> str:
    s = (sig or "").lower()
    for name, pattern in ERROR_CLASSES:
        if re.search(pattern, s):
            return name
    return "unknown"


def rate(runs):
    return sum(r["outcome"] == "fail" for r in runs) / len(runs) if runs else 0.0


def commit_correlated(runs) -> tuple[bool, str | None]:
    """True when every run on early commits passes and every run from some commit on fails."""
    order, by_commit = [], defaultdict(list)
    for r in runs:
        if r["commit"] not in by_commit:
            order.append(r["commit"])
        by_commit[r["commit"]].append(r)
    rates = [rate(by_commit[c]) for c in order]
    for i in range(1, len(order)):
        if all(x == 0 for x in rates[:i]) and all(x == 1 for x in rates[i:]):
            return True, order[i]
    return False, None


def env_concentrated(runs) -> tuple[bool, str | None]:
    by_env = defaultdict(list)
    for r in runs:
        by_env[r.get("env", "unknown")].append(r)
    if len(by_env) < 2:
        return False, None
    rates = {e: rate(rs) for e, rs in by_env.items()}
    worst = max(rates, key=rates.get)
    others = [v for e, v in rates.items() if e != worst]
    return (rates[worst] >= 0.6 and max(others) <= 0.1), worst


def data_overlap(runs) -> bool:
    """True when a failing run shared its data key with another run in the same time window."""
    windows = defaultdict(list)
    for r in runs:
        if r.get("data_key") and r.get("window"):
            windows[(r["data_key"], r["window"])].append(r)
    return any(len(v) > 1 and any(x["outcome"] == "fail" for x in v) for v in windows.values())


def investigate(test: dict) -> dict:
    runs = test["runs"]
    fails = [r for r in runs if r["outcome"] == "fail"]
    out = {"test_id": test["id"], "name": test.get("name", test["id"]), "runs": len(runs),
           "flake_rate": round(rate(runs), 2), "evidence": [], "alternative_hypotheses": []}

    def done(cls: str, conf: str) -> dict:
        out.update(classification=cls, confidence=conf, recommended_next_step=NEXT_STEP[cls],
                   real_regression=cls == "APP_REGRESSION",
                   owner_decision_needed=cls not in {"STABLE", "INSUFFICIENT_EVIDENCE"})
        return out

    if len(runs) < 3:
        out["evidence"].append(f"Only {len(runs)} run(s) supplied.")
        return done("INSUFFICIENT_EVIDENCE", "Low")
    if not fails:
        out["evidence"].append(f"All {len(runs)} runs passed.")
        return done("STABLE", "High")

    classes = defaultdict(int)
    for r in fails:
        classes[classify_error(r.get("error"))] += 1
    dominant = max(classes, key=classes.get)
    out["error_classes"] = dict(classes)
    out["evidence"].append(f"{len(fails)}/{len(runs)} runs failed; dominant error class '{dominant}'.")
    cc, first_bad = commit_correlated(runs)
    ec, bad_env = env_concentrated(runs)
    many = len(runs) >= 6

    if cc:
        out["evidence"].append(f"Every run passes before commit {first_bad} and fails from it onward.")
        out["first_failing_commit"] = first_bad
    if ec:
        out["evidence"].append(f"Failures concentrate on environment '{bad_env}'; other environments pass.")
        out["affected_environment"] = bad_env
    if cc and ec:
        out["alternative_hypotheses"].append("Commit and environment both correlate; confirm by running the failing commit on a healthy environment.")

    if cc:
        if dominant == "locator":
            return done("SELECTOR_CHURN", "High" if many else "Medium")
        if dominant == "infra":
            out["alternative_hypotheses"].append("Infra errors started with a commit; the change may have added a fragile dependency.")
        return done("APP_REGRESSION", "Medium" if ec or not many else "High")
    if dominant == "infra" or ec:
        return done("ENVIRONMENT_INSTABILITY", "High" if (dominant == "infra" and ec) else "Medium")
    if dominant == "data_conflict":
        overlap = data_overlap(runs)
        if overlap:
            out["evidence"].append("Failing runs shared a data key with a concurrent run.")
        return done("TEST_DATA_COLLISION", "High" if overlap else "Medium")
    same_commit_mixed = any(0 < rate([r for r in runs if r["commit"] == c]) < 1 for c in {r["commit"] for r in runs})
    if same_commit_mixed:
        out["evidence"].append("The same commit both passes and fails: nondeterminism inside the test, app or data.")
    if dominant == "timeout" or (same_commit_mixed and dominant != "unknown"):
        return done("TIMING_RACE", "High" if dominant == "timeout" and same_commit_mixed else "Medium")
    if same_commit_mixed:
        out["alternative_hypotheses"].append("Intermittent on the same commit, but error messages are too generic to separate timing, data or environment causes. Improve failure logging.")
    return done("UNCLASSIFIED", "Low")


def run(evidence: dict) -> dict:
    results = [investigate(t) for t in evidence["tests"]]
    counts: dict[str, int] = defaultdict(int)
    for r in results:
        counts[r["classification"]] += 1
    return {
        "specialist": "flaky-test-investigator",
        "version": VERSION,
        "scope": evidence.get("scope", "unspecified"),
        "summary": dict(counts),
        "real_regressions": [r["test_id"] for r in results if r["real_regression"]],
        "noise": [r["test_id"] for r in results if r["classification"] in {"ENVIRONMENT_INSTABILITY", "TEST_DATA_COLLISION", "TIMING_RACE", "SELECTOR_CHURN"}],
        "results": results,
        "note": "Advisory. Quarantine and remediation decisions belong to the QE owner.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("evidence", type=Path)
    a = p.parse_args()
    print(json.dumps(run(json.loads(a.evidence.read_text(encoding="utf-8"))), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
