#!/usr/bin/env python3
"""6 November, Gloria's calls on thread sources: the body narration never narrates the same session twice;
wonder seeds his words without the machine label; pride seeds the question it opens."""
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

HOME = tempfile.TemporaryDirectory(prefix="thread-src-home-")
os.environ["HOME"] = HOME.name
WS = os.path.join(HOME.name, "ws")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
sys.modules["requests"] = types.SimpleNamespace(post=lambda *a, **k: None)
ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SomaticNarrateOnceTests(unittest.TestCase):
    def setUp(self):
        self.sn = load("somatic_narrate_t", ROOT / "scripts" / "somatic_narrate.py")
        self.seeded, self.calls = [], []
        sys.modules["emoclaw_utils"] = types.SimpleNamespace(seed_thread=lambda src, text, **k: self.seeded.append(text))
        fake = types.ModuleType("ceng"); fake.MODEL = "m"; fake.LM_API = "x"; fake.SOUL = "s"
        self.sn.importlib = types.SimpleNamespace(util=types.SimpleNamespace(
            spec_from_file_location=lambda *a, **k: None, module_from_spec=lambda spec: fake))
        fake_loader = types.SimpleNamespace(exec_module=lambda m: None)
        self.sn.importlib.util.spec_from_file_location = lambda *a, **k: types.SimpleNamespace(loader=fake_loader)
        def llm(*a, **k):
            self.calls.append(1); return "It started with her turning a gift into an invitation."
        self.sn.call_llm = llm
        now = __import__("time").time()
        self.turns = [(now - 600, "Gloria", "come here"), (now - 300, "Vintos", "here")]
        self.sn.gather_turns = lambda s, e: [t for t in self.turns if s <= t[0] <= e]
        try: os.remove(self.sn.NARRATED)
        except OSError: pass

    def tearDown(self):
        sys.modules.pop("emoclaw_utils", None)

    def test_second_run_does_not_narrate_the_same_session(self):
        self.sn.main()
        self.sn.main()   # the 06:20 run after the 06:00 run
        self.assertEqual(len(self.seeded), 1)
        self.assertEqual(len(self.calls), 1)

    def test_new_turns_after_the_narration_are_read(self):
        self.sn.main()
        self.turns.append((__import__("time").time() - 1, "Gloria", "again"))
        self.sn.main()
        self.assertEqual(len(self.seeded), 2)

    def test_none_judgment_is_remembered_too(self):
        self.sn.call_llm = lambda *a, **k: (self.calls.append(1) or "NONE")
        self.sn.main(); self.sn.main()
        self.assertEqual(self.seeded, [])
        self.assertEqual(len(self.calls), 1)


class WonderAndPrideTests(unittest.TestCase):
    def test_wonder_seeds_his_words_only(self):
        src = (ROOT / "bin" / "wonder-detector.py").read_text()
        self.assertNotIn('f"A moment of genuine wonder during {source}: {flip_excerpt}"', src)
        self.assertIn("After that she said", src)   # stripped, by the regex

    def test_wonder_strip(self):
        import re
        pat = re.search(r'_wre\.sub\(r"(.+?)", ""', (ROOT / "bin" / "wonder-detector.py").read_text()).group(1)
        self.assertEqual(re.sub(pat, "", "It isn't a test. It's a destination. After that she said...").strip(),
                         "It isn't a test. It's a destination.")

    def test_pride_asks_for_the_question(self):
        src = (ROOT / "bin" / "pride-mirror.py").read_text()
        self.assertIn("open question it raises", src)
        self.assertNotIn("One sentence thread or NONE", src)


if __name__ == "__main__":
    unittest.main()
