import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ledgerspec_lh.cli import load_input, run_batch
from ledgerspec_lh.core import Blocked
from ledgerspec_lh.reconciliation import BankReconciler


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "run"
        self.bank = load_input(EXAMPLES / "reconciliation.json")
        self.journal = load_input(EXAMPLES / "journal.json")

    def test_reconcile_and_read_completed_receipt(self):
        first = run_batch("BANK_RECONCILIATION", self.bank, self.output, "example")
        rec = first["workpaper"]["output"]["reconciliation"]
        self.assertEqual([(x["ledger_id"], x["bank_id"]) for x in rec["matches"]], [("L1", "B1")])
        self.assertEqual([x["bank_id"] for x in rec["review_relationships"]], ["B2"])
        self.assertEqual(rec["accounting_postings"], 0)
        self.assertEqual(first, run_batch("BANK_RECONCILIATION", self.bank, self.output, "example"))

    def test_changed_input_cannot_reuse_workspace(self):
        run_batch("BANK_RECONCILIATION", self.bank, self.output, "example")
        altered = copy.deepcopy(self.bank)
        altered["bank_lines"][0]["amount"] = "99.99"
        with self.assertRaisesRegex(ValueError, "BINDING_DRIFT"):
            run_batch("BANK_RECONCILIATION", altered, self.output, "example")

    def test_corrupt_workpaper_is_rejected(self):
        first = run_batch("BANK_RECONCILIATION", self.bank, self.output, "example")
        artifact = self.output / "artifacts" / (first["artifact_sha256"] + ".json")
        artifact.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(Blocked, "ARTIFACT_CORRUPTION"):
            run_batch("BANK_RECONCILIATION", self.bank, self.output, "example")

    def test_missing_receipt_fails_closed(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "JOURNAL_MISSING_NO_RECREATE"):
            run_batch("BANK_RECONCILIATION", self.bank, self.output, "example")

    def test_balanced_and_one_cent_unbalanced(self):
        result = run_batch("GENERAL_JOURNALS", self.journal, self.output, "journal")
        self.assertEqual(result["workpaper"]["output"]["decisions"][0]["status"], "ACCEPTED")
        self.journal["journal_lines"][0]["debit_amount"] = "100.01"
        result = run_batch("GENERAL_JOURNALS", self.journal, self.output.with_name("diff"), "journal")
        item = result["workpaper"]["output"]["decisions"][0]
        self.assertEqual((item["status"], item["difference_cents"]), ("UNBALANCED", 1))

    def test_duplicate_bank_records_remain_for_review(self):
        other = {**self.bank["bank_lines"][0], "id": "B3"}
        rec = BankReconciler().reconcile(self.bank["ledger_entries"], self.bank["bank_lines"] + [other])
        self.assertEqual(rec["predicted_pair_count"], 0)
        self.assertIn(["B1", "B3"], rec["duplicate_bank_groups"])

    def test_duplicate_json_keys_rejected(self):
        source = self.output.with_name("duplicate.json")
        source.write_text('{"ledger_entries":[],"ledger_entries":[]}', encoding="utf-8")
        with self.assertRaisesRegex(Blocked, "DUPLICATE_INPUT_KEY"):
            load_input(source)


if __name__ == "__main__":
    unittest.main()
