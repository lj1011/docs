import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DESK_LLM"] = "mock"
os.environ["DESK_DATA"] = tempfile.mkdtemp()

from desk import guidelines as G  # noqa: E402
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
        self.assertTrue(script["director_statement"]["intent"])
        self.assertTrue(script["variants"][0]["falsify"])
        self.assertEqual(script["guidelines"]["version"], "v0.3.1")
        p = ide.edit_version(self.pid, {"beats": {"cta": "新的结尾"}})
        self.assertIsNone(p["story"]["approved"])

    def _scripted(self):
        p = ide.generate_ideas(self.pid)
        ide.idea_action(self.pid, p["ideas"][0]["id"], "pick", {})
        ide.generate_outline(self.pid)
        return ide.generate_script(self.pid)

    def test_ideas_carry_skeleton_anchor_cards(self):
        p = ide.generate_ideas(self.pid)
        for i in p["ideas"]:
            self.assertIsNotNone(G.skeleton(i["skeleton"]), i["skeleton"])
            self.assertTrue(i["visual_anchor"])
            self.assertTrue(all(c.startswith("#") for c in i["cards"]))
        self.assertEqual(p["guidelines"]["version"], "v0.3.1")

    def test_approve_requires_director_statement(self):
        self._scripted()
        ide.edit_version(self.pid, {"director": {"intent": "", "anchor": "x"}})
        with self.assertRaisesRegex(ide.DeskError, "导演阐述"):
            ide.approve(self.pid)

    def test_approve_requires_single_variable_variants(self):
        self._scripted()
        ide.edit_version(self.pid, {"variants": []})
        with self.assertRaisesRegex(ide.DeskError, "变体"):
            ide.approve(self.pid)
        ide.edit_version(self.pid, {"variants": [{"variable": "停格、钩子位置", "change": "a→b", "hypothesis": "h", "falsify": "f"}]})
        with self.assertRaisesRegex(ide.DeskError, "不止一个变量"):
            ide.approve(self.pid)
        ide.edit_version(self.pid, {"variants": [{"variable": "停格有无", "change": "有→无", "hypothesis": "h", "falsify": "f"}]})
        self.assertTrue(ide.approve(self.pid)["story"]["approved"])

    def test_approve_requires_first_person_director(self):
        self._scripted()
        ide.edit_version(self.pid, {"director": {"intent": "让观众相信早起不难", "anchor": "我选闹钟",
                                                 "camera_light_rhythm": "我用冷光", "hypothesis": "我赌停格"}})
        with self.assertRaisesRegex(ide.DeskError, "第一人称"):
            ide.approve(self.pid)

    def test_brief_project_type(self):
        self.assertEqual(self.p["brief"]["project_type"], "original")
        self.assertEqual(self.p["brief"]["brand"], "")
        b = ide.create_project({"topic": "t", "brand": "某品牌"})["brief"]
        self.assertEqual((b["project_type"], b["brand"]), ("brand", "某品牌"))
        b = ide.create_project({"topic": "t", "project_type": "brand"})["brief"]
        self.assertEqual(b["brand"], "待补")

    def test_variant_metric_defaults_to_keven_judgment(self):
        self._scripted()
        p = ide.edit_version(self.pid, {"variants": [{"variable": "停格有无", "change": "有→无", "hypothesis": "h", "falsify": "f"}]})
        self.assertEqual(ide._active(p)["variants"][0]["metric"], G.DEFAULT_METRIC)

    def _dark(self, pid):
        ide.edit_version(pid, {"beats": {"turn": "一场惊悚的打斗"}})

    def test_brand_film_vetoes_dark_tone(self):
        pid = ide.create_project({**BRIEF, "brand": "某品牌"})["id"]
        p = ide.generate_ideas(pid)
        ide.idea_action(pid, p["ideas"][0]["id"], "pick", {})
        ide.generate_outline(pid)
        ide.generate_script(pid)
        self._dark(pid)
        with self.assertRaisesRegex(ide.DeskError, "品牌片"):
            ide.approve(pid)

    def test_original_story_allows_dark_but_not_blade_closeup(self):
        self._scripted()
        self._dark(self.pid)
        self.assertTrue(ide.approve(self.pid)["story"]["approved"])
        ide.edit_version(self.pid, {"beats": {"payoff": "刀刃抵喉的特写"}})
        with self.assertRaisesRegex(ide.DeskError, "A2"):
            ide.approve(self.pid)

    def test_brand_film_mock_flow_passes(self):
        pid = ide.create_project({**BRIEF, "brand": "某品牌"})["id"]
        p = ide.generate_ideas(pid)
        ide.idea_action(pid, p["ideas"][0]["id"], "pick", {})
        ide.generate_outline(pid)
        ide.generate_script(pid)
        self.assertTrue(ide.approve(pid)["story"]["approved"])
        script = json.loads(ide.script_path(pid).read_text(encoding="utf-8"))
        self.assertEqual((script["project_type"], script["brand"]), ("brand", "某品牌"))

    def test_scores_against_pass_lines(self):
        p = self._scripted()
        v = ide._active(p)
        self.assertFalse(ide.score_summary(v)["passed"])
        scores = {q["id"]: 2 for q in G.load()["questions"]}
        p = ide.edit_version(self.pid, {"scores": {**scores, "X9": 2, "N1": 7}})
        v = ide._active(p)
        self.assertNotIn("X9", v["scores"])
        self.assertEqual(v["scores"]["N1"], 2)
        self.assertTrue(ide.score_summary(v)["passed"])

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


class Guidelines(unittest.TestCase):
    def setUp(self):
        self.g = G.load()
        self.text = self.g["text"]

    def test_file_parsed(self):
        self.assertTrue(self.g["exists"])
        self.assertEqual(self.g["version"], "v0.3.1")
        self.assertGreaterEqual(len(self.g["skeletons"]), 10)
        self.assertEqual({q["dim"] for q in self.g["questions"]}, {"narrative", "visual"})
        self.assertEqual(self.g["thresholds"]["total"], [16, 26])

    def test_required_sections_present(self):
        for title in ["零、", "一、好点子的判断标准", "二、故事骨架库", "三、视觉手法库", "四、方法论", "五、反模式", "六、人机配合方式", "七、Keven 拍板记录与开放问题", "八、灵感信号储备"]:
            self.assertIn("## " + title, self.text)

    def test_every_skeleton_and_commonality_cites_cards(self):
        import re
        for sk in self.g["skeletons"]:
            self.assertTrue(sk["cards"], sk["id"])
            self.assertTrue(all(1 <= int(c) <= 25 for c in sk["cards"]))
        rows = [l for l in self.g["sections"]["零"].splitlines() if re.match(r"^\| C\d+", l)]
        self.assertGreaterEqual(len(rows), 10)
        for r in rows:
            self.assertTrue(re.search(r"#\d\d", r), r)
        cited = set(re.findall(r"#(\d\d)", self.g["sections"]["零"]))
        self.assertEqual(cited, {f"{i:02d}" for i in range(1, 26)})

    def test_keven_decisions_recorded(self):
        import re
        sec = self.g["sections"]["七"]
        self.assertIn("### 7.1 已由 Keven 拍板（2026-10-19）", sec)
        self.assertIn("### 7.2", sec)
        decided = sec.split("### 7.2")[0]
        self.assertEqual(len(re.findall(r"^\d+\. ", decided, re.M)), 8)
        self.assertIn("| v0.2 | 2026-10-19", self.g["sections"]["六"])
        self.assertEqual(self.g["thresholds"]["narrative"], [7, 12])
        self.assertEqual(self.g["thresholds"]["visual"], [8, 14])

    def test_v03_cards_and_signals_absorbed(self):
        s18, s19 = G.skeleton("S18"), G.skeleton("S19")
        self.assertIn("25", s18["cards"])
        self.assertIn("0.5–2.5 秒", s18["mechanism"])
        self.assertEqual(s19["cards"], ["24"])
        self.assertIn("### 3.9 多镜 AI 一致性", self.g["sections"]["三"])
        self.assertIn("午夜样板间", self.g["sections"]["五"])
        self.assertIn("| v0.3 | 2026-10-20", self.g["sections"]["六"])
        sig = G.digest("ideas")
        self.assertIn("RÆBURN", sig)
        self.assertIn("Taali Twirlz", sig)
        self.assertNotIn("**", sig.split("【灵感信号")[1])

    def test_digests_injected(self):
        self.assertIn("S07", G.digest("ideas"))
        self.assertIn("一票否决", G.digest("ideas"))
        self.assertIn("戏剧节拍" if False else "→", G.digest("outline"))
        script = G.digest("script")
        self.assertIn("【导演阐述】", script)
        self.assertIn("视觉手法库", script)
        self.assertIn("单变量", script)
        self.assertIn("第一人称", script)
        self.assertIn("品牌片：禁止暗黑", G.digest("ideas", "brand"))
        self.assertIn("自创故事（无品牌）：可以用暗黑", G.digest("ideas", "original"))
        self.assertIn(G.DEFAULT_METRIC, G.digest("outline"))

    def test_prompts_receive_guidelines(self):
        seen = []
        orig_provider, orig_chat = llm.provider, llm.chat_json
        llm.provider = lambda: {"name": "openai", "model": "fake", "base_url": "x"}

        def fake(system, user):
            seen.append(user)
            if "故事节拍大纲" in user:
                return {"skeleton": "S07", "beats": {"hook": "h", "turn": "t", "payoff": "p", "cta": "c"}}
            if "镜头表" in user:
                return {"title": "t", "shots": [{"beat": "hook", "vo": "一句", "screen_text": "", "visual": ""}],
                        "director": {"intent": "我想要i", "anchor": "我选a", "camera_light_rhythm": "我用c", "hypothesis": "我赌h"},
                        "variants": [{"variable": "停格有无", "change": "有→无", "hypothesis": "h", "falsify": "f"}]}
            return {"ideas": [{"hook": "钩子", "angle": "a", "format": "口播", "skeleton": "s07", "visual_anchor": "红鸟", "why": "w", "cards": ["8", "#01"]}]}
        llm.chat_json = fake
        try:
            p = ide.create_project(BRIEF)
            p = ide.generate_ideas(p["id"], 1)
            idea = p["ideas"][0]
            self.assertEqual((idea["skeleton"], idea["cards"]), ("S07", ["#08", "#01"]))
            ide.idea_action(p["id"], idea["id"], "pick", {})
            ide.generate_outline(p["id"])
            p = ide.generate_script(p["id"])
            v = ide._active(p)
            self.assertEqual(v["skeleton"], "S07")
            self.assertEqual(v["director"]["intent"], "我想要i")
            self.assertTrue(ide.approve(p["id"])["story"]["approved"])
        finally:
            llm.provider, llm.chat_json = orig_provider, orig_chat
        self.assertEqual(len(seen), 3)
        self.assertIn("故事骨架库", seen[0])
        self.assertIn("S07 诱饵", seen[1])
        self.assertIn("【导演阐述】", seen[2])
        self.assertTrue(all("{{" not in u for u in seen))


class PromptFiles(unittest.TestCase):
    def test_all_placeholders_filled(self):
        seen = {}
        orig = llm.chat_json
        llm.chat_json = lambda system, user: seen.setdefault("user", user) and {"ideas": []}
        try:
            llm.run_prompt("ideas", {"brief": {"topic": "x"}, "count": "10", "duration": "30", "guidelines": "G",
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
