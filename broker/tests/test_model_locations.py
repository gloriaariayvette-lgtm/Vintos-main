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


if __name__ == "__main__":
    unittest.main()
