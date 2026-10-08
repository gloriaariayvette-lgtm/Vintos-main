"""A Forge full of reports (403, X-Forge-Refusal: four_unfinished) holds the Lab's reports, once, until the
Forge's open count changes. Scratch workspace; the sender and the project reader are stubs; nothing leaves
this process.
"""
import importlib.util, io, os, sys, tempfile, types, unittest, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vintos-report-hold-")
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
# Only a missing limb is kept in the outbox by flush_reports; a bare question is withdrawn before any retry.
GAP = "The Lab needs an instrument it does not have: a molecular dynamics simulator\nIt came up on this question: q"


class Full:
    def __init__(self): self.calls = 0
    def __call__(self, req, timeout=0):
        self.calls += 1
        raise urllib.error.HTTPError("u", 403, "Forbidden", {"X-Forge-Refusal": "four_unfinished"}, io.BytesIO(b""))


class ReportHold(unittest.TestCase):
    def setUp(self):
        lab._ensure()
        cfg = lab.config(); cfg["forge_report_intake"] = {"url": "http://127.0.0.1:9/api/lab-intake", "token_file": "x"}
        lab._atomic(lab.CONFIG, cfg)
        for f in (OUTBOX, src.REPORT_PAUSE):
            if os.path.exists(f): os.unlink(f)
        self.projects = [{"state": "ready"}] * 4
        src.fetch_projects = lambda: list(self.projects)
        # The isolation itself: a throwaway store, a stub sender, a stub project reader.
        self.assertTrue(lab.ROOT.startswith(HOME), lab.ROOT)
        self.assertTrue(src.REPORT_PAUSE.startswith(HOME), src.REPORT_PAUSE)
        self.assertIsNotNone(src.fetch_projects)
        self.assertRaises(AssertionError, sys.modules["lab_http"].open_request)

    def flush(self):
        tried = []
        src.offer_report, real = (lambda ids, q, send=None: tried.append(ids)), src.offer_report
        try: src.flush_reports()
        finally: src.offer_report = real
        return tried

    def test_four_unfinished_holds_reports_until_the_count_changes(self):
        with self.assertRaises(urllib.error.HTTPError): src.offer_report(["R1"], GAP, send=Full())
        pause = lab._load(src.REPORT_PAUSE, {})
        self.assertEqual((pause["guard"], pause["unfinished"]), ("four_unfinished", 4))
        # The timed pause has run out; the hold on the Forge's count has not.
        pause["until"] = 0; lab._atomic(src.REPORT_PAUSE, pause)
        rows = lab._load(OUTBOX, {})
        for row in rows.values(): row["next_attempt"] = 0
        lab._atomic(OUTBOX, rows)
        self.assertEqual(self.flush(), [], "while the Forge's open count is unchanged, nothing is offered")
        self.assertTrue(os.path.exists(src.REPORT_PAUSE))
        self.projects = self.projects[:3]                 # one report finished: the count moved
        self.assertEqual(self.flush(), [["R1"]], "a changed count releases the hold")
        self.assertFalse(os.path.exists(src.REPORT_PAUSE))

    def test_an_unnamed_403_keeps_only_the_timed_pause(self):
        bare = lambda req, timeout=0: (_ for _ in ()).throw(
            urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"")))
        with self.assertRaises(urllib.error.HTTPError): src.offer_report(["R2"], GAP, send=bare)
        pause = lab._load(src.REPORT_PAUSE, {})
        self.assertNotIn("guard", pause)
        self.assertGreater(pause["until"], 0)


if __name__ == "__main__":
    unittest.main()
