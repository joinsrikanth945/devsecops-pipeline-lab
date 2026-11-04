"""Tests for scripts/gate.py: the branch policy must behave exactly as taught.

Run:  python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_gate(env):
    """Import gate.py fresh with the given environment (it reads env at import)."""
    with mock.patch.dict(os.environ, env, clear=False):
        spec = importlib.util.spec_from_file_location("gate", ROOT / "scripts" / "gate.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name in ("gitleaks.json", "semgrep.json", "trivy.json"):
            shutil.copy(FIXTURES / name, self.tmp / name)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_gate(self, event="push", branch="main", **extra):
        env = {"REPORTS_DIR": str(self.tmp), "GITHUB_EVENT_NAME": event,
               "GITHUB_REF": f"refs/heads/{branch}", "GITHUB_STEP_SUMMARY": ""}
        env.update(extra)
        with mock.patch.dict(os.environ, env):
            gate = load_gate(env)
            summary = gate.summarize()
            code = gate.enforce()
        return summary, code

    def test_counts_are_read_from_each_report(self):
        summary, _ = self.run_gate()
        s = summary["scanners"]
        self.assertEqual(s["secrets"]["counts"]["high"], 1)
        self.assertEqual((s["sast"]["counts"]["high"], s["sast"]["counts"]["medium"], s["sast"]["counts"]["low"]), (1, 1, 1))
        self.assertEqual((s["image"]["counts"]["critical"], s["image"]["counts"]["high"]), (1, 2))

    def test_main_is_blocked_by_findings(self):
        summary, code = self.run_gate(branch="main")
        self.assertEqual((summary["result"], summary["mode"], code), ("BLOCKED", "blocking", 1))

    def test_testing_push_is_advisory(self):
        summary, code = self.run_gate(branch="testing")
        self.assertEqual((summary["result"], summary["mode"], code), ("ADVISORY", "advisory", 0))

    def test_pull_request_to_testing_is_not_advisory(self):
        summary, code = self.run_gate(event="pull_request", branch="testing")
        self.assertEqual((summary["result"], code), ("BLOCKED", 1))

    def test_clean_reports_pass_everywhere(self):
        (self.tmp / "gitleaks.json").write_text("[]")
        (self.tmp / "semgrep.json").write_text('{"results": []}')
        (self.tmp / "trivy.json").write_text('{"ArtifactName": "x", "Results": []}')
        summary, code = self.run_gate(branch="main")
        self.assertEqual((summary["result"], code), ("PASS", 0))

    def test_missing_report_is_an_error_even_on_testing(self):
        (self.tmp / "semgrep.json").unlink()
        summary, code = self.run_gate(branch="testing")
        self.assertEqual((summary["result"], code), ("ERROR", 1))
        self.assertIn("missing", summary["scanners"]["sast"]["reason"])

    def test_broken_json_is_an_error(self):
        (self.tmp / "trivy.json").write_text("{not json")
        summary, code = self.run_gate(branch="testing")
        self.assertEqual((summary["result"], code), ("ERROR", 1))

    def test_thresholds_can_be_relaxed(self):
        # Only image findings would block; SAST and secrets set to not block.
        (self.tmp / "trivy.json").write_text('{"ArtifactName": "x", "Results": []}')
        summary, code = self.run_gate(branch="main", BLOCK_ON_SECRETS="0", BLOCK_ON_SAST="none")
        self.assertEqual((summary["result"], code), ("PASS", 0))

    def test_step_summary_table_is_written(self):
        target = self.tmp / "step.md"
        self.run_gate(branch="main", GITHUB_STEP_SUMMARY=str(target))
        text = target.read_text()
        self.assertIn("Security result: BLOCKED", text)
        self.assertIn("| image | ok | 1 | 2 |", text)

    def test_summary_file_is_valid_json(self):
        self.run_gate(branch="testing")
        data = json.loads((self.tmp / "summary.json").read_text())
        self.assertEqual(data["branch"], "testing")


if __name__ == "__main__":
    unittest.main()
