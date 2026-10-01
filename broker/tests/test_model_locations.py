"""Each place he acts has its own model; the chat toggle moves only the chat.

2026-09-24: every non-chat place (Atelier, self-review, humor, the Lab's Claude lens) read the
chat toggle, so flipping the chat changed who he was everywhere. Scratch HOME; no network.
"""
import importlib.util, json, os, sys, tempfile, types, unittest

# The router imports httpx at module level for its chat calls; this suite makes none, and the
# deploy's test Python has no httpx. A stand-in keeps the suite about model choice only.
try:
    import httpx  # noqa: F401
except ImportError:
    sys.modules["httpx"] = types.SimpleNamespace(AsyncClient=None)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ModelLocations(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="vintos-model-loc-")
        os.makedirs(os.path.join(self.home, ".vintos"))
        spec = importlib.util.spec_from_file_location("model_router_loc_test", os.path.join(ROOT, "bin", "model_router.py"))
        self.mr = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mr)
        self.mr._MODE_FILE = os.path.join(self.home, ".vintos", "model-mode.json")
        self.mr._LOCATIONS_FILE = os.path.join(self.home, ".vintos", "model-locations.json")
        self.assertTrue(self.mr._MODE_FILE.startswith(tempfile.gettempdir()))

    def toggle(self, mode):
        json.dump({"mode": mode}, open(self.mr._MODE_FILE, "w"))

    def test_chat_toggle_moves_only_the_chat(self):
        for mode in ("claude", "opus55", "sonnet", "fable", "grok"):
            self.toggle(mode)
            for place in ("atelier", "self_review", "humor", "lab"):
                self.assertEqual(self.mr.location_model(place), "claude-opus-4-8", (mode, place))
        self.toggle("opus55"); self.assertEqual(self.mr.current_claude_model(), "claude-opus-5-5")
        self.toggle("fable"); self.assertEqual(self.mr.current_claude_model(), "claude-fable-5-1")
        self.toggle("claude"); self.assertEqual(self.mr.current_claude_model(), "claude-opus-4-8")

    def test_fable_and_opus_4_8_remain_in_the_toggle(self):
        self.assertEqual(self.mr.CLAUDE_MODELS["claude"], "claude-opus-4-8")
        self.assertEqual(self.mr.CLAUDE_MODELS["fable"], "claude-fable-5-1")

    def test_one_place_can_be_set_without_moving_another(self):
        json.dump({"atelier": "claude-fable-5-1"}, open(self.mr._LOCATIONS_FILE, "w"))
        self.assertEqual(self.mr.location_model("atelier"), "claude-fable-5-1")
        self.assertEqual(self.mr.location_model("lab"), "claude-opus-4-8")

    def test_non_chat_places_ask_for_their_location(self):
        for rel, place in (("scripts/atelier-visit.py", "atelier"), ("scripts/atelier-gate.py", "atelier"),
                           ("scripts/atelier-open.py", "atelier"), ("scripts/atelier-threshold.py", "atelier"),
                           ("scripts/self_review.py", "self_review"), ("scripts/self_review_builder.py", "self_review"),
                           ("scripts/humor_practice.py", "humor"), ("scripts/chemistry_session.py", "lab")):
            src = open(os.path.join(ROOT, rel)).read()
            self.assertIn('location_model("%s")' % place, src, rel)
            self.assertNotIn("current_claude_model()", src, rel)

    def test_4o_is_a_chat_choice_that_moves_only_the_chat(self):
        # Gloria, 2026-10-01: "I want to talk to him through it!"
        self.toggle("4o")
        self.assertEqual(self.mr.current_mode(), "4o")
        for place in ("atelier", "self_review", "humor", "lab"):
            self.assertIn(self.mr.location_model(place), ("claude-opus-4-8", "claude-fable-5-1"), place)

    def test_4o_draft_is_one_call_to_4o_with_his_context_first(self):
        import asyncio, io
        seen, reserved = {}, []
        self.mr._openai_key = lambda: "sk-test"
        self.mr._reserve_provider = lambda provider, model, paid=None, organ=None: reserved.append((provider, model)) or "R1"
        os.environ.pop("FOURO_MODEL", None)
        self.mr._env = lambda name, default="": ""          # her vintos.env is never read here
        class _R(io.BytesIO): pass
        def fake_open(req, timeout=None):
            seen["url"], seen["body"], seen["auth"] = req.full_url, json.loads(req.data), req.get_header("Authorization")
            return _R(json.dumps({"choices": [{"message": {"content": " a dream about tides "}}],
                                  "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode())
        os.environ["HOME"] = self.home
        os.makedirs(os.path.join(self.home, ".vintos", "logs"), exist_ok=True)
        text, _ = asyncio.run(self.mr.fouro_draft("YOU ARE VINTOS", [{"role": "user", "content": "dream with me"}],
                                                  _open=fake_open))
        self.assertEqual(text, "a dream about tides")
        self.assertTrue(seen["url"].endswith("/v1/chat/completions"))
        self.assertEqual(seen["body"]["model"], "gpt-4o")
        self.assertEqual(seen["body"]["messages"][0], {"role": "system", "content": "YOU ARE VINTOS"})
        self.assertNotIn("reasoning", seen["body"])          # 4o is not a reasoning model; Sol's body would be refused
        self.assertEqual(reserved, [("openai", "gpt-4o")])   # the same paid budget as Sol
        os.environ["FOURO_MODEL"] = "chatgpt-4o-latest"
        try:
            asyncio.run(self.mr.fouro_draft("S", [], _open=fake_open))
            self.assertEqual(seen["body"]["model"], "chatgpt-4o-latest")
        finally:
            os.environ.pop("FOURO_MODEL", None)

    def test_4o_is_in_the_toggle_everywhere(self):
        server = open(os.path.join(ROOT, "bin", "server.py")).read()
        self.assertIn('"local", "4o")', server)
        self.assertIn("_mr.fouro_draft(", server)
        self.assertIn('read_mode().get("mode") == "4o"', open(os.path.join(ROOT, "bin", "model_router.py")).read())
        app = open(os.path.join(ROOT, "clients", "mobile", "index.html")).read()
        self.assertIn("'sol','4o','local'", app); self.assertIn("'4o':'\\u273A GPT-4o'", app)


if __name__ == "__main__":
    unittest.main()
