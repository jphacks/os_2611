import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "research", ROOT / ".agents/skills/work-context/scripts/research.py")
research = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research)


def brief():
    today = date.today().isoformat()
    return {"as_of": today, "scope": "合成テスト：学修支援",
            "sources": [{"id": "s1", "title": "Public guidance", "url": "https://example.org/help",
                         "accessed_at": today, "published_at": None}],
            "findings": [{"kind": "fact", "text": "公開案内がある", "source_ids": ["s1"],
                          "relevance": "利用条件の確認に使う"}],
            "coverage": {"direct": ["公式案内"], "adjacent": [], "counter": [],
                         "gaps": ["個人への適用は未確認"]}}


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / ".private"

    def call(self, action, **kw):
        return research.handle(dict(action=action, **kw), self.directory)

    def test_worker_no_finance_by_default(self):
        plan = self.call("plan", context={"audience": "worker", "organization": "架空会社",
                                          "role": "一般事務", "topics": ["資料整理"]})
        self.assertNotIn("決算", json.dumps(plan, ensure_ascii=False))
        self.assertEqual({q["purpose"] for q in plan["searches"]},
                         {"public_background", "direct", "adjacent", "counter"})

    def test_student_context_and_owner_finance_opt_in(self):
        plan = self.call("plan", context={"audience": "student", "organization": "架空大学",
                                          "major": "芸術学", "topics": ["学修支援"]})
        self.assertIn("学科", plan["searches"][0]["query"])
        owner = self.call("plan", context={"audience": "owner"})
        self.assertFalse(owner["financial_context_required"])
        owner = self.call("plan", context={"audience": "owner", "financial_context_required": True})
        self.assertTrue(any(q["purpose"] == "financial_task" for q in owner["searches"]))

    def test_reject_private_context_keys(self):
        with self.assertRaisesRegex(research.Error, "invalid_context"):
            self.call("plan", context={"audience": "worker", "private_notes": "PRIVATE"})

    def test_read_and_validate_do_not_write_or_claim_verification(self):
        self.assertEqual(self.call("status")["state"]["revision"], 0)
        self.assertFalse(self.call("validate", report=brief())["evidence_verified"])
        self.assertFalse(self.directory.exists())

    def test_ref_integrity(self):
        report = brief()
        report["findings"][0]["source_ids"] = ["invented"]
        with self.assertRaisesRegex(research.Error, "invalid_report"):
            self.call("validate", report=report)

    def test_fact_needs_source_question_may_have_none(self):
        report = brief()
        report["findings"][0]["source_ids"] = []
        with self.assertRaisesRegex(research.Error, "invalid_report"):
            self.call("validate", report=report)
        report["findings"][0]["kind"] = "question"
        self.assertTrue(self.call("validate", report=report)["ok"])

    def test_no_unknown_date_as_freshness(self):
        report = brief()
        report["sources"][0]["published_at"] = "9999-01-01"
        with self.assertRaisesRegex(research.Error, "invalid_report"):
            self.call("validate", report=report)

    def test_duplicate_sources_and_nonweb_urls(self):
        report = brief()
        report["sources"].append(copy.deepcopy(report["sources"][0]))
        with self.assertRaisesRegex(research.Error, "invalid_report"):
            self.call("validate", report=report)
        report = brief()
        report["sources"][0]["url"] = "file:///private/file"
        with self.assertRaisesRegex(research.Error, "invalid_report"):
            self.call("validate", report=report)

    def test_save_compare_and_conflict(self):
        report = brief()
        self.call("save", confirmed=True, expected_revision=0, report=report)
        changed = copy.deepcopy(report)
        changed["findings"][0]["text"] = "案内が改定された"
        diff = self.call("compare", report=changed)["diff"]
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(len(diff["not_in_latest"]), 1)
        self.assertEqual(self.call("status")["state"]["report"], report)
        with self.assertRaisesRegex(research.Error, "revision_conflict"):
            self.call("save", confirmed=True, expected_revision=0, report=changed)

    def test_no_consent_and_clear(self):
        with self.assertRaisesRegex(research.Error, "consent_required"):
            self.call("save", confirmed=False, expected_revision=0, report=brief())
        self.assertFalse(self.directory.exists())
        self.call("save", confirmed=True, expected_revision=0, report=brief())
        self.call("clear", confirmed=True, expected_revision=1)
        state = self.call("status")["state"]
        self.assertEqual(state, {"revision": 2, "report": None})

    def test_corrupt_storage_and_symlink(self):
        self.directory.mkdir()
        path = self.directory / "research.json"
        path.write_text("broken")
        with self.assertRaisesRegex(research.Error, "invalid_state"):
            self.call("save", confirmed=True, expected_revision=0, report=brief())
        self.assertEqual(path.read_text(), "broken")

    def test_symlink_and_busy(self):
        self.directory.mkdir()
        outside = Path(self.tmp.name) / "outside"
        outside.write_text("PRIVATE")
        (self.directory / "research.json").symlink_to(outside)
        with self.assertRaisesRegex(research.Error, "unsafe_path"):
            self.call("status")
        self.assertEqual(outside.read_text(), "PRIVATE")

    def test_research_storage_does_not_change_personal_profile(self):
        research.intake.handle({"action": "apply", "confirmed": True,
                                "expected_revision": 0,
                                "profile": {"role": "学生", "major": "芸術学"}}, self.directory)
        before = (self.directory / "state.json").read_bytes()
        self.call("save", confirmed=True, expected_revision=0, report=brief())
        self.assertEqual((self.directory / "state.json").read_bytes(), before)

    def test_live_public_examples_match_report_contract(self):
        for name in ("worker-brief.json", "student-brief.json"):
            with self.subTest(name=name):
                report = json.loads((ROOT / "examples" / name).read_text())
                result = self.call("validate", report=report)
                self.assertTrue(result["ok"])
                self.assertFalse(result["evidence_verified"])


if __name__ == "__main__":
    unittest.main()
