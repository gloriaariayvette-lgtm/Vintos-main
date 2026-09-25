"""His Grok images and video run on Gloria's SuperGrok login, never Atlas or the API key.
Scratch HOME; the login file, cap config and usage ledger are throwaway; every network call is a
stub, and the suite asserts that nothing real is reachable."""
import importlib.util, io, json, os, sys, tempfile, time, types, unittest, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vintos-grok-sub-")
os.environ.update(HOME=HOME, VINTOS_GROK_AUTH=os.path.join(HOME, ".grok", "auth.json"),
                  VINTOS_GROK_SUB_CONFIG=os.path.join(HOME, ".vintos", "grok-subscription.json"),
                  VINTOS_GROK_SUB_USAGE=os.path.join(HOME, ".vintos", "grok-subscription-usage.jsonl"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
spec = importlib.util.spec_from_file_location("grok_subscription", os.path.join(ROOT, "scripts", "grok_subscription.py"))
G = importlib.util.module_from_spec(spec); sys.modules["grok_subscription"] = G; spec.loader.exec_module(G)

IMG = os.path.join(HOME, "hero.jpg"); open(IMG, "wb").write(b"\xff\xd8\xffjpg")
B64 = "aW1n"   # "img"


class Resp:
    def __init__(self, obj): self.raw = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
    def read(self, *a): return self.raw
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Net:
    """Answers by URL; records every request. Anything unexpected fails the test."""
    def __init__(self, routes): self.routes, self.calls = routes, []
    def __call__(self, req, timeout=0):
        url = req if isinstance(req, str) else req.full_url
        body = None if isinstance(req, str) or req.data is None else req.data
        self.calls.append((url, body, {} if isinstance(req, str) else dict(req.header_items())))
        for prefix, answer in self.routes:
            if url.startswith(prefix):
                if isinstance(answer, Exception): raise answer
                return Resp(answer(url, body) if callable(answer) else answer)
        raise AssertionError("unexpected request: " + url)


def login(expires_at):
    os.makedirs(os.path.dirname(G.AUTH), exist_ok=True)
    with open(G.AUTH, "w") as f: json.dump({"https://auth.x.ai::cid": {"key": "tok-old", "refresh_token": "rt-old", "expires_at": expires_at,
                                          "oidc_issuer": "https://auth.x.ai", "oidc_client_id": "cid",
                                          "email": "g@example.com"}}, f)


class GrokSubscription(unittest.TestCase):
    def setUp(self):
        for f in (G.USAGE, G.CONFIG):
            if os.path.exists(f): os.unlink(f)
        login(time.time() + 5 * 86400)

    def test_isolation(self):
        for p in (G.AUTH, G.CONFIG, G.USAGE): self.assertTrue(p.startswith(HOME), p)
        G._open = Net([])
        with self.assertRaises(AssertionError): G._open("https://api.x.ai/v1/anything")

    def test_image_uses_her_login_on_api_x_ai(self):
        net = G._open = Net([("https://api.x.ai/v1/images/generations", {"data": [{"b64_json": B64}]})])
        data, _ = G.image("a lighthouse")
        self.assertEqual(data, b"img")
        url, body, headers = net.calls[0]
        self.assertEqual(headers.get("Authorization"), "Bearer tok-old")
        self.assertEqual(json.loads(body)["model"], "grok-imagine-image")
        self.assertIn("1 of 40", G.status()["images_this_week"])

    def test_a_token_near_expiry_refreshes_and_is_written_back(self):
        login(time.time() + 60)
        net = G._open = Net([("https://auth.x.ai/.well-known", {"token_endpoint": "https://auth.x.ai/token"}),
                             ("https://auth.x.ai/token", {"access_token": "tok-new", "refresh_token": "rt-new",
                                                          "expires_in": 604800}),
                             ("https://api.x.ai/", {"data": [{"b64_json": B64}]})])
        G.image("x")
        saved = json.load(open(G.AUTH))["https://auth.x.ai::cid"]
        self.assertEqual((saved["key"], saved["refresh_token"], saved["email"]), ("tok-new", "rt-new", "g@example.com"))
        self.assertEqual(oct(os.stat(G.AUTH).st_mode & 0o777), "0o600")
        self.assertIn("grant_type=refresh_token", net.calls[1][1].decode())
        self.assertEqual(net.calls[2][2].get("Authorization"), "Bearer tok-new")

    def test_no_login_makes_nothing(self):
        os.unlink(G.AUTH)
        G._open = Net([])
        with self.assertRaises(G.Unavailable): G.image("x")

    def test_a_refusal_is_unavailable_not_a_fallback(self):
        G._open = Net([("https://api.x.ai/", urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"no")))])
        with self.assertRaises(G.Unavailable): G.image("x")

    def test_the_weekly_cap_stops_before_any_request(self):
        with open(G.CONFIG, "w") as f: json.dump({"images_per_week": 1}, f)
        G._open = Net([("https://api.x.ai/", {"data": [{"b64_json": B64}]})])
        G.image("x")
        G._open = Net([])
        with self.assertRaises(G.Unavailable): G.image("y")

    def test_edit_sends_one_or_several_references(self):
        net = G._open = Net([("https://api.x.ai/v1/images/edits", {"data": [{"b64_json": B64}]})])
        G.edit("him in a field", [IMG])
        G.edit("him and her", [IMG, IMG])
        one, two = (json.loads(c[1]) for c in net.calls)
        self.assertIn("image", one); self.assertNotIn("images", one)
        self.assertEqual(len(two["images"]), 2)

    def test_video_submits_polls_and_downloads(self):
        net = G._open = Net([("https://api.x.ai/v1/videos/generations", {"id": "V1"}),
                             ("https://api.x.ai/v1/videos/V1", {"status": "done", "video": {"url": "https://cdn/v.mp4"}}),
                             ("https://cdn/v.mp4", b"mp4")])
        self.assertEqual(G.video("slow push in", IMG, duration=40, sleep=lambda s: None), b"mp4")
        self.assertEqual(json.loads(net.calls[0][1])["duration"], 15, "xAI's own 15 s limit")
        self.assertNotIn("Authorization", net.calls[-1][2], "the download link is not sent her token")


class CallersUseTheSubscription(unittest.TestCase):
    def test_send_video_animates_and_builds_stills_on_the_subscription(self):
        def no_network(*a, **k): raise AssertionError("Atlas or the API key must not be reached for Grok steps")
        sys.modules["requests"] = types.SimpleNamespace(post=no_network, get=no_network)
        for m in ("deliver", "reflection_stage"): sys.modules[m] = types.SimpleNamespace(CHANNELS={}, deliver=no_network)
        sys.modules["artifact_manifest"] = types.SimpleNamespace(
            unique_path=lambda d, stem, ext, data: (os.path.join(d, stem + ext), 1))
        vs = importlib.util.spec_from_file_location("vsv_sub_test", os.path.join(ROOT, "bin", "vintos-send-video.py"))
        V = importlib.util.module_from_spec(vs); vs.loader.exec_module(V)
        V.HERO = IMG; V.SCENE_DIR = os.path.join(HOME, "scenes"); V.ATLAS_KEY = ""
        calls = []
        real = (G.video, G.edit)
        self.addCleanup(lambda: (setattr(G, "video", real[0]), setattr(G, "edit", real[1])))
        G.video = lambda prompt, still, duration=6, **k: calls.append(("video", still, duration)) or b"mp4"
        G.edit = lambda prompt, refs, **k: calls.append(("edit", refs)) or b"jpg"
        self.assertEqual(V.atlas_generate("I turn to her", IMG, model=V.GROK_VIDEO_MODEL, duration=10), b"mp4")
        self.assertTrue(V.make_scene_still("on a porch at dusk").startswith(HOME))
        self.assertEqual(calls, [("video", IMG, 10), ("edit", [IMG])])
        G.video = lambda *a, **k: (_ for _ in ()).throw(G.Unavailable("cap"))
        self.assertIsNone(V.atlas_generate("x", IMG, model=V.GROK_VIDEO_MODEL), "unavailable makes nothing")

    def test_no_grok_caller_still_uses_the_api_key_for_imagine(self):
        for rel in ("bin/vintos-video.py", "bin/dream-art.py", "scripts/dream-art.py", "bin/vintos-send-video.py"):
            src = open(os.path.join(ROOT, rel)).read()
            self.assertNotIn("api.x.ai/v1/images", src, rel)
            self.assertNotIn("api.x.ai/v1/videos", src, rel)


if __name__ == "__main__":
    unittest.main()
