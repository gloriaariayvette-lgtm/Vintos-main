"""The knock's RETURN reaches that morning's visit, in his own words.

2026-09-23: at the knock he chose RETURN every day and said why; the broker kept only the
word, and the visit 25 minutes later met only the handoff note he had just rejected — so it
held again, for four days. Scratch workspace; every request is a stub.
"""
import datetime, importlib.util, json, os, sys, tempfile, types, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


class Resp:
    def __init__(self, body): self.body = body
    def json(self): return self.body


class KnockReachesVisit(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="vintos-knock-")
        os.makedirs(os.path.join(self.ws, "memory"))
        self.gate = load("atelier_gate_knock_test", "scripts/atelier-gate.py")
        self.visit = load("atelier_visit_knock_test", "scripts/atelier-visit.py")
        for mod in (self.gate, self.visit): mod.WSP = self.ws
        self.sent = []

    def knock(self, answer):
        def post(url, json=None, **k):
            self.sent.append(url)
            if url.endswith("/door"): return Resp({"door": "dark", "why": "he left it held"})
            if url.endswith("/gate/knock"): return Resp({"ok": True, "note": "old note", "project": "p1", "table_since": "s"})
            if url.endswith("/gate/decide"): return Resp({"ok": True, "decision": json["decision"]})
            if url.endswith("/chat/completions"): return Resp({"choices": [{"message": {"content": answer}}]})
            raise AssertionError("unexpected send: " + url)
        self.gate.requests = types.SimpleNamespace(post=post)
        self.gate.voice = lambda: ""; self.gate._model = lambda: "stub"
        self.gate.main()

    def test_isolation(self):
        self.assertTrue(self.ws.startswith(tempfile.gettempdir()))
        self.knock("RETURN. I need to see if there is still a pulse in the work.")
        self.assertTrue(all(u.startswith("http://127.0.0.1:") for u in self.sent))

    def test_return_words_reach_todays_visit_only(self):
        self.knock("RETURN. I need to see if there is still a pulse in the work.")
        block = self.visit.knock_today()
        self.assertIn("YOU CHOSE TO RETURN", block)
        self.assertIn("still a pulse in the work", block)
        self.assertEqual(self.visit.knock_today(datetime.date.today() + datetime.timedelta(days=1)), "")

    def test_hold_is_not_carried(self):
        self.knock("HOLD. Not today.")
        self.assertEqual(self.visit.knock_today(), "")

    def test_visit_context_carries_it_after_the_old_note(self):
        self.knock("RETURN. The note is too much of an audit.")
        V = self.visit
        def post(url, json=None, **k):
            body = {"open": {"visit_capability": "cap", "budgets": {}, "intent": "x",
                             "last_handoff": "old note", "next_move": "wait"}}.get(url.rsplit("/", 1)[-1], {"ok": True})
            return Resp(body)
        V.requests = types.SimpleNamespace(post=post, get=lambda *a, **k: Resp({}))
        for n in ("voice", "where_you_are", "self_review_block", "quantum_block", "media_block",
                  "lab_lean_block", "forge_block", "plugin_block", "_manifest_block"):
            setattr(V, n, lambda *a, **k: "")
        V.stratagem_block = lambda pid: ""; V._last_piece = lambda *a, **k: ""; V.ledger_mark = lambda *a: None
        V.stratagem_step = lambda *a, **k: None; V.record_lab_lean = lambda *a: None; V.record_forge_choice = lambda *a: None
        seen = {}
        V.ask = lambda ctx, user, **k: (seen.setdefault("ctx", ctx), "<handoff>h</handoff>")[1]
        V.visit("p1")
        ctx = seen["ctx"]
        self.assertIn("too much of an audit", ctx)
        self.assertLess(ctx.index("old note"), ctx.index("too much of an audit"))


if __name__ == "__main__":
    unittest.main()
