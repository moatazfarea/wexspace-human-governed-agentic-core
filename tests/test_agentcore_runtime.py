import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from wexspace_human_governed_core.runtime import GovernedRuntime
from wexspace_human_governed_core.agentcore_runtime import AgentCoreDeploymentManifest, AgentCoreRuntime


class TestAgentCoreRuntime(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.state_dir = self.temp_dir / "state"

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_manifest_generation(self):
        manifest = AgentCoreDeploymentManifest()
        d = manifest.to_dict()
        self.assertEqual(d["agent_name"], "WexspaceGovernedAgent")
        self.assertEqual(d["foundation_model"], "amazon.nova-pro-v1:0")
        self.assertEqual(len(d["action_groups"]), 1)
        self.assertIn("/inspect_request", d["action_groups"][0]["api_schema"]["paths"])
        self.assertIn("/reconcile_evidence", d["action_groups"][0]["api_schema"]["paths"])
        self.assertIn("/prepare_review_package", d["action_groups"][0]["api_schema"]["paths"])

    def test_health_check(self):
        runtime = AgentCoreRuntime(self.state_dir)
        health = runtime.health_check()
        self.assertEqual(health["status"], "HEALTHY")
        self.assertEqual(health["governance_mode"], "FAIL_CLOSED_HUMAN_GATE")

    def test_governed_execution_halts_at_human_review(self):
        inputs = {"request_id": "REQ-001", "expected_quantity": 10, "observed_quantity": 9}
        gov_runtime = GovernedRuntime(self.state_dir)
        work_id = "work-agentcore-001"
        gov_runtime.create_work(work_id, "Reconcile receiving evidence", inputs)

        agentcore = AgentCoreRuntime(self.state_dir)
        res = agentcore.execute_governed_turn(work_id, "Please reconcile this receiving discrepancy.")

        self.assertEqual(res["status"], "HALTED_AT_HUMAN_REVIEW")
        self.assertTrue(res["human_decision_required"])
        self.assertEqual(res["cursor"], 3)
        self.assertEqual(res["phase"], "HUMAN_REVIEW")
        self.assertEqual(res["executed_actions"], ["inspect_request", "reconcile_evidence", "prepare_review_package"])

        # Verify side effects in ledger
        ledger_types = [e["event"]["type"] for e in gov_runtime.ledger.read_all()]
        self.assertIn("agentcore_invocation_started", ledger_types)
        self.assertIn("agentcore_invocation_completed", ledger_types)
        self.assertIn("node_pass", ledger_types)


if __name__ == "__main__":
    unittest.main()
