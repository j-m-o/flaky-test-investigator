"""Fixture tests for Flaky Test Investigator. Run: python -m unittest discover tests"""
import json
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "flaky-test-investigator"
sys.path.insert(0, str(SKILL / "scripts"))
import investigate  # noqa: E402

FIX = SKILL / "assets" / "fixtures"


class FixtureClassifications(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = investigate.run(json.loads((FIX / "release-4.2-reruns.json").read_text()))
        cls.by_id = {r["test_id"]: r for r in cls.report["results"]}

    def test_each_test_matches_expected_class(self):
        expected = json.loads((FIX / "expected-classifications.json").read_text())
        for tid, cls_ in expected.items():
            with self.subTest(test=tid):
                self.assertEqual(self.by_id[tid]["classification"], cls_, self.by_id[tid]["evidence"])

    def test_only_true_regression_is_flagged_real(self):
        self.assertEqual(self.report["real_regressions"], ["T-101"])

    def test_unknowns_are_not_noise_or_pass(self):
        for tid in ("T-107", "T-108"):
            self.assertNotIn(tid, self.report["noise"])
            self.assertFalse(self.by_id[tid]["real_regression"])

    def test_first_failing_commit_reported(self):
        self.assertEqual(self.by_id["T-101"]["first_failing_commit"], "b2")


class Rules(unittest.TestCase):
    def runs(self, spec):
        return {"id": "X", "runs": [{"commit": c, "env": e, "outcome": o, "error": err} for c, e, o, err in spec]}

    def test_commit_beats_environment_and_reports_both(self):
        t = self.runs([("a", "east", "pass", None), ("a", "west", "pass", None),
                       ("b", "west", "fail", "expected 1 to equal 2"), ("b", "west", "fail", "expected 1 to equal 2")])
        r = investigate.investigate(t)
        self.assertEqual(r["classification"], "APP_REGRESSION")
        self.assertTrue(r["alternative_hypotheses"])

    def test_error_classifier(self):
        self.assertEqual(investigate.classify_error("locator('#x') element not found"), "locator")
        self.assertEqual(investigate.classify_error("503 Service Unavailable"), "infra")
        self.assertEqual(investigate.classify_error("409 Conflict"), "data_conflict")
        self.assertEqual(investigate.classify_error("Something went wrong"), "unknown")


if __name__ == "__main__":
    unittest.main()
