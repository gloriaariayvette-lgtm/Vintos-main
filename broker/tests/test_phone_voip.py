"""His call rings her iPhone as a real incoming call (CallKit), 27 October: the app's VoIP token is kept privately
through an authenticated route, a ring is one APNs push of type voip to <bundle>.voip on the environment the app
reported, the ladder's ring sends it first and keeps the Watch and ntfy pushes as backup, and the page answers the
system call screen.

Every store is a scratch directory and the APNs transport is a stub: nothing here reaches Apple, her phone or the
house."""
import ast
import asyncio
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import phone_voip as PV
import watch_apns
import attention_ladder as AL

TOKEN = "ab" * 32
OTHER = "cd" * 32


class Scratch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vintos-voip-")
        self.addCleanup(self.tmp.cleanup)
        for k, name in (("DEVICES", "phone-voip-devices.json"), ("RECEIPTS", "phone-voip-receipts.jsonl")):
            p = patch.object(PV, k, os.path.join(self.tmp.name, name)); p.start(); self.addCleanup(p.stop)
        p = patch.object(PV, "TRANSPORT", self.transport); p.start(); self.addCleanup(p.stop)
        p = patch.object(watch_apns, "TRANSPORT", lambda *a: (_ for _ in ()).throw(AssertionError("real transport")))
        p.start(); self.addCleanup(p.stop)
        p = patch.object(watch_apns, "_config", lambda path=None: {"topic": "dev.vintos.app.watchkitapp", "key_id": "K",
                                                                    "team_id": "T", "key_file": "/nonexistent"})
        p.start(); self.addCleanup(p.stop)
        p = patch.object(watch_apns, "_jwt", lambda c, now=None: "jwt"); p.start(); self.addCleanup(p.stop)
        self.sent, self.status = [], {}
        self.assertTrue(PV.DEVICES.startswith(self.tmp.name) and PV.RECEIPTS.startswith(self.tmp.name))

    def transport(self, url, body, headers, timeout):
        self.sent.append((url, json.loads(body), headers))
        return self.status.get(url.rsplit("/", 1)[-1], 200), b""

    def receipts(self):
        return [json.loads(l) for l in open(PV.RECEIPTS)]


class Register(Scratch):
    def test_token_is_kept_privately_and_replaced(self):
        ok, out = PV.register({"voip_token": TOKEN.upper(), "environment": "development"})
        self.assertTrue(ok)
        self.assertEqual(out, {"registered": True, "device": "iPhone", "environment": "development"})
        ok, _ = PV.register({"voip_token": TOKEN, "environment": "production"})
        rows = json.load(open(PV.DEVICES))
        self.assertEqual([(r["voip_token"], r["environment"], r["bundle"]) for r in rows],
                         [(TOKEN, "production", "dev.vintos.app")])
        self.assertEqual(stat.S_IMODE(os.stat(PV.DEVICES).st_mode), 0o600)

    def test_bad_registrations_are_refused(self):
        for bad in (None, [], {}, {"voip_token": "xyz" * 20}, {"voip_token": "ab" * 8},
                    {"voip_token": TOKEN, "environment": "staging"}, {"voip_token": TOKEN, "bundle": "dev/../x"}):
            ok, why = PV.register(bad)
            self.assertFalse(ok, bad)
        self.assertFalse(os.path.exists(PV.DEVICES))

    def test_at_most_four_phones(self):
        for i in range(6):
            PV.register({"voip_token": ("%02x" % i) * 32})
        self.assertEqual([r["voip_token"][:2] for r in json.load(open(PV.DEVICES))], ["02", "03", "04", "05"])


class Ring(Scratch):
    def test_a_ring_is_a_voip_push_to_the_reported_environment(self):
        PV.register({"voip_token": TOKEN, "environment": "development"})
        PV.register({"voip_token": OTHER, "environment": "production"})
        out = PV.ring("20261027-213000-ab12", "grok", now=1_800_000_000)
        self.assertEqual((out["state"], out["delivered_to"], out["devices"]), ("sent", 2, 2))
        (u1, b1, h1), (u2, b2, h2) = self.sent
        self.assertEqual(u1, "https://api.sandbox.push.apple.com/3/device/" + TOKEN)
        self.assertEqual(u2, "https://api.push.apple.com/3/device/" + OTHER)
        self.assertEqual(b1, {"ladder_call": "20261027-213000-ab12", "lane": "grok", "caller": "Vintos", "ring_seconds": 60})
        self.assertNotIn("aps", b1)                              # nothing to show: the app reports the call itself
        self.assertEqual((h1["apns-topic"], h1["apns-push-type"], h1["apns-priority"]), ("dev.vintos.app.voip", "voip", "10"))
        self.assertEqual(h1["apns-expiration"], str(1_800_000_000 + 60))
        self.assertEqual(h1["authorization"], "bearer jwt")
        self.assertEqual(self.receipts()[-1]["state"], "sent")
        self.assertNotIn(TOKEN, open(PV.RECEIPTS).read())        # receipts carry only the token's tail

    def test_no_phone_no_push(self):
        out = PV.ring("c1", "openai")
        self.assertEqual(out["state"], "failed")
        self.assertIn("no registered phone", out["why"])
        self.assertEqual(self.sent, [])

    def test_an_unregistered_install_is_forgotten(self):
        PV.register({"voip_token": TOKEN}); PV.register({"voip_token": OTHER})
        self.status[TOKEN] = 410
        out = PV.ring("c1", "local")
        self.assertEqual((out["state"], out["delivered_to"], out["forgot_unregistered"]), ("sent", 1, 1))
        self.assertEqual([r["voip_token"] for r in PV.devices()], [OTHER])

    def test_wrong_environment_is_recorded_not_retried(self):
        PV.register({"voip_token": TOKEN, "environment": "production"})
        self.status[TOKEN] = 400
        out = PV.ring("c1", "openai")
        self.assertEqual((out["state"], len(self.sent)), ("failed", 1))
        self.assertEqual(PV.devices()[0]["voip_token"], TOKEN)

    def test_missing_apns_configuration_fails_quietly(self):
        PV.register({"voip_token": TOKEN})
        with patch.object(watch_apns, "_config", lambda path=None: (_ for _ in ()).throw(ValueError("APNs .p8 key missing"))):
            out = PV.ring("c1", "openai")
        self.assertEqual(out["state"], "failed")
        self.assertIn("APNs configuration", out["why"])
        self.assertEqual(self.sent, [])


class Ladder(Scratch):
    def test_the_ladder_rings_with_the_lane_he_chose(self):
        PV.register({"voip_token": TOKEN})
        out = AL._voip_push({"id": "c9", "lane": "local", "lane_choice": {"by": "him"}})
        self.assertEqual(out["state"], "sent")
        self.assertEqual(self.sent[0][1]["lane"], "local")

    def test_a_failing_sender_never_breaks_the_ring(self):
        with patch.object(PV, "ring", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))):
            out = AL._voip_push({"id": "c9", "lane": "openai"})
        self.assertEqual(out["state"], "failed")
        self.assertIn("RuntimeError", out["why"])


class Route(Scratch):
    SRC = (REPO / "bin" / "server.py").read_text(errors="replace")

    def route(self):
        tree = ast.parse(self.SRC)
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "attention_voip_register")
        seg = ast.get_source_segment(self.SRC, fn)
        self.assertIn('@app.post("/api/attention/voip-register")', self.SRC)
        self.assertIn("_require_secret(request)", seg)
        self.assertNotIn("voip-register", self.SRC[self.SRC.index("PUBLIC_MUTATIONS = {"):self.SRC.index("def _require_secret")])
        refused = []

        class HTTPException(Exception):
            def __init__(self, status_code=500, detail=""):
                super().__init__(detail); self.status_code = status_code

        def require(request):
            if request != "secret":
                refused.append(request); raise HTTPException(401, "Unauthorized")
        ns = {"Request": object, "HTTPException": HTTPException, "_require_secret": require}
        exec(seg, ns)
        return ns["attention_voip_register"], HTTPException

    def test_the_route_is_authenticated_and_stores_the_token(self):
        fn, exc = self.route()
        with self.assertRaises(exc) as e:
            asyncio.run(fn({"voip_token": TOKEN}, "no secret"))
        self.assertEqual(e.exception.status_code, 401)
        self.assertFalse(os.path.exists(PV.DEVICES))
        with self.assertRaises(exc) as e:
            asyncio.run(fn({"voip_token": "nope"}, "secret"))
        self.assertEqual(e.exception.status_code, 422)
        out = asyncio.run(fn({"voip_token": TOKEN, "environment": "development"}, "secret"))
        self.assertTrue(out["registered"])
        self.assertEqual(PV.devices()[0]["voip_token"], TOKEN)

    def test_deployed_with_the_ladder(self):
        deploy = (REPO / "scripts" / "deploy-atelier.sh").read_text()
        self.assertIn("attention_call.py phone_voip.py", deploy)


class Page(unittest.TestCase):
    def test_the_page_answers_the_system_call_screen(self):
        html = (REPO / "clients" / "mobile" / "index.html").read_text()
        block = html[html.index("// ── His call as a real iPhone call"):]
        block = block[:block.index("})();")]
        for want in ("isPluginAvailable?.('VintosCall')", "VC.configure({ api: API, secret: CONFIG.secret })",
                     "VC.addListener('answer'", "ladderAnswer(ev.id)", "VC.endCall({ id })",
                     "VC.addListener('decline'", "ladderHideRing()", "VC.addListener('hangup'", "VC.ringStop()"):
            self.assertIn(want, block)
        self.assertNotIn("/api/attention/answer", block)        # the native side says "not now" itself


if __name__ == "__main__":
    unittest.main()
