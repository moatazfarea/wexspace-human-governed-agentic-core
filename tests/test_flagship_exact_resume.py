import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from wexspace_human_governed_core.runtime import GovernedRuntime
from wexspace_human_governed_core.state import WorkRepository, NODE_ORDER


class TestFlagshipExactResume(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.state_dir = self.temp_dir / "state"

    def test_interruption_restart_and_side_effect_deduplication(self):
        work_id = "WORK-DISCREPANCY-2026-09"
        inputs = {
            "request_id": "PO-98421",
            "vendor": "Acme Industrial Logistics",
            "expected_quantity": 500,
            "observed_quantity": 415,
            "unit_cost_usd": 50.0,
            "variance_usd": -4250.0
        }

        # PHASE 1: Process A starts and executes Step 1 (inspect_request)
        runtime_a = GovernedRuntime(self.state_dir)
        runtime_a.create_work(work_id, "Reconcile delivery discrepancy for PO-98421", inputs)
        
        # Run exactly 1 step
        status_step1 = runtime_a.run_deterministic(work_id, stop_after=1)
        self.assertEqual(status_step1["work"]["cursor"], 1)
        self.assertEqual(status_step1["work"]["state"], "OPEN")
        
        # Verify inspection passed
        inspect_node = status_step1["nodes"]["inspect_request"]
        self.assertEqual(inspect_node["state"], "PASS")

        # Verify side effect recorded in DB before crash
        self.assertEqual(runtime_a.repo.effect_count(work_id, "tool:inspect_request"), 1)

        # SIMULATE HARD PROCESS / RUNTIME CRASH (Process A is killed)
        del runtime_a

        # PHASE 2: Process B boots freshly from durable SQLite + Evidence Ledger
        runtime_b = GovernedRuntime(self.state_dir)
        recovered_work = runtime_b.repo.work(work_id)
        
        # Verify cursor recovery
        self.assertEqual(recovered_work["cursor"], 1, "Process B must recover exact cursor=1 without restating context!")
        
        # Resume Process B to completion
        status_final = runtime_b.run_deterministic(work_id)
        self.assertEqual(status_final["work"]["cursor"], 3)
        self.assertEqual(status_final["work"]["state"], "HUMAN_REVIEW")

        # Verify all 3 nodes completed
        self.assertEqual(status_final["nodes"]["inspect_request"]["state"], "PASS")
        self.assertEqual(status_final["nodes"]["reconcile_evidence"]["state"], "PASS")
        self.assertEqual(status_final["nodes"]["prepare_review_package"]["state"], "PASS")

        # Verify NO duplicate side effects were created for inspect_request
        self.assertEqual(runtime_b.repo.effect_count(work_id, "tool:inspect_request"), 1)
        self.assertEqual(runtime_b.repo.effect_count(work_id, "tool:reconcile_evidence"), 1)
        self.assertEqual(runtime_b.repo.effect_count(work_id, "tool:prepare_review_package"), 1)

        # Verify cryptographic ledger integrity
        self.assertTrue(runtime_b.ledger.verify(), "Evidence ledger hash chain must be cryptographically valid!")

        # Export review package
        out_dir = self.temp_dir / "review_package"
        dec_path, ev_path = runtime_b.export_review_package(work_id, out_dir)
        self.assertTrue(dec_path.exists())
        self.assertTrue(ev_path.exists())

        decision = json.loads(dec_path.read_text())
        self.assertEqual(decision["decision_state"], "HUMAN_REVIEW_REQUIRED")
        self.assertFalse(decision["agent_may_auto_approve"])
        self.assertEqual(decision["reconciliation"]["delta"], -85)
        print(f"\nPASS: Exact-Resume Showcase Verified! Discrepancy caught: {decision['reconciliation']['delta']} units (-$4,250)")


if __name__ == "__main__":
    unittest.main()
