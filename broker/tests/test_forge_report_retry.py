"""The Lab's Forge report sender stops hammering a refusal. Scratch workspace; the sender is a
stub; no request leaves this process.

2026-09-24: the gap scan counted 18,821 forge_report_retry faults in one week — a refused
report retried every 60 seconds, forever.
"""
import importlib.util, io, os, sys, tempfile, time, types, unittest, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vintos-report-retry-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"))
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.modules["forge_loop_runtime"] = types.SimpleNamespace(secret=lambda path: "token")
sys.modules["lab_http"] = types.SimpleNamespace(open_request=lambda *a, **k: (_ for _ in ()).throw(
    AssertionError("the real sender must never be used in this suite")))


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod


lab = load("chemistry_lab", "scripts/chemistry_lab.py")
src = load("chemistry_sources", "scripts/chemistry_sources.py")
src.report_packet = lambda ids: {"receipts": list(ids)}
OUTBOX = os.path.join(lab.ROOT, "forge-report-outbox.json")


class Sender:
    def __init__(self, fail=None): self.fail, self.calls = fail, 0
    def __call__(self, req, timeout=0):
        self.calls += 1
        if self.fail: raise self.fail
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s, n): return b'{"id": "P-1"}'
        return R()


class ReportRetry(unittest.TestCase):
    def setUp(self):
        lab._ensure()
        cfg = lab.config(); cfg["forge_report_intake"] = {"url": "http://127.0.0.1:9/api/lab-intake", "token_file": "x"}
        lab._atomic(lab.CONFIG, cfg)
        for f in (OUTBOX, src.REPORT_PAUSE):
            if os.path.exists(f): os.unlink(f)
        self.assertTrue(lab.ROOT.startswith(HOME), lab.ROOT)

    def test_a_forge_refusal_pauses_every_report_and_is_not_final(self):
        # The Forge answers 403 for "four unfinished reports; retain Lab receipts until capacity returns"
        # as well as for a real refusal. A capacity hold must never discard his findings.
        full = Sender(urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"")))
        with self.assertRaises(urllib.error.HTTPError): src.offer_report(["R1"], "q", send=full)
        row = next(iter(lab._load(OUTBOX, {}).values()))
        self.assertEqual((row["state"], row["http_status"]), ("pending", 403))
        self.assertGreater(lab._load(src.REPORT_PAUSE, {})["until"], time.time() + 60 * 25)
        tried = []
        src.offer_report, real = (lambda ids, q, send=None: tried.append(ids)), src.offer_report
        try:
            src.flush_reports()
        finally:
            src.offer_report = real
        self.assertEqual(tried, [], "while the Forge is full, no report is offered")
        os.unlink(src.REPORT_PAUSE)
        self.assertEqual(src.offer_report(["R1"], "q", send=Sender())["id"], "P-1", "after the pause it lands")

    def test_a_report_left_refused_by_the_earlier_build_is_retried(self):
        lab._atomic(OUTBOX, {"k": {"receipt_ids": ["R9"], "question": "q", "state": "refused", "next_attempt": 0}})
        tried = []
        src.offer_report, real = (lambda ids, q, send=None: tried.append(ids)), src.offer_report
        try:
            src.flush_reports()
        finally:
            src.offer_report = real
        self.assertEqual(tried, [["R9"]])

    def test_a_transient_failure_backs_off_then_is_abandoned(self):
        down = Sender(urllib.error.URLError("connection refused"))
        waits = []
        for _ in range(src.REPORT_MAX_ATTEMPTS):
            before = time.time()
            with self.assertRaises(urllib.error.URLError): src.offer_report(["R2"], "q", send=down)
            row = next(iter(lab._load(OUTBOX, {}).values()))
            waits.append(row["next_attempt"] - before)
        self.assertEqual(row["state"], "abandoned")
        self.assertTrue(all(b >= a - 1 for a, b in zip(waits, waits[1:])), waits)
        self.assertLessEqual(max(waits), src.REPORT_BACKOFF_CAP_S + 1)
        self.assertGreater(waits[5], 60 * 20, "the wait grows well past the old fixed minute")
        after = Sender()
        self.assertEqual(src.offer_report(["R2"], "q", send=after)["state"], "abandoned")
        self.assertEqual(after.calls, 0)

    def test_an_accepted_report_still_lands(self):
        self.assertEqual(src.offer_report(["R3"], "q", send=Sender())["id"], "P-1")
        self.assertEqual(next(iter(lab._load(OUTBOX, {}).values()))["state"], "accepted")


if __name__ == "__main__":
    unittest.main()
