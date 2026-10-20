"""Replay the 18 October Kie refusal: artist-reference tags and terminal tasks left pending.
Every store is scratch; models, HTTP, sockets, subprocesses and landing effects are stubs."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


class MusicReferenceFailure(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="music-reference-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        p = patch.dict(os.environ, HOME=str(self.root), SPARK_WORKSPACE=str(self.root / "workspace"),
                       VINTOS_ENV_FILE=str(self.root / "absent.env"))
        p.start(); self.addCleanup(p.stop)
        self.requests = types.SimpleNamespace(
            post=Mock(side_effect=AssertionError("no provider POST")),
            get=Mock(side_effect=AssertionError("no provider GET")))
        for p in (patch.dict(sys.modules, requests=self.requests),
                  patch("socket.socket.connect", side_effect=AssertionError("no sockets")),
                  patch("socket.create_connection", side_effect=AssertionError("no sockets")),
                  patch("subprocess.Popen", side_effect=AssertionError("no subprocess")),
                  patch("urllib.request.urlopen", side_effect=AssertionError("no models or HTTP"))):
            p.start(); self.addCleanup(p.stop)
        spec = importlib.util.spec_from_file_location("music_reference_fixture", REPO / "bin/dream_music.py")
        self.dm = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.dm)
        for name in ("MUSIC", "PROMPTS", "JOURNAL", "TEMPORAL_FILE"):
            setattr(self.dm, name, str(self.root / name.lower()))
        self.dm.LOG = str(self.root / "music/music.json")
        self.dm.KIE_KEY = "fixture-secret"
        self.dm.time.sleep = lambda *_: None
        self.dm._admit_ctx = lambda *_: contextlib.nullcontext()
        self.dm._feel_landed = Mock(side_effect=AssertionError("no live landing effects"))
        self.assertTrue(all(str(getattr(self.dm, n)).startswith(str(self.root))
                            for n in ("MUSIC", "LOG", "PROMPTS", "JOURNAL", "TEMPORAL_FILE")))
        self.assertIs(sys.modules["requests"], self.requests)

    def response(self, data): return types.SimpleNamespace(json=lambda: data)

    def test_reference_points_removed_before_kie_without_rewriting_lyrics(self):
        style = self.dm.style_str({"genre": "Dark-edged synth-pop. Arpeggiated bass and gated kicks. "
            "Reference points: early Erasure's melancholy, a little Depeche Mode cold-machine tension, "
            "a dash of Blade Runner soundtrack glow. No strings, no acoustic instruments.",
            "tempo": "100 BPM, F minor"})
        self.assertIn("Arpeggiated bass", style)
        self.assertIn("No strings", style)
        self.assertIn("100 BPM, F minor", style)
        for name in ("Erasure", "Depeche", "Blade Runner", "Reference points"):
            self.assertNotIn(name, style)
        self.requests.post.side_effect = None
        self.requests.post.return_value = self.response({"code": 200, "data": {"taskId": "fixture"}})
        lyrics = "[Chorus]\nAn original fixture line\n"
        self.assertEqual(self.dm._kie_generate("Fixture", style, lyrics, False, 180, "male"), "fixture")
        body = self.requests.post.call_args.kwargs["json"]
        self.assertEqual(body["prompt"], lyrics.strip())
        self.assertEqual(body["model"], "V6")
        self.assertNotIn("Depeche", body["style"])
        self.assertEqual(body["vocalGender"], "m")

    def test_other_reference_labels_and_plain_sonic_style(self):
        for label in ("References", "Reference", "Influences", "Inspirations", "REFERENCE POINTS"):
            with self.subTest(label=label):
                clean = self.dm.style_str({"genre": "Analog bass. " + label + ": Named Band. Warm claps.",
                                           "tempo": "90 BPM"})
                self.assertNotIn("Named Band", clean)
                self.assertIn("Warm claps", clean)
                self.assertIn("90 BPM", clean)
        self.assertEqual(self.dm.style_str({"genre": "warm synth-pop", "tempo": "90 BPM"}),
                         "warm synth-pop, 90 BPM")

    def test_terminal_provider_failure_is_recorded_not_polled_forever(self):
        self.dm._landing_begin("kie:failed-task", "Fixture", 0, {"source": "fixture.md"})
        self.requests.get.side_effect = None
        self.requests.get.return_value = self.response({"code": 200, "data": {
            "status": "GENERATE_AUDIO_FAILED", "errorCode": 400,
            "errorMessage": "Your tags contain artist name depeche mode. fixture-secret"}})
        output = io.StringIO()
        with contextlib.redirect_stderr(output): self.assertIsNone(self.dm._kie_poll("failed-task"))
        self.assertIn("GENERATE_AUDIO_FAILED (code 400)", output.getvalue())
        self.assertIn("artist name depeche mode", output.getvalue())
        self.assertNotIn("fixture-secret", output.getvalue())
        log = self.dm.load_log()
        landing = log["landings"][0]
        self.assertEqual(landing["state"], "failed")
        self.assertEqual(landing["failure"]["code"], 400)
        self.assertNotIn("fixture-secret", json.dumps(log))
        self.assertEqual(self.dm.pending_landings(float("inf")), [])
        self.assertEqual(self.dm.resume_landings(), [])
        self.assertEqual(self.requests.get.call_count, 1)
        self.requests.post.assert_not_called()
        self.assertEqual(log["generated"], [])
        self.assertNotIn("fixture.md", log["processed_files"])

    def test_transport_failure_stays_pending_without_replacement_submission(self):
        self.dm._landing_begin("kie:unknown-task", "Fixture", 0, {"source": "fixture.md"})
        self.requests.get.side_effect = OSError("fixture network outage")
        with patch.object(self.dm.time, "time", side_effect=[0, 1, 601]), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(self.dm._kie_poll("unknown-task"))
        self.assertEqual(len(self.dm.pending_landings(float("inf"))), 1)
        self.requests.post.assert_not_called()

    def test_cli_signals_failed_render_and_skips_draft_sidecar(self):
        prompts = Path(self.dm.PROMPTS); prompts.mkdir()
        song = prompts / "2026-10-18_051541.md"; song.write_text("**Title:** Fixture")
        Path(str(song) + ".sonnet-draft.md").write_text("**Title:** Draft")
        with patch.object(sys, "argv", ["dream_music.py"]), \
                patch.object(self.dm, "resume_landings", return_value=[]), \
                patch.object(self.dm, "process_file", return_value=False) as process:
            with self.assertRaises(SystemExit) as exc: self.dm.main()
        self.assertEqual(exc.exception.code, 1)
        process.assert_called_once_with(str(song), False)

    def test_renderer_twins_and_writers_use_the_same_contract(self):
        self.assertEqual((REPO / "bin/dream_music.py").read_bytes(),
                         (REPO / "scripts/dream-music.py").read_bytes())
        import song_draft
        self.assertIn("without named artists", song_draft.FINISH)
        composer = (REPO / "bin/music-composer.py").read_text()
        self.assertIn("no named artists", composer)
        self.assertEqual(song_draft.SONNET, "claude-sonnet-5-5")
        self.assertEqual(song_draft.GROK, "grok-4.20-0309-non-reasoning")


if __name__ == "__main__": unittest.main()
