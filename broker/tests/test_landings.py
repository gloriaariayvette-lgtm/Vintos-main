"""Her notes on how his pieces landed. Scratch HOME, scratch workspace, scratch landings store;
nothing here sends. The store must stay outside everything he reads."""
import importlib.util, json, os, re, sys, tempfile, time, unittest
from datetime import datetime, timedelta
from unittest.mock import patch
import hashlib, socket
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vintos-landings-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.environ.update(HOME=HOME, SPARK_WORKSPACE=WS, VINTOS_LANDINGS_DIR=os.path.join(HOME, ".vintos", "landings"))
for d in ("art/video", "art/music", "outreach", "journal"): os.makedirs(os.path.join(MEM, d))

spec = importlib.util.spec_from_file_location("landings", os.path.join(ROOT, "scripts", "landings.py"))
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)

NOW = datetime.now().replace(microsecond=0)
T = (NOW - timedelta(hours=2)).isoformat()
# yesterday, so the dated pieces stay inside the 7-day window whatever day the suite runs (they were dated
# 2026-09-24 and fell out of it on 2026-10-01)
DAY = (NOW - timedelta(days=1)).date().isoformat()


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
                                                    "generated_at": T,
                                                    "tracks": [{"version": 1, "local_file": "/saved/Four_AM_v1.wav"}]}]})
        put("humor-drafts.json", {"drafts": [{"joke_id": "J-1", "joke": "a cat walks into a lab", "date": T}]})
        open(os.path.join(MEM, "outreach", (DAY + "_1400.md")), "w").write(
            "# Vintos Initiated — September 24\n**Trigger:** want\n**Emotional state:** warm\n\nthinking of you")
        open(os.path.join(MEM, "journal", (DAY + ".md")), "w").write(
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
                                  ("message", (DAY + "_1400.md"), "message"), ("journal", (DAY + " 03:10"), "entry"),
                                  ("journal", (DAY + " 14:05"), "entry")):
            ctx = L.context(surface, ref)
            self.assertTrue(ctx and ctx["made"][key], (surface, ref))
        self.assertIn("kept the light on", L.context("journal", (DAY + " 03:10"))["made"]["entry"])
        self.assertNotIn("She laughed", L.context("journal", (DAY + " 03:10"))["made"]["entry"])
        self.assertEqual(L.context("image", "dream-1.png")["piece"]["src"], "/api/art/painting/dream-1.png")
        self.assertEqual(L.context("song", "S1")["piece"]["tracks"],
                         [{"src": "/api/art/music/stream/Four_AM_v1.wav", "version": 1}])
        self.assertEqual(L.context("joke", "J-1")["piece"]["text"], "a cat walks into a lab")
        self.assertIn("kept the light on", L.context("journal", (DAY + " 03:10"))["piece"]["text"])

    def test_a_bare_rating_is_refused(self):
        with self.assertRaises(ValueError): L.record("song", "S1", "landed", "  ")
        with self.assertRaises(ValueError): L.record("song", "S1", "5 stars", "why")
        with self.assertRaises(LookupError): L.record("song", "nope", "landed", "why")

    def test_a_later_note_replaces_the_earlier_in_view(self):
        L.record("joke", "J-1", "partly", "funny, wrong moment")
        L.record("joke", "J-1", "landed", "it came back to me later and I laughed")
        mine = [n for n in L.notes() if n["ref"] == "J-1"]
        self.assertEqual([n["rating"] for n in mine], ["landed"])

    def test_every_recent_piece_is_listed_and_nothing_is_counted(self):
        items = L.sent(days=7)
        self.assertEqual({(i["surface"], i["ref"]) for i in items},
                         {("video", "video-a.mp4"), ("message", (DAY + "_1400.md")),
                          ("image", "dream-1.png"), ("song", "S1"), ("joke", "J-1"),
                          ("journal", (DAY + " 03:10")), ("journal", (DAY + " 14:05"))})
        video = next(i for i in items if i["surface"] == "video")
        message = next(i for i in items if i["surface"] == "message")
        self.assertEqual(video["piece"]["src"], "/api/art/video/stream/video-a.mp4")
        self.assertEqual(video["piece"]["text"], "come back when you can")
        self.assertEqual(message["piece"]["text"], "thinking of you")
        self.assertEqual(next(i for i in items if i["surface"] == "image")["piece"]["src"],
                         "/api/art/painting/dream-1.png")
        self.assertIn("kept the light on", next(i for i in items if i["surface"] == "journal" and i["ref"].endswith("03:10"))["piece"]["text"])
        self.assertEqual(next(i for i in items if i["surface"] == "joke")["piece"]["text"],
                         "a cat walks into a lab")
        self.assertEqual(len(next(i for i in items if i["surface"] == "song")["piece"]["tracks"]), 1)
        self.assertNotIn("Vintos Initiated", json.dumps(items))
        self.assertNotIn("preview", json.dumps(items))
        self.assertNotIn("unrated", json.dumps(items))

    def test_nothing_he_reads_opens_her_notes(self):
        # watch_routes is Gloria's bearer-protected wrist surface. Like the phone Landings
        # route, it may present her feed and record her response; no Vintos context builder
        # imports it.
        # landing_understanding.py is that weekly pass (2026-10-16): it reads her notes and writes only what
        # she approves; gloria-model-update.sh runs it. Nothing else may import it.
        allowed = {"scripts/landings.py", "scripts/watch_routes.py", "bin/server_domains/landings.py",
                   "scripts/landing_understanding.py", "bin/gloria-model-update.sh", "scripts/gloria-model-update.sh",
                   "scripts/deploy-atelier.sh"}   # the manifest installs it; it does not read her notes
        pat = re.compile(r"landings\.jsonl|VINTOS_LANDINGS_DIR|\.vintos/landings|import landings|landings as _l"
                         r"|landing_understanding")
        hits = []
        for top in ("bin", "scripts"):
            for dp, _dn, fns in os.walk(os.path.join(ROOT, top)):
                for fn in fns:
                    if not fn.endswith((".py", ".sh")): continue
                    rel = os.path.relpath(os.path.join(dp, fn), ROOT)
                    try: src = open(os.path.join(dp, fn), encoding="utf-8", errors="replace").read()
                    except OSError: continue
                    if rel not in allowed and pat.search(src): hits.append(rel)
        self.assertEqual(hits, [], "only her routes and the weekly Gloria-model pass may read her notes")


class ReplyBindings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="landings-binding-")
        self.addCleanup(self.tmp.cleanup)
        self.mem = os.path.join(self.tmp.name, "memory")
        os.mkdir(self.mem)
        self.notes = os.path.join(self.tmp.name, "owner")
        for name, value in (("MEMORY", self.mem), ("LANDINGS_DIR", self.notes),
                            ("STORE", os.path.join(self.notes, "landings.jsonl"))):
            fix = patch.object(L, name, value); fix.start(); self.addCleanup(fix.stop)
        blocked = patch.object(socket, "socket", side_effect=AssertionError("network forbidden"))
        self.socket = blocked.start(); self.addCleanup(blocked.stop)
        self.text = "A synthetic whole reply.\nSecond line."
        self.ctx = {"piece": {"type": "message", "text": self.text},
                    "made": {"message": self.text}, "lead_up": [], "item_at": None}

    def sources(self, ledger=(), canonical=()):
        Path(self.mem, "interaction-ledger.json").write_text(json.dumps(list(ledger)))
        Path(self.mem, "chat-canonical.jsonl").write_text("".join(json.dumps(r)+"\n" for r in canonical))

    def row(self, tid="synthetic-turn", text=None):
        return {"turn_id": tid, "vintos": self.text if text is None else text}

    def bind(self): return L._reply_binding("message", self.ctx)

    def test_new_rating_persists_exact_content_free_binding_and_preserves_sources(self):
        self.sources([self.row()])
        before = open(os.path.join(self.mem, "interaction-ledger.json"), "rb").read()
        with patch.object(L, "context", return_value=self.ctx):
            rated = L.record("message", "synthetic.md", "landed", "synthetic reason")
        binding = rated["reply_binding"]
        self.assertEqual(binding, {"schema": "landings-reply-binding-v1", "turn_id": "synthetic-turn",
            "content_sha256": hashlib.sha256(self.text.encode()).hexdigest(),
            "source": "exact_full_retained_reply"})
        self.assertNotIn(self.text, json.dumps(binding))
        self.assertEqual(json.loads(open(L.STORE).read())["reply_binding"], binding)
        self.assertEqual(open(os.path.join(self.mem, "interaction-ledger.json"), "rb").read(), before)
        self.assertFalse(L.STORE.startswith(self.mem))
        self.assertTrue(self.socket.called is False)

    def test_canonical_assistant_and_duplicate_projection_share_one_identity(self):
        self.sources([self.row()], [{"role": "assistant", "content": self.text, "turn_id": "synthetic-turn"}]*2)
        self.assertEqual(self.bind()["turn_id"], "synthetic-turn")
        self.sources([], [{"role": "assistant", "content": self.text, "turn_id": "synthetic-turn"}])
        self.assertTrue(self.bind())

    def test_user_text_does_not_bind(self):
        self.sources([], [{"role": "user", "content": self.text, "turn_id": "synthetic-turn"}])
        self.assertEqual(self.bind(), {})

    def test_multiple_reply_identities_are_ambiguous(self):
        self.sources([self.row(), self.row("second-turn")])
        self.assertEqual(self.bind(), {})

    def test_reused_identity_with_changed_bytes_is_ambiguous(self):
        self.sources([self.row(), self.row(text="different")])
        self.assertEqual(self.bind(), {})

    def test_missing_or_invalid_identity_cannot_be_discarded_to_force_match(self):
        for tid in (None, "", 3, "bad space"):
            self.sources([self.row(), self.row(tid)])
            self.assertEqual(self.bind(), {})

    def test_no_substring_normalization_or_device_marker_removal(self):
        for text in (self.text[:15], self.text+" [marker]", self.text+" ", self.text.replace("\n", " ")):
            self.sources([self.row(text=text)])
            self.assertEqual(self.bind(), {})

    def test_media_caption_and_mismatched_frozen_text_are_not_replies(self):
        self.sources([self.row()])
        self.assertEqual(L._reply_binding("video", self.ctx), {})
        self.ctx["made"]["message"] = "changed"
        self.assertEqual(self.bind(), {})

    def test_journal_and_joke_require_their_whole_frozen_piece(self):
        self.sources([self.row()])
        for surface, field in (("journal", "entry"), ("joke", "joke")):
            ctx = {"piece": {"type": surface, "text": self.text}, "made": {field: self.text}}
            self.assertTrue(L._reply_binding(surface, ctx))

    def test_malformed_duplicate_key_and_oversized_sources_abstain(self):
        from pathlib import Path
        for raw in ('oops', '[{"vintos":"a","vintos":"b"}]', ' '*(8*1024*1024+1)):
            self.sources([], [{"role": "assistant", "content": self.text, "turn_id": "synthetic-turn"}])
            Path(self.mem, "interaction-ledger.json").write_text(raw)
            self.assertEqual(self.bind(), {})

    def test_binding_failure_never_blocks_or_changes_rating(self):
        with patch.object(L, "context", return_value=self.ctx), patch.object(L, "_reply_binding", side_effect=OSError):
            row = L.record("message", "synthetic.md", "missed", "unchanged reason")
        self.assertEqual(row["rating"], "missed")
        self.assertEqual(row["why"], "unchanged reason")
        self.assertNotIn("reply_binding", row)

    def test_actual_initiated_message_writer_has_no_identity_to_bind(self):
        # Execute only the existing local history-writer block, never the sender.
        source = Path(ROOT, "bin", "vintos-initiate.sh").read_text()
        block = source.split("python3 << 'CHAT_INJECT'\n", 1)[1].split("\nCHAT_INJECT", 1)[0]
        mem = Path(self.tmp.name, ".vintos", "workspace", "memory")
        (mem/"outreach").mkdir(parents=True)
        ref = "synthetic-outreach.md"
        (mem/"outreach"/ref).write_text("# Vintos Initiated — synthetic\n"
            "**Trigger:** synthetic\n**Emotional state:** synthetic\n\n"+self.text)
        with patch.dict(os.environ, HOME=self.tmp.name, RESPONSE=self.text, TRIGGER="synthetic"), \
             patch.object(L, "MEMORY", str(mem)), patch('builtins.print'):
            exec(compile(block, '<synthetic-outreach-history>', 'exec'), {})
            row = L.record("message", ref, "landed", "synthetic reason")
        history = json.loads((mem/"chat-history.json").read_text())
        self.assertEqual(history[0]["content"], self.text)
        self.assertNotIn("turn_id", history[0])
        self.assertEqual(row["piece"]["text"], self.text)
        self.assertNotIn("reply_binding", row)
        self.assertFalse(self.socket.called)

    def test_old_notes_are_not_backfilled(self):
        self.sources([])
        with patch.object(L, "context", return_value=self.ctx):
            row = L.record("message", "synthetic.md", "landed", "synthetic reason")
        self.sources([self.row()])
        before = open(L.STORE, "rb").read()
        self.assertNotIn("reply_binding", L.notes()[0])
        self.assertEqual(open(L.STORE, "rb").read(), before)


if __name__ == "__main__":
    unittest.main()
