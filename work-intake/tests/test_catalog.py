import copy
import importlib.util
import json
from pathlib import Path
import unittest
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("catalog", ROOT / ".agents/skills/find-capabilities/scripts/catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def source():
    return {"id": "s1", "title": "Synthetic official documentation", "url": "https://example.org/tool",
            "accessed_at": date.today().isoformat(), "published_at": None}


def candidate():
    return {"id": "tool", "name": "Synthetic tool", "locator": "https://example.org/tool", "tier": "official", "kind": "skill",
            "fit": "Matches synthetic task", "compatibility": "documented", "account": "none",
            "cost": "free_software", "license": "MIT; inference may cost extra",
            "permissions": ["Read selected files"], "data_flow": "Uses host model",
            "source_ids": ["s1"], "checks": {k: ["s1"] for k in
                ("identity", "entrypoint", "license", "dependencies", "permissions", "data_flow")}, "blockers": []}


class CatalogTests(unittest.TestCase):
    def evaluate(self, candidates):
        return catalog.handle({"action": "evaluate", "host": "Codex", "as_of": date.today().isoformat(),
                               "sources": [source()], "candidates": candidates})

    def test_prefer_existing_host_order_and_no_network(self):
        p = catalog.handle({"action": "plan", "task": "公開情報整理", "host": "Codex"})
        self.assertEqual(p["search_order"], ["builtin", "official", "community", "github"])
        self.assertFalse(p["network_executed"])

    def test_unknown_cannot_be_presented_as_ready(self):
        for field in ("compatibility", "account", "cost"):
            c = candidate(); c[field] = "unknown"
            r = self.evaluate([c])["candidates"][0]
            self.assertEqual(r["review_status"], "needs_review")
            self.assertIn(field, r["missing"])

    def test_missing_license_evidence_and_no_install_claim(self):
        c = candidate(); c["checks"]["license"] = []
        r = self.evaluate([c])["candidates"][0]
        self.assertEqual(r["review_status"], "needs_review")
        self.assertFalse(r["installed"])
        self.assertFalse(r["evidence_verified"])

    def test_blocked_official_does_not_hide_working_community(self):
        a = candidate(); a["compatibility"] = "incompatible"
        b = candidate(); b.update(id="community", tier="community", locator="https://example.org/community")
        r = self.evaluate([a, b])["candidates"]
        self.assertEqual(r[0]["id"], "community")
        self.assertEqual(r[1]["review_status"], "blocked")

    def test_complete_evidence_is_choice_not_test(self):
        r = self.evaluate([candidate()])["candidates"][0]
        self.assertEqual(r["review_status"], "ready_for_user_choice")
        self.assertEqual(r["compatibility"], "documented")
        self.assertFalse(r["installed"])

    def test_reference_and_duplicate_rejection(self):
        a = candidate(); a["checks"]["license"] = ["invented"]
        with self.assertRaises(catalog.Error): self.evaluate([a])
        with self.assertRaises(catalog.Error): self.evaluate([candidate(), candidate()])

    def test_cross_catalog_duplicates_and_credential_urls(self):
        a = candidate(); b = candidate()
        b.update(id="other-catalog", locator="https://EXAMPLE.org/tool/#catalog", tier="github")
        with self.assertRaisesRegex(catalog.Error, "duplicate_locator"): self.evaluate([a, b])
        b["locator"] = "https://user:password@example.org/tool"
        with self.assertRaisesRegex(catalog.Error, "invalid_locator"): self.evaluate([b])

    def test_unknown_fields_and_malformed_enum_are_rejected(self):
        for field, value in (("tier", []), ("compatibility", {}), ("checks", [])):
            c = candidate(); c[field] = value
            with self.assertRaises(catalog.Error): self.evaluate([c])
        with self.assertRaises(catalog.Error):
            catalog.handle({"action": "plan", "task": "x", "host": "x", "private_notes": "secret"})

    def company_packet(self):
        return {"action": "validate_companies", "as_of": date.today().isoformat(), "scope": "Test event",
                "sources": [source()], "companies": [{"name": "架空会社", "entity_scope": "Sponsor subsidiary",
                "relationships": [{"type": "event_sponsor", "status": "documented", "source_ids": ["s1"]},
                                  {"type": "osaka_attendance", "status": "unknown", "source_ids": []}],
                "claims": [{"kind": "inference", "topic": "fit", "text": "Possible relevance", "source_ids": ["s1"]}],
                "gaps": ["No local attendance evidence"]}]}

    def test_sponsorship_does_not_fill_attendance(self):
        p = self.company_packet(); before = copy.deepcopy(p)
        r = catalog.handle(p)
        self.assertTrue(r["ok"])
        self.assertFalse(r["evidence_verified"])
        self.assertEqual(p, before)

    def test_attendance_needs_its_own_reference(self):
        p = self.company_packet(); p["companies"][0]["relationships"][1]["status"] = "documented"
        with self.assertRaisesRegex(catalog.Error, "invalid_relationship"): catalog.handle(p)

    def test_live_examples(self):
        examples = list((ROOT / "examples").glob("jphacks-companies-*.json"))
        self.assertGreaterEqual(len(examples), 3)
        total = 0
        for path in examples:
            p = json.loads(path.read_text()); total += catalog.handle(p)["company_count"]
            for c in p["companies"]:
                for rel in c["relationships"]:
                    if rel["type"] in {"osaka_attendance", "osaka_prize"}:
                        self.assertEqual(rel["status"], "unknown")
        self.assertEqual(total, 28)
        p = json.loads((ROOT / "examples/capabilities.json").read_text())
        self.assertTrue(catalog.handle(p)["ok"])


if __name__ == "__main__": unittest.main()
