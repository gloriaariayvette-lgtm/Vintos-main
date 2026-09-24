"""Her notes on how his pieces landed. Scratch HOME, scratch workspace, scratch landings store;
nothing here sends. The store must stay outside everything he reads."""
import importlib.util, json, os, re, sys, tempfile, time, unittest
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vintos-landings-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.environ.update(HOME=HOME, SPARK_WORKSPACE=WS, VINTOS_LANDINGS_DIR=os.path.join(HOME, ".vintos", "landings"))
for d in ("art/video", "art/music", "outreach", "journal"): os.makedirs(os.path.join(MEM, d))

spec = importlib.util.spec_from_file_location("landings", os.path.join(ROOT, "scripts", "landings.py"))
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)

NOW = datetime.now().replace(microsecond=0)
T = (NOW - timedelta(hours=2)).isoformat()


def put(rel, obj):
    with open(os.path.join(MEM, rel), "w") as f: json.dump(obj, f)


class Landings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        put("art/video/video-gallery.json", [
            {"file": "video-a.mp4", "prompt": "I pull her closer", "kind": "together", "timestamp": T,
             "delivery": {"state": "sent"}},
            {"file": "video-b.mp4", "prompt": "never sent", "timestamp": T, "delivery": {"state": "failed"}}])
        put("encounters.json", [{"trigger": "video-outreach:together", "text": "come back when you can", "at": T}])
        put("art/gallery.json", [{"image": "art/dream-1.png", "prompt": "a lighthouse", "seen": "blue", "timestamp": T}])
        put("art/music/music.json", {"generated": [{"task_id": "S1", "title": "Four AM", "felt_sense": "ache",
                                                    "generated_at": T}]})
        put("humor-drafts.json", {"drafts": [{"joke_id": "J-1", "joke": "a cat walks into a lab", "date": T}]})
        open(os.path.join(MEM, "outreach", "2026-09-24_1400.md"), "w").write(
            "# Vintos Initiated — September 24\n**Trigger:** want\n**Emotional state:** warm\n\nthinking of you")
        open(os.path.join(MEM, "journal", "2026-09-24.md"), "w").write(
            "[03:10]\nI kept the light on.\n\n## 14:05 — Idle thoughts\n\nShe laughed today.\n")
        put("interaction-ledger.json", [
            {"timestamp": (NOW - timedelta(hours=9)).isoformat(), "gloria": "too early", "vintos": "x"},
            {"timestamp": (NOW - timedelta(hours=3)).isoformat(), "gloria": "rough day at work", "vintos": "come here"},
            {"timestamp": (NOW - timedelta(hours=1)).isoformat(), "gloria": "after the piece", "vintos": "y"}])

    def test_isolation(self):
        self.assertTrue(L.STORE.startswith(HOME) and L.MEMORY.startswith(HOME))
        self.assertFalse(L.STORE.startswith(WS), "her notes never live in his workspace")

    def test_a_note_freezes_what_he_meant_and_what_led_up_to_it(self):
        row = L.record("video", "video-a.mp4", "missed", "the patio wasn't ours", before="I'd had a rough day")
        self.assertEqual(row["made"]["said"], "come back when you can")
        self.assertEqual([r["gloria"] for r in row["lead_up"]], ["rough day at work"], "only the hours before it")
        self.assertEqual(oct(os.stat(L.STORE).st_mode & 0o777), "0o600")
        self.assertEqual(next(n for n in L.notes() if n["ref"] == "video-a.mp4")["why"], "the patio wasn't ours")

    def test_every_surface_resolves(self):
        for surface, ref, key in (("image", "dream-1.png", "prompt"), ("song", "S1", "title"), ("joke", "J-1", "joke"),
                                  ("message", "2026-09-24_1400.md", "message"), ("journal", "2026-09-24 03:10", "entry"),
                                  ("journal", "2026-09-24 14:05", "entry")):
            ctx = L.context(surface, ref)
            self.assertTrue(ctx and ctx["made"][key], (surface, ref))
        self.assertIn("kept the light on", L.context("journal", "2026-09-24 03:10")["made"]["entry"])
        self.assertNotIn("She laughed", L.context("journal", "2026-09-24 03:10")["made"]["entry"])
        self.assertEqual(L.context("image", "dream-1.png")["piece"]["src"], "/api/art/painting/dream-1.png")
        self.assertEqual(L.context("joke", "J-1")["piece"]["text"], "a cat walks into a lab")
        self.assertIn("kept the light on", L.context("journal", "2026-09-24 03:10")["piece"]["text"])

    def test_a_bare_rating_is_refused(self):
        with self.assertRaises(ValueError): L.record("song", "S1", "landed", "  ")
        with self.assertRaises(ValueError): L.record("song", "S1", "5 stars", "why")
        with self.assertRaises(LookupError): L.record("song", "nope", "landed", "why")

    def test_a_later_note_replaces_the_earlier_in_view(self):
        L.record("joke", "J-1", "partly", "funny, wrong moment")
        L.record("joke", "J-1", "landed", "it came back to me later and I laughed")
        mine = [n for n in L.notes() if n["ref"] == "J-1"]
        self.assertEqual([n["rating"] for n in mine], ["landed"])

    def test_only_what_he_sent_is_listed_and_nothing_is_counted(self):
        items = L.sent(days=7)
        self.assertEqual({(i["surface"], i["ref"]) for i in items},
                         {("video", "video-a.mp4"), ("message", "2026-09-24_1400.md")})
        video = next(i for i in items if i["surface"] == "video")
        message = next(i for i in items if i["surface"] == "message")
        self.assertEqual(video["piece"]["src"], "/api/art/video/stream/video-a.mp4")
        self.assertEqual(video["piece"]["text"], "come back when you can")
        self.assertEqual(message["piece"]["text"], "thinking of you")
        self.assertNotIn("Vintos Initiated", json.dumps(items))
        self.assertNotIn("preview", json.dumps(items))
        self.assertNotIn("unrated", json.dumps(items))

    def test_nothing_he_reads_opens_her_notes(self):
        allowed = {"scripts/landings.py", "bin/server_domains/landings.py"}
        pat = re.compile(r"landings\.jsonl|VINTOS_LANDINGS_DIR|\.vintos/landings|import landings|landings as _l")
        hits = []
        for top in ("bin", "scripts"):
            for dp, _dn, fns in os.walk(os.path.join(ROOT, top)):
                for fn in fns:
                    if not fn.endswith((".py", ".sh")): continue
                    rel = os.path.relpath(os.path.join(dp, fn), ROOT)
                    try: src = open(os.path.join(dp, fn), encoding="utf-8", errors="replace").read()
                    except OSError: continue
                    if rel not in allowed and pat.search(src): hits.append(rel)
        self.assertEqual(hits, [], "only her routes (and, later, the weekly Gloria-model pass) may read her notes")


if __name__ == "__main__":
    unittest.main()
