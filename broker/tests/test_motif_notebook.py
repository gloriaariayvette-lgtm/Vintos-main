#!/usr/bin/env python3
"""His motif notebook (proposal 02, 25 October): a typed phrase of actual notes, written as MIDI, checked by the
existing verifier, rendered by the existing CPU piano tone, kept inside the current Atelier project; and a later
variation of it with his chosen operation and the exact note diff, the parent never rewritten.

Scratch HOME and workspace; a scratch broker room (the real broker code, its ROOT repointed); every socket is
refused; the only "post" is a function that hands the body to the scratch broker's own routes after its own
authorization matrix. Nothing here can buy a render, reach the paid song path, or send to her phone."""
import base64, copy, hashlib, importlib.util, json, math, os, shutil, socket, sys, tempfile, types, unittest, wave
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="motif-notebook-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(os.environ["SPARK_WORKSPACE"], "memory"), exist_ok=True)
NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)

sys.path.insert(0, os.path.join(REPO, "scripts"))
import motif_score as S
import motif_memory as MM
import midi_check
sys.path.insert(0, os.path.join(REPO, "broker")); import broker as BK
spec = importlib.util.spec_from_file_location("atelier_visit_motif", os.path.join(REPO, "scripts", "atelier-visit.py"))
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)

PHRASE = {"title": "the door", "tempo": [[0, 120], [4, 60]], "meter": "4/4",
          "notes": [[60, 0, 1, 80], [60, 1, 1, 70], [67, 2, 0.5, 90], [67, 2.5, 0.5, 90],   # repeated pitches, legato
                    [65, 3, 2, 75], [64, 5, 1, 60], [62, 6.5, 1.5, 64]]}                       # a rest at beat 6


class FakeBroker:
    """The scratch broker's routes, behind its own authorization matrix. Every url it is handed is recorded."""
    def __init__(self):
        self.urls = []

    def post(self, url, json=None, timeout=None, **k):
        self.urls.append(url)
        if not url.startswith(AV.B):
            raise AssertionError("posted outside the broker: %s" % url)
        path = url[len(AV.B):]
        ok, why = BK.authorize_route(path, json or {})
        body = BK.ROUTES[path](json) if ok else {"error": why}
        return types.SimpleNamespace(json=lambda: body)


class MotifNotebookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="motif-room-", dir=HOME)
        self.old = (BK.ROOT, BK.HEALTH, BK._KEYPATH)
        BK.ROOT, BK.HEALTH, BK._KEYPATH = self.tmp, os.path.join(self.tmp, "health.jsonl"), os.path.join(self.tmp, ".visit-key")
        os.makedirs(os.path.join(self.tmp, "projects"), exist_ok=True)
        self.scratch = tempfile.mkdtemp(prefix="motif-scratch-", dir=HOME)
        self.reveals = os.path.join(HOME, "reveals.json")
        if os.path.exists(MM.LAST): os.remove(MM.LAST)
        if os.path.exists(self.reveals): os.remove(self.reveals)

    def tearDown(self):
        BK.ROOT, BK.HEALTH, BK._KEYPATH = self.old
        shutil.rmtree(self.tmp, ignore_errors=True); shutil.rmtree(self.scratch, ignore_errors=True)

    # ------------------------------------------------------------------ isolation, asserted

    def test_the_suite_is_isolated_and_the_notebook_has_no_sender_or_paid_path(self):
        self.assertTrue(MM.WS.startswith(HOME) and MM.LAST.startswith(HOME) and MM.REVEALS.startswith(HOME))
        self.assertTrue(BK.ROOT.startswith(HOME))
        import ast
        for name in ("motif_memory.py", "motif_score.py"):
            src = open(os.path.join(REPO, "scripts", name)).read()
            imported = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import): imported |= {a.name.split(".")[0] for a in node.names}
                if isinstance(node, ast.ImportFrom): imported.add((node.module or "").split(".")[0])
            reach = imported & {"requests", "urllib", "http", "socket", "song_memory", "atelier_media", "paid_http",
                                "deliver", "atelier_voice"}
            self.assertFalse(reach, "%s must not import %s" % (name, sorted(reach)))
            for word in ("ntfy", "render_music", "dream-music", "https://"):
                self.assertFalse(word in src, "%s must not mention %s" % (name, word))
        song = open(os.path.join(REPO, "scripts", "song_memory.py")).read()
        self.assertIn("def too_close", song)            # the paid song path's refusal is still its own

    # ------------------------------------------------------------------ score and MIDI

    def test_round_trip_through_the_verifier_across_tempo_changes_and_repeated_pitches(self):
        score = S.validate(PHRASE)
        path = os.path.join(self.scratch, "p.mid")
        open(path, "wb").write(S.to_midi(score))
        div, notes, tempos = S.from_midi(path)
        want = S.timed(score)
        self.assertEqual(div, S.TICKS)
        self.assertEqual([n[2] for n in notes], [60, 60, 67, 67, 65, 64, 62])
        self.assertEqual(len(notes), len(want))
        for got, exp in zip(notes, want):
            self.assertAlmostEqual(got[0], exp[0], places=4); self.assertAlmostEqual(got[1], exp[1], places=4)
            self.assertEqual(got[3], exp[3])
        # 120 bpm for four beats is 2 s; then 60 bpm: the note at beat 5 starts at 3 s and the last ends at 6 s
        self.assertAlmostEqual(want[5][0], 3.0, places=6); self.assertAlmostEqual(want[-1][1], 6.0, places=6)
        self.assertEqual([t for _, t in tempos], [500000, 1000000])
        _, problems, coincident = midi_check.verify(*midi_check.read(path))
        self.assertEqual(problems, [], "a repeated pitch is released on the tick it is struck again, cleanly")
        self.assertIn((2 * S.TICKS, 60, 67), coincident)

    def test_rejections(self):
        bad = {
            "a note with no release": [[60, 0, None, 80]],
            "a note missing its duration": [{"pitch": 60, "onset": 0, "velocity": 80}],
            "a negative duration": [[60, 0, -1, 80]],
            "a zero-length note": [[60, 0, 0, 80]],
            "NaN pitch": [[float("nan"), 0, 1, 80]],
            "NaN onset": [[60, float("nan"), 1, 80]],
            "infinite duration": [[60, 0, float("inf"), 80]],
            "a pitch off the keyboard": [[12, 0, 1, 80]],
            "a velocity of zero": [[60, 0, 1, 0]],
            "two voices": [[60, 0, 2, 80], [64, 1, 1, 80]],
            "65 notes": [[60 + (i % 12), i * 0.25, 0.25, 80] for i in range(65)],
            "nine bars": [[60, 0, 1, 80], [62, 35, 1, 80]],
        }
        for why, notes in bad.items():
            with self.assertRaises(S.ScoreError, msg=why):
                S.validate({"tempo": 120, "meter": "4/4", "notes": notes})
        with self.assertRaises(S.ScoreError, msg="over 29 seconds"):
            S.validate({"tempo": 30, "meter": "4/4", "notes": [[60, 0, 1, 80], [62, 14, 1, 80]]})
        for tempo in (float("nan"), [[0, 120], [0, 60]], [[1, 120]], 1000):
            with self.assertRaises(S.ScoreError, msg=str(tempo)):
                S.validate({"tempo": tempo, "notes": [[60, 0, 1, 80]]})
        # NaN written as text in his request is refused, not rendered
        got = MM.step("0123456789ab", "cap", '<motif tempo="72">[[60, 0, NaN, 80]]</motif>', [], self._never_post)
        self.assertFalse(got["ok"]); self.assertIn("finite", got["error"])
        # a MIDI file with a note never released is refused on the way back in
        raw = bytearray(S.to_midi({"tempo": 120, "notes": [[60, 0, 1, 80]]}))
        off = raw.index(bytes([0x80, 60, 0]))
        raw[off:off + 3] = bytes([0xB0, 64, 0])          # the note-off becomes a pedal message: nothing releases it
        path = os.path.join(self.scratch, "unreleased.mid"); open(path, "wb").write(bytes(raw))
        with self.assertRaises(S.ScoreError):
            S.from_midi(path)
        # path traversal: scratch names, phrase ids and artifact names
        for name in ("../x.mid", "/etc/passwd", "a/b.mid", "..", ""):
            with self.assertRaises(MM.MotifError, msg=name):
                MM.inside(self.scratch, name)
        for ref in ("../../projects/0123456789ab/artifacts/x_write.json", "0123456789ab/x", "v../../..", ""):
            rec, why = MM.lookup(ref, [])
            self.assertIsNone(rec); self.assertIn("not name a phrase id", why)
        nb = MM.Notebook("0123456789ab", "cap", self._never_post)
        self.assertEqual(nb.records(["../../x_write.json", "20261025_120000_write.json/../../y"]), [])

    def _never_post(self, *a, **k):
        raise AssertionError("nothing should be posted here")

    # ------------------------------------------------------------------ render

    def test_render_in_scratch_with_the_existing_renderer_and_check_durations_and_attacks(self):
        rec = MM.phrase(PHRASE, "unlinked")
        before = set(os.listdir(self.scratch))
        got = MM.render(rec, base=self.scratch)
        self.assertEqual(set(os.listdir(self.scratch)), before, "the render's scratch directory is removed")
        self.assertIn("Events: all paired and clean.", got["report"])
        self.assertNotIn(self.scratch, got["report"])
        self.assertAlmostEqual(got["audio_seconds"], 7.0, places=2)       # 6 s of notes and the renderer's tail
        self.assertLessEqual(got["audio_seconds"], MM.AUDIO_SECONDS)
        wav = os.path.join(self.scratch, "check.wav"); open(wav, "wb").write(got["wav"])
        with wave.open(wav, "rb") as w:
            self.assertEqual(w.getframerate(), midi_check.RATE)
        heard = midi_check.attacks(wav)
        onsets = sorted({round(s, 4) for s, _, _, _ in S.timed(S.validate(PHRASE))})
        for s in onsets:
            self.assertTrue(heard and min(abs(h - s) for h in heard) < 0.05, "an attack lands at %.3f s" % s)
        with self.assertRaises(MM.MotifError):
            MM.render(rec, base=self.scratch, timeout=0.001)

    # ------------------------------------------------------------------ variations

    def test_transposition_changes_the_expected_pitches_and_never_the_parent(self):
        parent = MM.phrase(PHRASE, "the night the door stuck")
        frozen = copy.deepcopy(parent)
        child = MM.vary(parent, "transpose", by="5")
        self.assertEqual(parent, frozen, "the parent record is not touched")
        self.assertEqual([n["pitch"] for n in child["score"]["notes"]], [p + 5 for p in (60, 60, 67, 67, 65, 64, 62)])
        self.assertEqual(child["parent"], parent["variation_id"]); self.assertEqual(child["motif_id"], parent["motif_id"])
        self.assertNotEqual(child["variation_id"], parent["variation_id"])
        self.assertFalse(child["unchanged"])
        self.assertEqual(len(child["diff"]["notes"]), 7)
        self.assertTrue(all(r["fields"] == ["pitch"] and r["after"]["pitch"] - r["before"]["pitch"] == 5
                            for r in child["diff"]["notes"]))
        self.assertEqual(child["operation"], {"op": "transpose", "by": "5"})
        frag = MM.vary(parent, "fragment", by="3-5")
        self.assertEqual([n["pitch"] for n in frag["score"]["notes"]], [67, 67, 65])
        self.assertEqual(frag["score"]["notes"][0]["onset"], 0)
        self.assertEqual(frag["score"]["tempo"][0], [0, 120])
        slow = MM.vary(parent, "augment", by="2")
        self.assertEqual(slow["score"]["notes"][-1]["duration"], 3.0)
        inv = MM.vary(parent, "invert")
        self.assertEqual([n["pitch"] for n in inv["score"]["notes"]][:3], [60, 60, 53])
        with self.assertRaises(MM.MotifError):
            MM.vary(parent, "transpose", by="60")        # more than three octaves: refused
        high = MM.phrase({"tempo": 90, "notes": [[100, 0, 1, 80]]})
        with self.assertRaises(S.ScoreError):
            MM.vary(high, "transpose", by="12")          # off the keyboard: refused
        self.assertEqual(parent, frozen, "a refused variation leaves the parent as it was")

    def test_an_identical_variation_is_labelled_unchanged(self):
        parent = MM.phrase(PHRASE)
        same = MM.vary(parent, "transpose", by="0")
        self.assertTrue(same["unchanged"]); self.assertEqual(same["diff"]["notes"], [])
        self.assertTrue(same["diff"]["summary"].startswith("unchanged"))
        again = MM.vary(parent, "rewrite", notes=copy.deepcopy(PHRASE["notes"]))
        self.assertTrue(again["unchanged"])
        retempo = MM.vary(parent, "retempo", by="80")
        self.assertFalse(retempo["unchanged"]); self.assertEqual(retempo["diff"]["notes"], [])
        self.assertIn("tempo changed", retempo["diff"]["summary"])

    # ------------------------------------------------------------------ the room

    def _visit(self, pid):
        return BK.open_visit({"id": pid})

    def test_a_phrase_then_a_later_variation_both_render_and_stay_in_the_project(self):
        broker = FakeBroker()
        pid = BK.create_project({"intent": "a melody that comes back", "sealed": True})["id"]
        BK.to_table({"id": pid})
        sent = []
        with mock.patch.object(AV.requests, "post", side_effect=broker.post), \
             mock.patch.object(AV, "_failed", side_effect=lambda *a: sent.append(a)), \
             mock.patch.object(AV, "MOTIF_REVEALS", self.reveals):
            pk = self._visit(pid)
            current, text = AV.motif_notebook(pid, pk, pk["visit_capability"])
            self.assertEqual(current, [])
            self.assertIn("YOUR MOTIF NOTEBOOK", text); self.assertIn("The notebook is empty.", text)
            self.assertIn("<motif title=", text); self.assertIn("<motif_vary of=", text)
            work = ('<piece kind="write">a note</piece><motif title="the door" tempo="120, 4:60" meter="4/4" '
                    'origin="unlinked">%s it came out of the hallway</motif>' % json.dumps(PHRASE["notes"]))
            self.assertFalse(AV.made_nothing('<motif tempo="72">[[60,0,1,80]]</motif>', {}))
            first = AV.motif_step(pid, pk["visit_capability"], work, current)
            self.assertTrue(first["ok"], first)
            BK.handoff({"id": pid, "text": "made the phrase", "capability": pk["visit_capability"]})

            # a later ordinary visit: he meets the phrase and chooses to vary it
            pk = self._visit(pid)
            current, text = AV.motif_notebook(pid, pk, pk["visit_capability"])
            self.assertEqual([r["variation_id"] for r in current], [first["variation_id"]])
            self.assertIn(first["variation_id"], text); self.assertIn("YOUR LAST PHRASE WAS MADE", text)
            self.assertIn("timing check: Rendered attacks", text)
            ad = os.path.join(BK._p(pid), "artifacts")
            parent_bytes = hashlib.sha256(open(os.path.join(ad, first["record"]), "rb").read()).hexdigest()
            second = AV.motif_step(pid, pk["visit_capability"],
                                   '<motif_vary of="%s" op="transpose" by="-3">lower, as if from further off</motif_vary>'
                                   % first["variation_id"], current)
            self.assertTrue(second["ok"], second)
            self.assertEqual((second["parent"], second["op"], second["unchanged"]), (first["variation_id"], "transpose", False))
        self.assertEqual(sent, [])
        self.assertTrue(all(u.startswith(AV.B) for u in broker.urls), broker.urls)
        self.assertEqual(NET, [])
        names = sorted(os.listdir(ad))
        self.assertEqual(sum(n.endswith("_music.wav") for n in names), 2, names)
        self.assertEqual(hashlib.sha256(open(os.path.join(ad, first["record"]), "rb").read()).hexdigest(), parent_bytes)
        child = json.load(open(os.path.join(ad, second["record"])))
        self.assertEqual(child["parent"], first["variation_id"])
        self.assertEqual([n["pitch"] for n in child["score"]["notes"]], [p - 3 for p in (60, 60, 67, 67, 65, 64, 62)])
        self.assertIn("Events: all paired and clean.", child["timing_report"])
        self.assertEqual(base64.b64decode(child["midi_b64"])[:4], b"MThd")
        for f in (first["audio"], second["audio"]):
            self.assertEqual(open(os.path.join(ad, f), "rb").read()[:4], b"RIFF")
        last = json.load(open(MM.LAST))
        self.assertNotIn("notes", json.dumps(last)); self.assertNotIn("hallway", json.dumps(last))

    def test_a_sealed_projects_phrase_is_not_reachable_from_another_project_until_revealed(self):
        broker = FakeBroker()
        sealed = BK.create_project({"intent": "private", "sealed": True})["id"]
        pk = self._visit(sealed)
        made = MM.step(sealed, pk["visit_capability"], '<motif tempo="90">[[60,0,1,80],[64,1,1,80]]</motif>', [],
                       broker.post, reveals=self.reveals)
        self.assertTrue(made["ok"], made)
        other = BK.create_project({"intent": "the next work", "sealed": True})["id"]
        pk2 = self._visit(other)
        current = MM.Notebook(other, pk2["visit_capability"], broker.post).records(list(pk2["artifacts"]))
        self.assertEqual(current, [])
        rec, why = MM.lookup(made["variation_id"], current, reveals=self.reveals)
        self.assertIsNone(rec); self.assertIn("sealed project's phrases stay in that project", why)
        # the other project's capability does not open the sealed project's record either
        got = broker.post(AV.B + "/artifact", json={"id": sealed, "file": made["record"],
                                                   "visit_capability": pk2["visit_capability"]}).json()
        self.assertNotIn("content", got)
        tried = MM.step(other, pk2["visit_capability"], '<motif_vary of="%s" op="transpose" by="2"></motif_vary>'
                        % made["variation_id"], current, broker.post, reveals=self.reveals)
        self.assertFalse(tried["ok"]); self.assertIn("stay in that project", tried["error"])
        # once he reveals it (the reveals store his reveal action writes), it may recur in later work
        content = open(os.path.join(BK._p(sealed), "artifacts", made["record"])).read()
        json.dump([{"revealed": True, "medium": "write", "artifact": made["record"], "content": content}],
                  open(self.reveals, "w"))
        rec, why = MM.lookup(made["variation_id"], current, reveals=self.reveals)
        self.assertEqual(rec["variation_id"], made["variation_id"]); self.assertIsNone(why)
        self.assertIn("PHRASES YOU HAVE REVEALED", MM.block(current, reveals=self.reveals))
        varied = MM.step(other, pk2["visit_capability"], '<motif_vary of="%s" op="retrograde"></motif_vary>'
                         % made["variation_id"], current, broker.post, reveals=self.reveals)
        self.assertTrue(varied["ok"], varied)
        self.assertTrue(os.path.isfile(os.path.join(BK._p(other), "artifacts", varied["record"])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
