import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DESK_LLM"] = "mock"
os.environ["DESK_DATA"] = tempfile.mkdtemp()

from desk import ideation as ide  # noqa: E402
from desk import llm_providers as llm  # noqa: E402

BRIEF = {"topic": "早上不赖床", "audience": "上班族", "taboo": "医疗建议", "refs": ["a", "", "b", "c"]}


class IdeationFlow(unittest.TestCase):
    def setUp(self):
        self.p = ide.create_project(BRIEF)
        self.pid = self.p["id"]

    def test_empty_brief_rejected(self):
        with self.assertRaises(ide.DeskError):
            ide.create_project({"topic": "  "})

    def test_refs_capped_at_three(self):
        self.assertEqual(self.p["brief"]["refs"], ["a", "b", "c"])

    def test_ten_ideas_and_rounds(self):
        p = ide.generate_ideas(self.pid)
        self.assertEqual(len(p["ideas"]), 10)
        p = ide.generate_ideas(self.pid)
        self.assertEqual(len(p["ideas"]), 20)
        self.assertEqual(p["rounds"], 2)

    def test_reject_needs_reason_and_is_persisted(self):
        p = ide.generate_ideas(self.pid)
        iid = p["ideas"][0]["id"]
        with self.assertRaises(ide.DeskError):
            ide.idea_action(self.pid, iid, "reject", {})
        p = ide.idea_action(self.pid, iid, "reject", {"reason": "太标题党"})
        self.assertEqual(ide.load(self.pid)["ideas"][0]["reject_reason"], "太标题党")
        fb = ide._feedback(p)
        self.assertEqual(fb["rejected"][0]["reason"], "太标题党")

    def test_more_like_and_remix(self):
        p = ide.generate_ideas(self.pid)
        a, b = p["ideas"][0]["id"], p["ideas"][1]["id"]
        p = ide.more_like(self.pid, a)
        self.assertEqual(len(p["ideas"]), 13)
        self.assertTrue(ide._idea(p, a)["starred"])
        p = ide.remix(self.pid, a, b)
        self.assertTrue(p["ideas"][-1]["origin"].startswith("remix:"))

    def test_story_requires_pick(self):
        ide.generate_ideas(self.pid)
        with self.assertRaises(ide.DeskError):
            ide.generate_outline(self.pid)

    def test_full_flow_to_approved_script(self):
        p = ide.generate_ideas(self.pid)
        iid = p["ideas"][3]["id"]
        p = ide.idea_action(self.pid, iid, "edit", {"hook": "我改过的钩子"})
        p = ide.idea_action(self.pid, iid, "pick", {})
        self.assertEqual(p["step"], "story")
        p = ide.generate_outline(self.pid)
        v1 = p["story"]["active"]
        with self.assertRaises(ide.DeskError):
            ide.approve(self.pid)
        p = ide.regen_beat(self.pid, "turn")
        self.assertEqual(len(p["story"]["versions"]), 2)
        v2 = ide._active(p)
        self.assertEqual(v2["beats"]["hook"], next(v for v in p["story"]["versions"] if v["id"] == v1)["beats"]["hook"])
        p = ide.generate_script(self.pid)
        self.assertTrue(ide._active(p)["script"]["shots"])
        p = ide.approve(self.pid)
        script = json.loads(ide.script_path(self.pid).read_text(encoding="utf-8"))
        self.assertTrue(script["approved"])
        self.assertEqual(script["source"]["idea"]["hook"], "我改过的钩子")
        p = ide.edit_version(self.pid, {"beats": {"cta": "新的结尾"}})
        self.assertIsNone(p["story"]["approved"])

    def test_script_json_renders_through_loader(self):
        from desk.script import load_script

        p = ide.generate_ideas(self.pid)
        ide.idea_action(self.pid, p["ideas"][0]["id"], "pick", {})
        ide.generate_outline(self.pid)
        ide.generate_script(self.pid)
        ide.approve(self.pid)
        s = load_script(ide.script_path(self.pid))
        self.assertTrue(s.approved)
        self.assertGreaterEqual(len(s.shots), 4)


class PromptFiles(unittest.TestCase):
    def test_all_placeholders_filled(self):
        seen = {}
        orig = llm.chat_json
        llm.chat_json = lambda system, user: seen.setdefault("user", user) and {"ideas": []}
        try:
            llm.run_prompt("ideas", {"brief": {"topic": "x"}, "count": "10", "duration": "30",
                                     "starred": "无", "rejected": [{"hook": "h", "reason": "r"}], "existing": "无"})
        finally:
            llm.chat_json = orig
        self.assertNotIn("{{", seen["user"])
        self.assertIn("\"reason\": \"r\"", seen["user"])

    def test_provider_selection(self):
        env = {k: os.environ.pop(k, None) for k in ("DESK_LLM", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_BASE_URL")}
        try:
            self.assertEqual(llm.provider()["name"], "mock")
            os.environ["ANTHROPIC_API_KEY"] = "x"
            self.assertEqual(llm.provider()["name"], "anthropic")
            os.environ["OPENAI_API_KEY"] = "x"
            os.environ["OPENAI_BASE_URL"] = "https://api.deepseek.com/v1/"
            p = llm.provider()
            self.assertEqual((p["name"], p["base_url"]), ("openai", "https://api.deepseek.com/v1"))
        finally:
            for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_BASE_URL"):
                os.environ.pop(k, None)
            os.environ["DESK_LLM"] = "mock"

    def test_json_parsing_tolerates_fences(self):
        self.assertEqual(llm._parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(llm._parse_json('好的：{"a": 2} 完毕'), {"a": 2})


if __name__ == "__main__":
    unittest.main()
