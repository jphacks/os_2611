import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from datetime import date
from test_catalog import candidate, source

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/find-capabilities/scripts/recommend.py"
spec = importlib.util.spec_from_file_location("recommend", SCRIPT)
recommend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recommend)


def request():
    return {"action": "recommend", "language": "ja-JP",
            "preferences": {"allow_new_accounts": True, "allow_setup": True}, "host_inventory_checked": True,
            "task": {"summary": "会議後の決定事項を整理する", "desired_output": "決定事項と次の作業を分けて一覧にしてください"},
            "pool": {"action": "evaluate", "host": "Codex", "as_of": date.today().isoformat(),
                     "sources": [source()], "candidates": [candidate()]},
            "assessments": [{"id": "tool", "match": "direct", "reason": "合成テストの作業に対応する", "source_ids": ["s1"]}],
            "available_tools": []}


def existing():
    return {"id": "current", "name": "既存の文章整理", "match": "direct",
            "reason": "指定された文章だけで一覧を作れる", "permission": "available",
            "account": "existing", "cost": "existing_quota",
            "scope": "利用者が指定した会議メモ", "data_flow": "利用中のAIサービスで処理する",
            "limitations": ["外部アプリへの書き込みは行わない"],
            "observation": {"host": "Codex", "checked_at": date.today().isoformat(),
                            "evidence": "Synthetic host observation; no actual tool executed"}}


class RecommendationTests(unittest.TestCase):
    def test_existing_direct_avoids_install(self):
        req = request(); req["available_tools"] = [existing()]
        before = copy.deepcopy(req)
        r = recommend.handle(req)
        self.assertEqual(r["selection"]["state"], "use_existing")
        self.assertEqual(r["selection"]["id"], "current")
        self.assertFalse(r["executed"]); self.assertFalse(r["persisted"])
        self.assertEqual(req, before)

    def test_fit_precedes_official_source(self):
        req = request(); a = req["pool"]["candidates"][0]
        b = candidate(); b.update(id="direct", tier="github", locator="https://example.org/direct")
        req["pool"]["candidates"].append(b)
        req["assessments"] = [{"id": a["id"], "match": "partial", "reason": "一部のみ", "source_ids": ["s1"]},
                              {"id": b["id"], "match": "direct", "reason": "作業に直接対応", "source_ids": ["s1"]}]
        self.assertEqual(recommend.handle(req)["selection"]["id"], "direct")

    def test_unknown_direct_does_not_hide_usable_partial(self):
        req = request(); req["pool"]["candidates"][0]["cost"] = "unknown"
        t = existing(); t["match"] = "partial"; req["available_tools"] = [t]
        r = recommend.handle(req)
        self.assertEqual(r["selection"]["id"], "current")
        self.assertIn("一部", r["message"]["coverage"])

    def test_permission_never_becomes_granted(self):
        req = request(); req["pool"]["candidates"] = []; req["assessments"] = []
        t = existing(); t["permission"] = "needs_approval"; req["available_tools"] = [t]
        r = recommend.handle(req)
        self.assertEqual(r["selection"]["state"], "permission_needed")
        self.assertIn("承認手順", r["message"]["next_step"])
        self.assertFalse(r["executed"])

    def test_unknown_cost_of_enabled_tool_is_not_free(self):
        req = request(); req["pool"]["candidates"] = []; req["assessments"] = []
        t = existing(); t["cost"] = "unknown"; req["available_tools"] = [t]
        r = recommend.handle(req)
        self.assertEqual(r["selection"]["state"], "review_needed")
        self.assertIn("費用", r["message"]["unchecked"])

    def test_enabled_tool_requiring_new_account_is_not_ready_now(self):
        req = request(); req["pool"]["candidates"] = []; req["assessments"] = []
        t = existing(); t["account"] = "new"; req["available_tools"] = [t]
        r = recommend.handle(req)
        self.assertEqual(r["selection"]["state"], "choose_setup")
        self.assertIn("別アカウント", r["message"]["account"])

    def test_blocked_and_adjacent_do_not_force_recommendation(self):
        req = request(); req["assessments"][0]["match"] = "adjacent"
        r = recommend.handle(req)
        self.assertIsNone(r["selection"])
        self.assertIn("まだありません", r["message"]["summary"])
        req["assessments"][0]["match"] = "direct"
        req["pool"]["candidates"][0]["compatibility"] = "incompatible"
        self.assertIsNone(recommend.handle(req)["selection"])

    def test_unavailable_existing_not_used(self):
        req = request(); t = existing(); t["permission"] = "unavailable"
        req["available_tools"] = [t]
        self.assertEqual(recommend.handle(req)["selection"]["type"], "candidate")

    def test_missing_or_fabricated_assessment_rejected(self):
        for value in ([], [{"id": "invented", "match": "direct", "reason": "x"}]):
            req = request(); req["assessments"] = value
            with self.assertRaises(recommend.Error): recommend.handle(req)

    def test_host_and_observation_date_must_match(self):
        for field, value in (("host", "OtherHost"), ("checked_at", "2000-01-01")):
            req = request(); t = existing(); t["observation"][field] = value
            req["available_tools"] = [t]
            with self.assertRaises(recommend.Error): recommend.handle(req)

    def test_unknown_language_asks_host_to_translate(self):
        req = request(); req["language"] = "ko-KR"
        r = recommend.handle(req)
        self.assertIsNone(r["message"])
        self.assertTrue(r["host_translation_required"])
        self.assertEqual(r["language"], "ko-KR")

    def test_chinese_terms_and_source_preserved(self):
        req = request(); req["language"] = "zh-CN"
        req["pool"]["candidates"][0]["checks"]["license"] = []
        r = recommend.handle(req)
        self.assertIn("使用许可", r["message"]["unchecked"])
        self.assertEqual(r["selection"]["source_ids"], ["s1"])

    def test_clickable_source_metadata_and_inference_retained(self):
        r = recommend.handle(request())
        s = r["message"]["sources"][0]
        self.assertEqual(s["url"], "https://example.org/tool")
        self.assertIsNone(s["published_at"])
        self.assertEqual(s["accessed_at"], date.today().isoformat())
        self.assertTrue(r["selection"]["reason_is_inference"])
        req = request(); req["assessments"][0]["source_ids"] = ["invented"]
        with self.assertRaises(recommend.Error): recommend.handle(req)

    def test_setup_choice_does_not_claim_tested(self):
        r = recommend.handle(request())
        self.assertEqual(r["selection"]["state"], "choose_setup")
        self.assertEqual(r["selection"]["compatibility"], "documented")
        self.assertIn("まだ設定", r["message"]["summary"])

    def test_no_setup_preference_keeps_candidate_as_comparison(self):
        req = request(); req["preferences"]["allow_setup"] = False
        r = recommend.handle(req)
        self.assertEqual(r["selection"]["state"], "review_only")
        self.assertNotIn(r["message"]["why"], r["message"]["limitations"])
        self.assertEqual(r["message"]["setup_sources"][0]["id"], "s1")

    def test_new_account_preference_is_enforced(self):
        req = request(); req["preferences"]["allow_new_accounts"] = False
        req["pool"]["candidates"][0]["account"] = "new"
        self.assertIsNone(recommend.handle(req)["selection"])

    def test_unchecked_inventory_never_leads_to_setup(self):
        req = request(); req["host_inventory_checked"] = False
        self.assertEqual(recommend.handle(req)["selection"]["state"], "review_only")
        req["available_tools"] = [existing()]
        with self.assertRaisesRegex(recommend.Error, "inventory_not_checked"): recommend.handle(req)

    def test_lightweight_defaults_and_strict_preference_types(self):
        req = request(); del req["preferences"]; del req["host_inventory_checked"]
        self.assertEqual(recommend.handle(req)["selection"]["state"], "review_only")
        req["preferences"] = {"allow_new_accounts": "false", "allow_setup": False}
        with self.assertRaisesRegex(recommend.Error, "invalid_preferences"): recommend.handle(req)

    def test_alternatives_bounded(self):
        req = request(); req["pool"]["candidates"] = []; req["assessments"] = []
        for i in range(7):
            t = existing(); t["id"] = f"tool{i}"; req["available_tools"].append(t)
        self.assertEqual(len(recommend.handle(req)["alternatives"]), 2)

    def test_cli_rejects_bad_input_without_traceback(self):
        p = subprocess.run([sys.executable, str(SCRIPT)], input=b"{bad", capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertFalse(json.loads(p.stdout)["ok"])
        self.assertEqual(p.stderr, b"")

    def test_japanese_experience_examples(self):
        expected = {"worker": ("use_existing", "current-writing"),
                    "blocked": ("permission_needed", "current-writing"),
                    "jphacks": ("use_existing", "host-public-search"),
                    "discovery": ("review_needed", "recommender")}
        for name, (state, selected) in expected.items():
            req = json.loads((ROOT / f"examples/recommend-{name}-ja.json").read_text())
            r = recommend.handle(req)
            self.assertEqual(r["selection"]["state"], state)
            self.assertEqual(r["selection"]["id"], selected)
            self.assertFalse(r["executed"])
            self.assertEqual(r["language"], "ja-JP")
            if name == "discovery":
                self.assertEqual(r["message"]["sources"][0]["url"],
                                 "https://github.com/JasperHye/skill-recommender/blob/main/SKILL.md")


if __name__ == "__main__": unittest.main()
