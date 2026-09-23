#!/usr/bin/env python3
"""Image and music cross only into a scratch broker room; senders are stubbed."""
import base64, importlib.util, json, os, shutil, sys, tempfile, types, unittest
from unittest import mock

try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


MEDIA = load("atelier_media_test", os.path.join(ROOT, "scripts", "atelier_media.py"))
VISIT = load("atelier_visit_media_test", os.path.join(ROOT, "scripts", "atelier-visit.py"))
sys.path.insert(0, os.path.join(ROOT, "broker")); import broker as BK


class AtelierMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="atelier-media-")
        self.old_root, BK.ROOT = BK.ROOT, self.tmp
        BK.HEALTH = os.path.join(self.tmp, "health.jsonl")
        BK._KEYPATH = os.path.join(self.tmp, ".visit-key")
        os.makedirs(os.path.join(self.tmp, "projects"), exist_ok=True)

    def tearDown(self):
        BK.ROOT = self.old_root; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_image_and_music_use_existing_renderers_without_public_writes(self):
        art = types.SimpleNamespace(_local_render=lambda prompt: b"\x89PNG\r\nprivate")
        music = types.SimpleNamespace(generate=lambda *a: "task-1", poll=lambda _t: [{"audio_url": "/track"}],
                                      dl=lambda _u, path: open(path, "wb").write(b"RIFFprivate") > 0)
        with mock.patch.object(MEDIA, "_load", side_effect=lambda _n, f: art if f == "dream-art.py" else music):
            image = MEDIA.render_image("a blue room")
            song = MEDIA.render_music("return", "low strings")
        self.assertEqual(image["bytes"], b"\x89PNG\r\nprivate")
        self.assertEqual(song["bytes"], b"RIFFprivate")
        self.assertFalse(any("gallery" in p or "activity" in p for p in os.listdir(self.tmp)))

    def test_binary_artifact_is_kept_and_read_in_the_scratch_room(self):
        pid = BK.create_project({"intent": "paint privately", "sealed": True})["id"]
        BK.to_table({"id": pid}); opened = BK.open_visit({"id": pid})
        body = {"id": pid, "kind": "image", "ext": "png",
                "content_b64": base64.b64encode(b"\x89PNG\r\nprivate").decode(),
                "visit_capability": opened["visit_capability"]}
        made = BK.make(body)
        self.assertTrue(made["ok"])
        got = BK.read_artifact({"id": pid, "file": made["file"]})
        self.assertEqual(got["encoding"], "base64")
        self.assertTrue(got["content"].startswith("data:image/png;base64,"))
        self.assertTrue(os.path.realpath(os.path.join(BK._p(pid), "artifacts", made["file"])).startswith(os.path.realpath(self.tmp)))

        BK.inspect({"id": pid, "kind": "image", "artifact": made["file"], "note": "seen"})
        song = BK.make({"id": pid, "kind": "music", "ext": "wav",
                        "content_b64": base64.b64encode(b"RIFF-entirely-ascii").decode()})
        heard = BK.read_artifact({"id": pid, "file": song["file"]})
        self.assertEqual(heard["encoding"], "base64", "a valid-UTF8 WAV is still binary by its medium")
        self.assertTrue(heard["content"].startswith("data:audio/wav;base64,"))

    def test_media_requests_parse_in_any_attribute_order_and_quote(self):
        # 2026-09-23: his music requests matched nothing and vanished without a make, refusal or log.
        for text in ('<music style="low strings" title="return" duration="90">hum</music>',
                     "<music title='return' style='low strings'>hum</music>",
                     '<music duration="90s" title="return" style="low strings">hum</music>'):
            got = VISIT._media_request(text)
            self.assertEqual((got["kind"], got["title"], got["style"]), ("music", "return", "low strings"), text)
        self.assertEqual(VISIT._media_request('<music title="bare">hum</music>')["style"], "open")
        self.assertEqual(VISIT._media_request("<image>a blue room</image>")["prompt"], "a blue room")
        self.assertEqual(VISIT._media_request('<image prompt="blue pressure">night</image>')["title"], "night")
        self.assertIsNone(VISIT._media_request("no request here"))
    def test_status_reports_no_image_model_when_none_is_cached(self):
        art = types.SimpleNamespace(_find_local_model=lambda: ("", ""))
        with mock.patch.object(MEDIA, "_load", side_effect=lambda _n, f: art if f == "dream-art.py" else None):
            self.assertFalse(MEDIA.status()["image"]["ok"])
    def test_visit_elects_image_and_broker_receives_only_encoded_bytes(self):
        renderer = types.SimpleNamespace(render_image=lambda _p: {"ok": True, "kind": "image",
            "ext": "png", "mime_type": "image/png", "bytes": b"pngbytes", "size": 8})
        calls = []
        def post(url, json=None, timeout=None):
            calls.append((url, json)); return types.SimpleNamespace(json=lambda: {"ok": True, "file": "made_image.png"})
        follow = "<media_reading>The color holds.</media_reading><handoff>keep looking</handoff>"
        with mock.patch.object(VISIT, "_media_module", return_value=renderer), \
             mock.patch.object(VISIT, "ask", return_value=follow), \
             mock.patch.object(VISIT.requests, "post", side_effect=post):
            out = VISIT.media_loop("project", "sealed context", '<image prompt="blue pressure">night</image>', "cap")
        made = next(body for url, body in calls if url.endswith("/make"))
        self.assertEqual(base64.b64decode(made["content_b64"]), b"pngbytes")
        self.assertEqual(made["kind"], "image")
        self.assertNotIn("content", made)
        self.assertIn("The color holds", out)

    def test_prompt_names_outages_instead_of_erasing_media(self):
        state = {"image": {"configured": False, "ok": False, "outage": "no painter"},
                 "music": {"configured": True, "ok": False, "outage": "composer asleep"}}
        with mock.patch.object(VISIT, "_media_module", return_value=types.SimpleNamespace(status=lambda: state)):
            block = VISIT.media_block()
        self.assertIn("IMAGE outage: no painter", block)
        self.assertIn("MUSIC outage: composer asleep", block)


if __name__ == "__main__": unittest.main(verbosity=2)
