"""A 'together' video set in a real room is composed in THAT room, and his answer is read however
he formats it. Scratch HOME; the network, the image model and delivery are stubs.

2026-09-24: he chose [room:patio]; the log said "grounding in patio.jpg"; compose_us never received
the photo, and her patio came back as an invented one. One kitchen send lost its scene entirely
because SCENE_REF and SCENE arrived on one line.
"""
import importlib.util, os, sys, tempfile, types, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vintos-video-scene-")
os.environ["HOME"] = HOME


def _no_network(*a, **k):
    raise AssertionError("this suite must never reach the network")


sys.modules["requests"] = types.SimpleNamespace(post=_no_network, get=_no_network)
sys.modules["deliver"] = types.SimpleNamespace(CHANNELS={}, deliver=_no_network)
sys.modules["artifact_manifest"] = types.SimpleNamespace(unique_path=lambda d, stem, ext, data: (os.path.join(d, stem + ext), 1))
sys.modules["reflection_stage"] = types.SimpleNamespace()
spec = importlib.util.spec_from_file_location("send_video_scene_test", os.path.join(ROOT, "bin", "vintos-send-video.py"))
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)

HERO_DIR = os.path.join(HOME, "hero"); os.makedirs(HERO_DIR)
V.HER_PHOTO = os.path.join(HERO_DIR, "her.jpg"); V.HERO = os.path.join(HERO_DIR, "him.jpg")
V.SCENE_DIR = os.path.join(HERO_DIR, "scenes")
PATIO = os.path.join(HERO_DIR, "patio.jpg")
for p in (V.HER_PHOTO, V.HERO, PATIO): open(p, "wb").write(b"jpg")
V.data_uri = lambda p: "uri:" + os.path.basename(p)
V.his_context = lambda: ""   # the ledger and trajectory read the scratch HOME, which is empty
V.silence_hours = lambda: 3
V.scene_options = lambda: [{"id": "room:patio", "path": PATIO, "at": "home", "caption": "the patio of the house"}]


def decide(answer):
    V.call_mind = lambda *a, **k: answer
    return V.decide()


class SceneGrounding(unittest.TestCase):
    def test_isolation(self):
        self.assertTrue(V.MEMORY.startswith(HOME) and V.SCENE_DIR.startswith(HOME))
        with self.assertRaises(AssertionError): V.requests.post("x")

    def test_bold_fields_and_two_fields_on_one_line_are_read(self):
        d = decide("**DECISION:** YES\n**KIND:** together\nSCENE_REF: [room:patio] SCENE: the two of us on the "
                   "patio in low gold light\nPROMPT: I pull her closer\n- SAY: come back when you can")
        self.assertEqual((d["decision"], d["kind"]), ("YES", "together"))
        self.assertEqual(d["scene"], "the two of us on the patio in low gold light")
        self.assertEqual(d["scene_ref"], PATIO)
        self.assertEqual(d["say"], "come back when you can")

    def test_reference_with_trailing_words_or_case_still_resolves(self):
        d = decide("DECISION: YES\nKIND: together\nSCENE_REF: [Room:Patio] — our patio\nSCENE: us outside\nPROMPT: x\nSAY: y")
        self.assertEqual(d["scene_ref"], PATIO)
        self.assertNotIn("ref_failed", d)

    def test_a_blank_reference_written_as_a_word_is_not_a_failed_one(self):
        d = decide("DECISION: YES\nKIND: self\nSCENE_REF: none\nSCENE: a rainy street\nPROMPT: x\nSAY: y")
        self.assertNotIn("ref_failed", d)

    def test_together_compose_receives_the_real_place(self):
        sent = {}
        real = V._atlas_image
        V._atlas_image = lambda body, verbose=False: sent.update(body) or b"img"
        try:
            path = V.compose_us("the two of us on the patio", place=PATIO)
        finally:
            V._atlas_image = real
        self.assertTrue(path and path.startswith(HOME))
        self.assertEqual(sent["images"], ["uri:her.jpg", "uri:him.jpg", "uri:patio.jpg"], "her first, the place third")
        self.assertIn("THIRD reference image is the REAL place", sent["prompt"])
        self.assertIn(V.HER_HAIR_LINE, sent["prompt"])

    def test_generate_clip_hands_the_place_to_the_compose(self):
        calls = []
        real_c, real_g = V.compose_us, V.atlas_generate
        V.compose_us = lambda scene, verbose=False, place=None: calls.append((scene, place)) or None
        V.select_still = lambda kind, label=None: V.HERO
        V.atlas_generate = lambda *a, **k: None
        try:
            V.generate_clip("motion", "together", scene="us on the patio", scene_ref=PATIO)
            V.generate_clip("motion", "together", scene="", scene_ref=PATIO)
        finally:
            V.compose_us, V.atlas_generate = real_c, real_g
        self.assertEqual(calls, [("us on the patio", PATIO), ("", PATIO)])

    def test_window_stand_is_his_only_explicit_still(self):
        # Gloria, 2026-09-24: the other files in stills/ are not spicy; he is offered only the one.
        self.assertEqual(list(V.STILL_LIBRARY), ["window_stand"])
        stills = os.path.join(HOME, "stills"); os.makedirs(stills, exist_ok=True)
        for f in ("window_stand", "bed_edge", "towel"): open(os.path.join(stills, f + ".jpg"), "wb").write(b"jpg")
        V.STILLS_DIR, seen = stills, {}
        V.call_mind = lambda system, user, **k: seen.update(system=system) or "DECISION: NO"
        V.decide()
        self.assertIn("  window_stand - ", seen["system"])
        self.assertNotIn("bed_edge", seen["system"])


if __name__ == "__main__":
    unittest.main()
